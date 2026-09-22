"""Live link check through CLI, daemon IPC, and TTY status lines."""

from __future__ import annotations

import os
import pty
import re
import select
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from beyond_local_file.daemon.client import send_when_up
from beyond_local_file.daemon.handlers import handle_request
from beyond_local_file.daemon.process import state_dir
from tests.daemon_support import daemon_running, invoke_cli, start_daemon, stop_daemon

_READY_WAIT_S = 15.0
_CHECK_LINE = re.compile(r"Checking (\d+)/(\d+) … (\S+)")


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
        env=_full_env(env),
    )


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


def _sync_state_paths(config_path: Path) -> list[Path]:
    run_dir = state_dir(config_path)
    return [
        run_dir / "sync-state.yml",
        config_path.parent / "sync-state.yml",
        config_path.parent / ".blf" / "sync-state.yml",
    ]


@pytest.fixture
def check_workspace(tmp_path: Path, isolated_home: dict[str, str]) -> Iterator[tuple[Path, Path, Path]]:
    config_path, managed, target = _write_workspace(tmp_path)
    try:
        yield config_path, managed, target
    finally:
        stop_daemon(config_path, isolated_home)


def test_check_handler_streams_checking_status_then_table(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """The check handler streams Checking i/n lines, then a table with no k/n."""
    del isolated_home
    config_path, _managed, target = _write_workspace(tmp_path)
    (target / "shared.txt").write_text("hub-0")
    nested = target / "nested"
    nested.mkdir()
    (nested / "keep.txt").write_text("keep")

    progress: list[str] = []
    response = handle_request(config_path, {"op": "check"}, on_progress=progress.append)

    assert response["exit_code"] == 0
    assert progress
    names: list[str] = []
    for line in progress:
        match = _CHECK_LINE.fullmatch(line)
        assert match, line
        assert int(match.group(1)) >= 1
        assert int(match.group(2)) >= 1
        names.append(match.group(3))
        assert "keep.txt" not in match.group(0)
        assert str(target) not in match.group(0)
    assert "shared.txt" in names
    assert "nested" in names
    stdout = str(response.get("stdout") or "")
    assert "proj-0" in stdout
    assert "Copy" in stdout
    assert "Checking " not in stdout
    assert "k/n" not in stdout
    assert not any(path.exists() for path in _sync_state_paths(config_path))


def test_check_handler_verbose_is_line_oriented_without_progress(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Verbose check stays line-oriented and does not stream a status line."""
    del isolated_home
    config_path, _managed, target = _write_workspace(tmp_path)
    (target / "shared.txt").write_text("hub-0")
    nested = target / "nested"
    nested.mkdir()
    (nested / "keep.txt").write_text("keep")

    progress: list[str] = []
    response = handle_request(
        config_path,
        {"op": "check", "output_format": "verbose"},
        on_progress=progress.append,
    )

    assert response["exit_code"] == 0
    assert progress == []
    stdout = str(response.get("stdout") or "")
    assert "Copy Status" in stdout
    assert "Copy Sync Status" in stdout
    assert "(in sync)" in stdout
    assert "┌" not in stdout
    assert not _CHECK_LINE.search(stdout)


def test_daemon_check_live_match_writes_no_sync_state(
    check_workspace: tuple[Path, Path, Path],
    isolated_home: dict[str, str],
) -> None:
    """After catch-up, check reports in-sync and never writes sync-state.yml."""
    config_path, _managed, _target = check_workspace
    with daemon_running(config_path, isolated_home):
        result = invoke_cli(
            ["--config", str(config_path), "link", "check", "--format", "verbose"],
            env=isolated_home,
        )
        assert result.exit_code == 0, result.output
        assert "(in sync)" in result.output
        assert "(manually synced)" not in result.output
        assert not any(path.exists() for path in _sync_state_paths(config_path))


def test_daemon_check_labels_mismatch_from_baseline_not_sync_state(
    check_workspace: tuple[Path, Path, Path],
    isolated_home: dict[str, str],
) -> None:
    """Live mismatch is labeled from baseline hashes; sync-state.yml is ignored."""
    config_path, managed, target = check_workspace
    start_daemon(config_path, isolated_home)
    stop_daemon(config_path, isolated_home)

    (managed / "shared.txt").write_text("managed-new")
    (target / "nested" / "keep.txt").write_text("target-new")
    lying = state_dir(config_path) / "sync-state.yml"
    lying.write_text("synced_files: []\n", encoding="utf-8")

    progress: list[str] = []
    response = handle_request(
        config_path,
        {"op": "check", "output_format": "verbose"},
        on_progress=progress.append,
    )

    assert response["exit_code"] == 0
    stdout = str(response.get("stdout") or "")
    assert "shared.txt" in stdout
    assert "(managed changed)" in stdout
    assert "nested" in stdout
    assert "(target changed)" in stdout
    assert "(manually synced)" not in stdout
    assert lying.exists()
    assert not any(path.exists() for path in _sync_state_paths(config_path) if path != lying)


def test_non_tty_check_prints_table_only(
    check_workspace: tuple[Path, Path, Path],
    isolated_home: dict[str, str],
) -> None:
    """Non-TTY check prints the final table and no status line."""
    config_path, _managed, _target = check_workspace
    with daemon_running(config_path, isolated_home):
        proc = _popen_cli(["--config", str(config_path), "link", "check"], isolated_home)
        stdout, stderr = proc.communicate(timeout=_READY_WAIT_S)
        assert proc.returncode == 0, stdout + stderr
        combined = stdout + stderr
        assert "proj-0" in stdout
        assert "Copy" in stdout
        assert "Checking " not in combined
        assert "k/n" not in stdout


def test_verbose_cli_stays_line_oriented(
    check_workspace: tuple[Path, Path, Path],
    isolated_home: dict[str, str],
) -> None:
    """CLI --format verbose stays line-oriented with no Live table."""
    config_path, _managed, _target = check_workspace
    with daemon_running(config_path, isolated_home):
        proc = _popen_cli(
            ["--config", str(config_path), "link", "check", "--format", "verbose"],
            isolated_home,
        )
        stdout, stderr = proc.communicate(timeout=_READY_WAIT_S)
        assert proc.returncode == 0, stdout + stderr
        assert "Copy Status" in stdout
        assert "Copy Sync Status" in stdout
        assert not _CHECK_LINE.search(stdout + stderr)
        assert "┌" not in stdout


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_tty_check_opens_shell_screen_then_prints_table(
    check_workspace: tuple[Path, Path, Path],
    isolated_home: dict[str, str],
) -> None:
    """TTY check opens the shell screen and, after close, prints the table."""
    config_path, managed, _target = check_workspace
    with daemon_running(config_path, isolated_home):
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
                    "link",
                    "check",
                ],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                env=_full_env(isolated_home),
                close_fds=True,
            )
            os.close(slave)
            slave = -1
            chunks: list[bytes] = []
            text = _read_pty(master, chunks, until="q: close", proc=proc)
            assert "\x1b[?1049h" in text, text
            assert "link check  all projects" in text
            assert "proj-0" in text
            assert "shared.txt" in text or "nested" in text
            assert "keep.txt" not in text
            assert str(managed) not in text
            assert proc.poll() is None
            os.write(master, b"q")
            text = _read_pty(master, chunks, until=None, proc=proc)
            assert proc.wait(timeout=_READY_WAIT_S) == 0
            assert "proj-0" in text
            assert "Copy" in text
            assert "k/n" not in text.replace("\r", "\n")
        finally:
            if slave != -1:
                os.close(slave)
            os.close(master)
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)


def test_daemon_ipc_streams_check_progress_on_existing_connection(
    check_workspace: tuple[Path, Path, Path],
    isolated_home: dict[str, str],
) -> None:
    """Check progress events reuse the shell IPC stream used for catch-up."""
    config_path, _managed, _target = check_workspace
    with daemon_running(config_path, isolated_home):
        progress: list[str] = []
        response = send_when_up(config_path, {"op": "check"}, on_progress=progress.append)
        assert int(response.get("exit_code", 1)) == 0
        assert progress
        checking = [line for line in progress if _CHECK_LINE.fullmatch(line)]
        assert checking
        assert any(line.startswith("Waiting · proj-0") for line in progress)
        assert any(line.startswith("Checking ") and line.endswith(" · proj-0") for line in progress)
        assert "Done · proj-0" in progress
        stdout = str(response.get("stdout") or "")
        assert "proj-0" in stdout
        assert "Checking " not in stdout
