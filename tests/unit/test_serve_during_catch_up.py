"""IPC is up during catch-up: status, blocking start, TTY line, waiting shells."""

from __future__ import annotations

import os
import pty
import re
import select
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from beyond_local_file.cli import cli
from beyond_local_file.daemon.process import state_dir

_READY_WAIT_S = 15.0
_POLL_S = 0.05
_HOLD_ENV = "BLF_TEST_CATCHUP_HOLD"
_CATCH_UP_LINE = re.compile(r"Catching up (\d+)/(\d+) … (\S+)")
_DAEMON_DOWN = "daemon is not running"


def _invoke(args: list[str], env: dict[str, str] | None = None) -> Result:
    return CliRunner().invoke(cli, args, env=env)


def _state_dir(config_path: Path) -> Path:
    return state_dir(config_path)


def _pid_path(config_path: Path) -> Path:
    return _state_dir(config_path) / "daemon.pid"


def _port_path(config_path: Path) -> Path:
    return _state_dir(config_path) / "daemon.port"


def _log_path(config_path: Path) -> Path:
    return _state_dir(config_path) / "daemon.log"


def _read_pid(config_path: Path) -> int | None:
    path = _pid_path(config_path)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    return int(text.splitlines()[0])


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    try:
        waited, _status = os.waitpid(pid, os.WNOHANG)
    except (ChildProcessError, OSError):
        return True
    return waited != pid


def _wait_until(predicate, *, timeout: float = _READY_WAIT_S) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(_POLL_S)
    raise TimeoutError("condition was not met")


def _stop_daemon(config_path: Path, env: dict[str, str]) -> None:
    _invoke(["--config", str(config_path), "daemon", "stop"], env=env)
    pid = _read_pid(config_path)
    if pid is not None and _pid_alive(pid):
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and _pid_alive(pid):
            time.sleep(_POLL_S)


def _write_workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    managed = tmp_path / "proj-0"
    target = tmp_path / "target-0"
    managed.mkdir()
    target.mkdir()
    (managed / "shared.txt").write_text("hub-0")
    nested = managed / "nested"
    nested.mkdir()
    (nested / "keep.txt").write_text("keep")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"proj-0: {target}\n")
    return config_path, managed, target


def _full_env(env: dict[str, str], extra: dict[str, str] | None = None) -> dict[str, str]:
    merged = {**os.environ, **env}
    if extra:
        merged.update(extra)
    return merged


def _popen_cli(
    args: list[str],
    env: dict[str, str],
    extra: dict[str, str] | None = None,
    *,
    cwd: Path | None = None,
) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-m", "beyond_local_file", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        cwd=str(cwd) if cwd is not None else None,
        env=_full_env(env, extra),
    )


@pytest.fixture
def daemon_env(isolated_home: dict[str, str]) -> dict[str, str]:
    return isolated_home


@pytest.fixture
def catchup_workspace(tmp_path: Path, daemon_env: dict[str, str]) -> Iterator[tuple[Path, Path, Path]]:
    config_path, managed, target = _write_workspace(tmp_path)
    try:
        yield config_path, managed, target
    finally:
        _stop_daemon(config_path, daemon_env)


def _hold_start(
    config_path: Path,
    env: dict[str, str],
    hold: Path,
) -> subprocess.Popen[str]:
    hold.write_text("hold\n", encoding="utf-8")
    proc = _popen_cli(
        ["--config", str(config_path), "daemon", "start"],
        env,
        {_HOLD_ENV: str(hold)},
    )
    _wait_until(lambda: _port_path(config_path).is_file() and _read_pid(config_path) is not None)
    return proc


def _finish_start(proc: subprocess.Popen[str], hold: Path) -> subprocess.CompletedProcess[str]:
    if hold.exists():
        hold.unlink()
    stdout, stderr = proc.communicate(timeout=_READY_WAIT_S)
    return subprocess.CompletedProcess(proc.args, proc.returncode or 0, stdout, stderr)


def _read_pty(master: int, chunks: list[bytes], *, until: str | None, proc: subprocess.Popen[bytes]) -> str:
    deadline = time.monotonic() + _READY_WAIT_S
    text = b"".join(chunks).decode("utf-8", errors="replace")
    while time.monotonic() < deadline:
        if until is not None and until in text:
            return text
        if until is None and proc.poll() is not None:
            return text
        ready, _, _ = select.select([master], [], [], 0.1)
        if ready:
            try:
                data = os.read(master, 4096)
            except OSError:
                break
            if not data:
                break
            chunks.append(data)
            text = b"".join(chunks).decode("utf-8", errors="replace")
        elif proc.poll() is not None:
            return b"".join(chunks).decode("utf-8", errors="replace")
    return b"".join(chunks).decode("utf-8", errors="replace")


def test_status_during_catch_up_reports_phase_and_pid(
    catchup_workspace: tuple[Path, Path, Path],
    daemon_env: dict[str, str],
    tmp_path: Path,
) -> None:
    """Port exists during catch-up; status reports phase catch-up and the pid."""
    config_path, _managed, _target = catchup_workspace
    hold = tmp_path / "catchup.hold"
    proc = _hold_start(config_path, daemon_env, hold)
    try:
        pid = _read_pid(config_path)
        assert pid is not None
        assert _pid_alive(pid)
        assert _port_path(config_path).is_file()

        status = _invoke(["--config", str(config_path), "daemon", "status"], env=daemon_env)
        assert status.exit_code == 0, status.output
        assert "catch-up" in status.output
        assert "ready" not in status.output
        assert str(pid) in status.output
        assert proc.poll() is None
    finally:
        finished = _finish_start(proc, hold)
    assert finished.returncode == 0, finished.stdout + finished.stderr

    ready = _invoke(["--config", str(config_path), "daemon", "status"], env=daemon_env)
    assert ready.exit_code == 0, ready.output
    assert "phase ready" in ready.output
    assert str(_read_pid(config_path)) in ready.output
    assert "catch-up" not in ready.output


def test_daemon_start_does_not_return_until_phase_ready(
    catchup_workspace: tuple[Path, Path, Path],
    daemon_env: dict[str, str],
    tmp_path: Path,
) -> None:
    """daemon start stays in the foreground until phase ready."""
    config_path, _managed, _target = catchup_workspace
    hold = tmp_path / "catchup.hold"
    proc = _hold_start(config_path, daemon_env, hold)
    try:
        time.sleep(0.3)
        assert proc.poll() is None
        status = _invoke(["--config", str(config_path), "daemon", "status"], env=daemon_env)
        assert "catch-up" in status.output
    finally:
        finished = _finish_start(proc, hold)
    assert finished.returncode == 0, finished.stdout + finished.stderr
    assert "Daemon started" in finished.stdout
    status = _invoke(["--config", str(config_path), "daemon", "status"], env=daemon_env)
    assert "phase ready" in status.output


def test_non_tty_start_has_no_status_line(
    catchup_workspace: tuple[Path, Path, Path],
    daemon_env: dict[str, str],
    tmp_path: Path,
) -> None:
    """Non-TTY start prints no Catching up line."""
    config_path, _managed, _target = catchup_workspace
    hold = tmp_path / "catchup.hold"
    proc = _hold_start(config_path, daemon_env, hold)
    finished = _finish_start(proc, hold)
    assert finished.returncode == 0, finished.stdout + finished.stderr
    combined = finished.stdout + finished.stderr
    assert "Catching up" not in combined
    assert "Daemon started" in finished.stdout


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_tty_start_rewrites_one_status_line(
    catchup_workspace: tuple[Path, Path, Path],
    daemon_env: dict[str, str],
    tmp_path: Path,
) -> None:
    """TTY start rewrites one Catching up i/n line with the current item name."""
    config_path, managed, _target = catchup_workspace
    hold = tmp_path / "catchup.hold"
    hold.write_text("hold\n", encoding="utf-8")
    master, slave = pty.openpty()
    proc: subprocess.Popen[bytes] | None = None
    try:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "beyond_local_file",
                "--config",
                str(config_path),
                "daemon",
                "start",
            ],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=_full_env(daemon_env, {_HOLD_ENV: str(hold)}),
            close_fds=True,
        )
        os.close(slave)
        slave = -1
        chunks: list[bytes] = []
        text = _read_pty(master, chunks, until="Catching up", proc=proc)
        assert "Catching up" in text, text
        assert "\r" in text
        match = _CATCH_UP_LINE.search(text.replace("\r", "\n"))
        assert match, text
        assert int(match.group(1)) >= 1
        assert int(match.group(2)) >= 1
        assert match.group(3) in {"shared.txt", "nested"}
        assert "keep.txt" not in match.group(0)
        assert str(managed) not in match.group(0)
        hold.unlink()
        text = _read_pty(master, chunks, until=None, proc=proc)
        assert proc.wait(timeout=_READY_WAIT_S) == 0
        assert "Daemon started" in text
    finally:
        if hold.exists():
            hold.unlink()
        if slave != -1:
            os.close(slave)
        os.close(master)
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_link_check_waits_through_catch_up_instead_of_daemon_down(
    catchup_workspace: tuple[Path, Path, Path],
    daemon_env: dict[str, str],
    tmp_path: Path,
) -> None:
    """link check during catch-up waits for ready instead of failing daemon-down."""
    config_path, _managed, _target = catchup_workspace
    hold = tmp_path / "catchup.hold"
    start_proc = _hold_start(config_path, daemon_env, hold)
    check_proc: subprocess.Popen[str] | None = None
    try:
        check_proc = _popen_cli(["--config", str(config_path), "link", "check"], daemon_env)
        time.sleep(0.4)
        assert check_proc.poll() is None
        hold.unlink()
        stdout, stderr = check_proc.communicate(timeout=_READY_WAIT_S)
        assert check_proc.returncode == 0, stdout + stderr
        assert _DAEMON_DOWN not in (stdout + stderr).lower()
        assert "proj-0" in stdout
    finally:
        finished = _finish_start(start_proc, hold)
        if check_proc is not None and check_proc.poll() is None:
            check_proc.kill()
            check_proc.wait(timeout=5)
    assert finished.returncode == 0, finished.stdout + finished.stderr


def test_revlink_and_remove_wait_through_catch_up_instead_of_daemon_down(
    catchup_workspace: tuple[Path, Path, Path],
    daemon_env: dict[str, str],
    tmp_path: Path,
) -> None:
    """revlink restore and remove wait through catch-up instead of daemon-down."""
    config_path, _managed, target = catchup_workspace
    hold = tmp_path / "catchup.hold"
    start_proc = _hold_start(config_path, daemon_env, hold)
    restore_proc: subprocess.Popen[str] | None = None
    remove_proc: subprocess.Popen[str] | None = None
    try:
        restore_proc = _popen_cli(
            ["--config", str(config_path), "revlink", "restore", "--dry-run", "shared.txt"],
            daemon_env,
            cwd=target,
        )
        remove_proc = _popen_cli(
            ["--config", str(config_path), "remove", "--dry-run", "nested"],
            daemon_env,
            cwd=target,
        )
        time.sleep(0.4)
        assert restore_proc.poll() is None
        assert remove_proc.poll() is None
        hold.unlink()
        restore_out, restore_err = restore_proc.communicate(timeout=_READY_WAIT_S)
        remove_out, remove_err = remove_proc.communicate(timeout=_READY_WAIT_S)
        restore_text = restore_out + restore_err
        remove_text = remove_out + remove_err
        assert restore_proc.returncode == 0, restore_text
        assert remove_proc.returncode == 0, remove_text
        assert _DAEMON_DOWN not in restore_text.lower()
        assert _DAEMON_DOWN not in remove_text.lower()
    finally:
        finished = _finish_start(start_proc, hold)
        for child in (restore_proc, remove_proc):
            if child is not None and child.poll() is None:
                child.kill()
                child.wait(timeout=5)
    assert finished.returncode == 0, finished.stdout + finished.stderr


def test_live_observe_does_not_run_during_catch_up(
    catchup_workspace: tuple[Path, Path, Path],
    daemon_env: dict[str, str],
    tmp_path: Path,
) -> None:
    """A target edit during catch-up is not applied until phase ready."""
    config_path, managed, target = catchup_workspace
    hold = tmp_path / "catchup.hold"
    proc = _hold_start(config_path, daemon_env, hold)
    try:
        _wait_until((target / "shared.txt").is_file)
        (target / "shared.txt").write_text("during-hold")
        time.sleep(0.6)
        assert (managed / "shared.txt").read_text() == "hub-0"
        log = _log_path(config_path)
        if log.exists():
            assert "live:" not in log.read_text(encoding="utf-8")
    finally:
        finished = _finish_start(proc, hold)
    assert finished.returncode == 0, finished.stdout + finished.stderr

    (managed / "nested" / "keep.txt").write_text("after-ready")
    _wait_until(lambda: (target / "nested" / "keep.txt").read_text() == "after-ready")
    assert (target / "nested" / "keep.txt").read_text() == "after-ready"
