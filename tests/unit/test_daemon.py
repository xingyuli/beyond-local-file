"""Daemon process, snapshot, baseline, and catch-up at the public CLI seam."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from beyond_local_file.cli import cli
from beyond_local_file.sync_state import SyncState

_WORKER_FLAG = "--worker"
_READY_WAIT_S = 15.0
_POLL_S = 0.05


def _invoke(args: list[str], env: dict[str, str] | None = None) -> Result:
    """Invoke the CLI in-process."""
    return CliRunner().invoke(cli, args, env=env)


def _write_workspace(tmp_path: Path, *, projects: int = 1) -> tuple[Path, list[Path], list[Path]]:
    """Create managed projects, targets, and a config file.

    Args:
        tmp_path: Test workspace root.
        projects: Number of managed-project mappings to create.

    Returns:
        Config path, managed project paths, and target project paths.
    """
    lines: list[str] = []
    managed_dirs: list[Path] = []
    target_dirs: list[Path] = []
    for index in range(projects):
        name = f"proj-{index}"
        managed = tmp_path / name
        target = tmp_path / f"target-{index}"
        managed.mkdir()
        target.mkdir()
        (managed / "shared.txt").write_text(f"hub-{index}")
        nested = managed / "nested"
        nested.mkdir()
        (nested / "keep.txt").write_text("keep")
        (nested / "change.txt").write_text("original")
        lines.append(f"{name}: {target}")
        managed_dirs.append(managed)
        target_dirs.append(target)
    config_path = tmp_path / "config.yml"
    config_path.write_text("\n".join(lines) + "\n")
    return config_path, managed_dirs, target_dirs


def _state_dir(config_path: Path) -> Path:
    """Return the .blf directory next to the loaded config."""
    return config_path.parent / ".blf"


def _pid_path(config_path: Path) -> Path:
    return _state_dir(config_path) / "daemon.pid"


def _log_path(config_path: Path) -> Path:
    return _state_dir(config_path) / "daemon.log"


def _snapshot_path(config_path: Path) -> Path:
    return _state_dir(config_path) / "mapping-snapshot.yml"


def _baseline_path(config_path: Path) -> Path:
    return _state_dir(config_path) / "baseline.yml"


def _wait_until(predicate, *, timeout: float = _READY_WAIT_S) -> None:
    """Poll *predicate* until it is true or *timeout* elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(_POLL_S)
    raise TimeoutError("condition was not met")


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
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False
    try:
        waited, _status = os.waitpid(pid, os.WNOHANG)
    except (ChildProcessError, OSError):
        return True
    return waited != pid


def _stop_daemon(config_path: Path, env: dict[str, str]) -> None:
    _invoke(["--config", str(config_path), "daemon", "stop"], env=env)
    pid = _read_pid(config_path)
    if pid is not None and _pid_alive(pid):
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and _pid_alive(pid):
            time.sleep(_POLL_S)


@pytest.fixture
def daemon_env(isolated_home: dict[str, str]) -> dict[str, str]:
    """Environment that bypasses the real ~/.blfrc."""
    return isolated_home


@pytest.fixture
def daemon_workspace(tmp_path: Path, daemon_env: dict[str, str]) -> Iterator[tuple[Path, list[Path], list[Path]]]:
    """Workspace with one mapping; always stop the daemon afterwards."""
    config_path, managed, targets = _write_workspace(tmp_path, projects=1)
    try:
        yield config_path, managed, targets
    finally:
        _stop_daemon(config_path, daemon_env)


def test_daemon_group_exposes_start_stop_status_logs() -> None:
    """blf daemon --help lists start, stop, status, and logs."""
    result = _invoke(["daemon", "--help"])

    assert result.exit_code == 0
    assert "start" in result.output
    assert "stop" in result.output
    assert "status" in result.output
    assert "logs" in result.output


def test_daemon_start_backgrounds_one_process_stop_status_and_logs(
    daemon_workspace: tuple[Path, list[Path], list[Path]],
    daemon_env: dict[str, str],
) -> None:
    """start backgrounds one process; status reflects it; stop ends it; logs follow."""
    config_path, _managed, _targets = daemon_workspace

    started = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output

    pid = _read_pid(config_path)
    assert pid is not None
    assert _pid_alive(pid)

    status_running = _invoke(["--config", str(config_path), "daemon", "status"], env=daemon_env)
    assert status_running.exit_code == 0, status_running.output
    assert "running" in status_running.output.lower()
    assert "not running" not in status_running.output.lower()

    _wait_until(lambda: _log_path(config_path).exists() and _log_path(config_path).stat().st_size > 0)
    logs_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "beyond_local_file",
            "--config",
            str(config_path),
            "daemon",
            "logs",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, **daemon_env},
    )
    try:
        deadline = time.monotonic() + 5.0
        collected = ""
        assert logs_proc.stdout is not None
        while time.monotonic() < deadline:
            line = logs_proc.stdout.readline()
            if line:
                collected += line
                break
            if logs_proc.poll() is not None:
                break
        assert collected, "logs did not print existing log content"
        logs_proc.send_signal(signal.SIGINT)
        logs_proc.wait(timeout=5)
    finally:
        if logs_proc.poll() is None:
            logs_proc.kill()
            logs_proc.wait(timeout=5)

    assert _pid_alive(pid)

    stopped = _invoke(["--config", str(config_path), "daemon", "stop"], env=daemon_env)
    assert stopped.exit_code == 0, stopped.output
    _wait_until(lambda: not _pid_alive(pid))

    status_stopped = _invoke(["--config", str(config_path), "daemon", "status"], env=daemon_env)
    assert status_stopped.exit_code == 0, status_stopped.output
    assert "not running" in status_stopped.output.lower()


def test_second_start_errors_while_daemon_is_running(
    daemon_workspace: tuple[Path, list[Path], list[Path]],
    daemon_env: dict[str, str],
) -> None:
    """A second start fails if the daemon is already running."""
    config_path, _managed, _targets = daemon_workspace

    first = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
    assert first.exit_code == 0, first.output
    pid = _read_pid(config_path)
    assert pid is not None

    second = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
    assert second.exit_code != 0
    assert "already" in second.output.lower()
    assert _read_pid(config_path) == pid
    assert _pid_alive(pid)


def test_one_daemon_process_hosts_all_managed_projects(
    tmp_path: Path,
    daemon_env: dict[str, str],
) -> None:
    """The process list shows one blf daemon, not one process per managed project."""
    config_path, _managed, _targets = _write_workspace(tmp_path, projects=2)
    try:
        started = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
        assert started.exit_code == 0, started.output
        pid = _read_pid(config_path)
        assert pid is not None
        assert _pid_alive(pid)

        listed = subprocess.check_output(["ps", "-ax", "-o", "pid=,command="], text=True)
        workers = [line for line in listed.splitlines() if _WORKER_FLAG in line and str(config_path) in line]
        assert len(workers) == 1, workers
        assert str(pid) in workers[0]
    finally:
        _stop_daemon(config_path, daemon_env)


def test_fresh_catch_up_copies_hub_trees_and_records_baseline(
    daemon_workspace: tuple[Path, list[Path], list[Path]],
    daemon_env: dict[str, str],
) -> None:
    """First start with no baseline copies hub trees into targets, then records a baseline."""
    config_path, managed_dirs, target_dirs = daemon_workspace
    managed = managed_dirs[0]
    target = target_dirs[0]

    started = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output

    assert (target / "shared.txt").is_file()
    assert not (target / "shared.txt").is_symlink()
    assert (target / "shared.txt").read_text() == "hub-0"
    assert (target / "nested" / "keep.txt").read_text() == "keep"
    assert (target / "nested" / "change.txt").read_text() == "original"
    assert (managed / "shared.txt").read_text() == "hub-0"
    assert _baseline_path(config_path).is_file()


def test_fresh_catch_up_overwrites_target_even_when_sync_state_matches_hub(
    daemon_workspace: tuple[Path, list[Path], list[Path]],
    daemon_env: dict[str, str],
) -> None:
    """No baseline means hub is truth: target edits are not reverse-synced."""
    config_path, managed_dirs, target_dirs = daemon_workspace
    managed = managed_dirs[0]
    target = target_dirs[0]
    projection = target / "shared.txt"
    projection.write_text("hub-0")
    state = SyncState(config_path.parent)
    state.update_record(managed / "shared.txt", projection)
    state.save()
    projection.write_text("from-target")

    started = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output

    assert (managed / "shared.txt").read_text() == "hub-0"
    assert projection.read_text() == "hub-0"


def test_update_catch_up_applies_only_paths_that_differ_from_baseline(
    daemon_workspace: tuple[Path, list[Path], list[Path]],
    daemon_env: dict[str, str],
) -> None:
    """A later start with a baseline only applies paths that differ from that baseline."""
    config_path, managed_dirs, target_dirs = daemon_workspace
    managed = managed_dirs[0]
    target = target_dirs[0]

    first = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
    assert first.exit_code == 0, first.output
    stopped = _invoke(["--config", str(config_path), "daemon", "stop"], env=daemon_env)
    assert stopped.exit_code == 0, stopped.output

    (managed / "nested" / "change.txt").write_text("hub-updated")
    (managed / "nested" / "new.txt").write_text("added-on-hub")
    (target / "shared.txt").write_text("target-work")
    (target / "nested" / "keep.txt").write_text("keep")

    second = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
    assert second.exit_code == 0, second.output

    assert (target / "nested" / "change.txt").read_text() == "hub-updated"
    assert (target / "nested" / "new.txt").read_text() == "added-on-hub"
    assert (target / "nested" / "keep.txt").read_text() == "keep"
    assert (target / "shared.txt").read_text() == "target-work"
    assert (managed / "shared.txt").read_text() == "hub-0"


def test_mapping_snapshot_survives_kill_and_start_does_not_delete_copies(
    daemon_workspace: tuple[Path, list[Path], list[Path]],
    daemon_env: dict[str, str],
) -> None:
    """Snapshot stays on disk after a kill; a differing config does not delete copies."""
    config_path, _managed_dirs, target_dirs = daemon_workspace
    target = target_dirs[0]

    started = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output
    snapshot = _snapshot_path(config_path)
    assert snapshot.is_file()
    snapshot_bytes = snapshot.read_bytes()
    pid = _read_pid(config_path)
    assert pid is not None

    os.kill(pid, signal.SIGKILL)
    _wait_until(lambda: not _pid_alive(pid))
    assert snapshot.is_file()
    assert snapshot.read_bytes() == snapshot_bytes

    other_target = config_path.parent / "unrelated-target"
    other_target.mkdir()
    config_path.write_text(f"proj-0: {other_target}\n")

    restarted = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
    assert restarted.exit_code == 0, restarted.output
    assert (target / "shared.txt").is_file()
    assert (target / "shared.txt").read_text() == "hub-0"
    assert not (other_target / "shared.txt").exists()
