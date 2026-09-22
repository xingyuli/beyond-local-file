"""Daemon process, snapshot, baseline, and catch-up at the public CLI seam."""

from __future__ import annotations

import hashlib
import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from beyond_local_file.cli import cli
from beyond_local_file.daemon.process import singleton_set_id, state_dir

_WORKER_FLAG = "--worker"
_READY_WAIT_S = 15.0
_POLL_S = 0.05
_LOG_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}) (.*)$")


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
    """Return the set run directory for the loaded mapping file."""
    return state_dir(config_path)


def _pid_path(config_path: Path) -> Path:
    return _state_dir(config_path) / "daemon.pid"


def _log_path(config_path: Path) -> Path:
    return _state_dir(config_path) / "logs" / "daemon.log"


def _stamped_log_messages(log_file: Path) -> list[str]:
    """Return message bodies after asserting every log line has a local-offset stamp."""
    messages: list[str] = []
    for line in log_file.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        match = _LOG_STAMP.match(line)
        assert match, f"unstamped log line: {line!r}"
        messages.append(match.group(2))
    assert messages, "daemon.log had no lines"
    return messages


def _snapshot_path(config_path: Path) -> Path:
    return _state_dir(config_path) / "mapping-snapshot.yml"


def _baseline_dir(config_path: Path) -> Path:
    return _state_dir(config_path) / "baseline"


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
    """Environment that bypasses the real ~/.blf/config."""
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
    """blf daemon --help lists start, stop, status, logs, and reload."""
    result = _invoke(["daemon", "--help"])

    assert result.exit_code == 0
    assert "start" in result.output
    assert "stop" in result.output
    assert "status" in result.output
    assert "logs" in result.output
    assert "reload" in result.output


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
            "logs",
            "daemon",
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


def test_daemon_log_lines_begin_with_local_offset_timestamp(
    daemon_workspace: tuple[Path, list[Path], list[Path]],
    daemon_env: dict[str, str],
) -> None:
    """After start, daemon-log lines begin with a millisecond local-offset stamp."""
    config_path, _managed_dirs, _targets = daemon_workspace
    log_file = _log_path(config_path)

    started = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output
    _wait_until(lambda: log_file.exists() and "daemon ready" in log_file.read_text(encoding="utf-8"))

    messages = _stamped_log_messages(log_file)
    assert "daemon worker starting" in messages
    assert any(message.startswith("catch-up:") for message in messages)
    assert "daemon ready" in messages


def test_daemon_logs_prints_stamped_lines_unchanged(
    daemon_workspace: tuple[Path, list[Path], list[Path]],
    daemon_env: dict[str, str],
) -> None:
    """blf logs daemon reprints logs/daemon.log lines as stored, including the stamp."""
    config_path, _managed, _targets = daemon_workspace
    log_file = _log_path(config_path)

    started = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output
    _wait_until(lambda: log_file.exists() and log_file.stat().st_size > 0)

    stored = log_file.read_text(encoding="utf-8")
    first_stored = stored.splitlines()[0]
    assert _LOG_STAMP.match(first_stored), first_stored

    logs_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "beyond_local_file",
            "--config",
            str(config_path),
            "logs",
            "daemon",
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
        assert collected.splitlines()[0] == first_stored
        logs_proc.send_signal(signal.SIGINT)
        logs_proc.wait(timeout=5)
    finally:
        if logs_proc.poll() is None:
            logs_proc.kill()
            logs_proc.wait(timeout=5)


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
    assert _baseline_dir(config_path).is_dir()
    assert any(_baseline_dir(config_path).rglob("*"))


def test_fresh_catch_up_preserves_nested_symlinks_in_directory_item(
    daemon_workspace: tuple[Path, list[Path], list[Path]],
    daemon_env: dict[str, str],
) -> None:
    """Nested symlinks inside a directory item stay symlinks on the replica."""
    config_path, managed_dirs, target_dirs = daemon_workspace
    managed = managed_dirs[0]
    target = target_dirs[0]
    bin_dir = managed / "nested" / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    interpreter = bin_dir / "python3.14"
    interpreter.symlink_to("/opt/homebrew/opt/python@3.14/bin/python3.14")
    (bin_dir / "python").symlink_to("python3.14")

    started = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output

    copied_interpreter = target / "nested" / "venv" / "bin" / "python3.14"
    copied_python = target / "nested" / "venv" / "bin" / "python"
    assert copied_interpreter.is_symlink()
    assert copied_python.is_symlink()
    assert os.readlink(copied_interpreter) == "/opt/homebrew/opt/python@3.14/bin/python3.14"
    assert os.readlink(copied_python) == "python3.14"


def test_daemon_start_rejects_overlapping_items_on_one_target(
    tmp_path: Path,
    daemon_env: dict[str, str],
) -> None:
    """Two managed items on one target cannot share a path prefix."""
    hub_a = tmp_path / "proj-a"
    hub_b = tmp_path / "proj-b"
    target = tmp_path / "target"
    hub_a.mkdir()
    hub_b.mkdir()
    target.mkdir()
    (hub_a / "local-file").mkdir()
    (hub_a / "local-file" / "keep.txt").write_text("keep")
    nested = hub_b / "local-file" / "devops"
    nested.mkdir(parents=True)
    (nested / "k8s.md").write_text("k8s")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "\n".join(
            [
                "proj-a:",
                f"  target: {target}",
                "  subpath:",
                "    - local-file",
                "proj-b:",
                f"  target: {target}",
                "  subpath:",
                "    - local-file/devops/k8s.md",
                "",
            ]
        )
    )

    started = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
    assert started.exit_code == 1, started.output
    assert "overlapping items" in started.output
    assert "proj-a" in started.output
    assert "proj-b" in started.output
    assert "local-file/devops/k8s.md" in started.output


def test_daemon_start_rejects_overlapping_subpaths_in_one_project(
    tmp_path: Path,
    daemon_env: dict[str, str],
) -> None:
    """One managed project cannot declare nested items for the same target."""
    hub = tmp_path / "proj-a"
    target = tmp_path / "target"
    hub.mkdir()
    target.mkdir()
    docs = hub / "docs"
    docs.mkdir()
    (docs / "readme.md").write_text("docs")
    adr = docs / "adr"
    adr.mkdir()
    (adr / "0001.md").write_text("adr")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "\n".join(
            [
                "proj-a:",
                f"  target: {target}",
                "  subpath:",
                "    - docs",
                "    - docs/adr",
                "",
            ]
        )
    )

    started = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
    assert started.exit_code == 1, started.output
    assert "overlapping items" in started.output
    assert "docs/adr" in started.output


def test_daemon_start_allows_disjoint_items_from_two_projects_on_one_target(
    tmp_path: Path,
    daemon_env: dict[str, str],
) -> None:
    """Distinct item paths from two managed projects may share a target."""
    hub_a = tmp_path / "proj-a"
    hub_b = tmp_path / "proj-b"
    target = tmp_path / "target"
    hub_a.mkdir()
    hub_b.mkdir()
    target.mkdir()
    vscode = hub_a / ".vscode"
    vscode.mkdir()
    (vscode / "settings.json").write_text("{}")
    hooks = hub_b / ".kiro" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "hook.json").write_text("{}")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "\n".join(
            [
                "proj-a:",
                f"  target: {target}",
                "  subpath:",
                "    - .vscode",
                "proj-b:",
                f"  target: {target}",
                "  subpath:",
                "    - .kiro/hooks",
                "",
            ]
        )
    )

    try:
        started = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
        assert started.exit_code == 0, started.output
        assert (target / ".vscode" / "settings.json").read_text() == "{}"
        assert (target / ".kiro" / "hooks" / "hook.json").read_text() == "{}"
    finally:
        _invoke(["--config", str(config_path), "daemon", "stop"], env=daemon_env)


def test_fresh_catch_up_overwrites_target_even_when_sync_state_matches_hub(
    daemon_workspace: tuple[Path, list[Path], list[Path]],
    daemon_env: dict[str, str],
) -> None:
    """No baseline means hub is truth: target edits are not reverse-synced."""
    config_path, managed_dirs, target_dirs = daemon_workspace
    managed = managed_dirs[0]
    target = target_dirs[0]
    projection = target / "shared.txt"
    projection.write_text("from-target")

    started = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output

    assert (managed / "shared.txt").read_text() == "hub-0"
    assert projection.read_text() == "hub-0"
    assert not (_state_dir(config_path) / "sync-state.yml").exists()


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
    """Snapshot stays on disk after a kill; a differing config without a TTY does not delete copies."""
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
    assert restarted.exit_code != 0
    assert "confirm" in restarted.output.lower() or "interactive" in restarted.output.lower()
    assert snapshot.is_file()
    assert snapshot.read_bytes() == snapshot_bytes
    assert (target / "shared.txt").is_file()
    assert (target / "shared.txt").read_text() == "hub-0"
    assert not (other_target / "shared.txt").exists()
    assert _read_pid(config_path) is None or not _pid_alive(_read_pid(config_path) or 0)


def _expected_run_dir(config_path: Path, home: Path) -> Path:
    digest = hashlib.sha256(str(config_path.resolve()).encode("utf-8")).hexdigest()
    return home / ".blf" / "run" / f"file-{digest}"


def test_daemon_start_writes_state_under_runtime_home_file_hash(
    daemon_workspace: tuple[Path, list[Path], list[Path]],
    daemon_env: dict[str, str],
) -> None:
    """start writes pid, port, log, snapshot, and baseline under ~/.blf/run/file-<hash>/."""
    config_path, _managed, _targets = daemon_workspace
    run_dir = _expected_run_dir(config_path, Path(daemon_env["BLF_HOME"]))
    hub_local = config_path.parent / ".blf"

    started = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output

    assert (run_dir / "daemon.pid").is_file()
    assert (run_dir / "daemon.port").is_file()
    assert (run_dir / "daemon.ready").is_file()
    assert (run_dir / "logs" / "daemon.log").is_file()
    assert (run_dir / "logs" / "idle.log").is_file()
    assert (run_dir / "logs" / "requests.log").is_file()
    assert not (run_dir / "daemon.log").exists()
    assert (run_dir / "mapping-snapshot.yml").is_file()
    assert (run_dir / "baseline").is_dir()
    assert any((run_dir / "baseline").rglob("*"))
    assert not (run_dir / "baseline.yml").exists()
    assert not hub_local.exists()
    assert not (Path(daemon_env["BLF_HOME"]) / ".blf" / "run" / "global").exists()


def test_daemon_start_does_not_write_under_real_home(
    daemon_workspace: tuple[Path, list[Path], list[Path]],
    daemon_env: dict[str, str],
) -> None:
    """A test daemon must not create ``~/.blf/run/file-<hash>/`` on the real home."""
    config_path, _managed, _targets = daemon_workspace
    real_run = Path.home() / ".blf" / "run" / singleton_set_id(config_path)

    started = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output
    assert not real_run.exists()
    assert (_expected_run_dir(config_path, Path(daemon_env["BLF_HOME"])) / "daemon.pid").is_file()


def test_first_start_deletes_hub_local_blf_and_prints_removed_paths(
    daemon_workspace: tuple[Path, list[Path], list[Path]],
    daemon_env: dict[str, str],
) -> None:
    """First start deletes leftover <mapping-parent>/.blf/ and prints each path."""
    config_path, _managed, _targets = daemon_workspace
    leftover = config_path.parent / ".blf"
    leftover.mkdir()
    old_pid = leftover / "daemon.pid"
    old_pid.write_text("99999\n")
    old_log = leftover / "daemon.log"
    old_log.write_text("stale\n")

    started = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output
    assert not leftover.exists()
    assert str(old_pid) in started.output
    assert str(old_log) in started.output
    assert str(leftover) in started.output


def test_cwd_config_yml_uses_singleton_run_directory(
    daemon_workspace: tuple[Path, list[Path], list[Path]],
    daemon_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CWD config.yml with no -c and no global config uses the file-<hash> run directory."""
    config_path, _managed, _targets = daemon_workspace
    run_dir = _expected_run_dir(config_path, Path(daemon_env["BLF_HOME"]))
    monkeypatch.chdir(config_path.parent)

    started = _invoke(["daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output
    assert (run_dir / "daemon.pid").is_file()
    assert not (config_path.parent / ".blf").exists()


def test_demo_style_config_yml_flag_uses_singleton_run_directory(
    daemon_workspace: tuple[Path, list[Path], list[Path]],
    daemon_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--config config.yml is a singleton set and does not create a global worker."""
    config_path, _managed, _targets = daemon_workspace
    run_dir = _expected_run_dir(config_path, Path(daemon_env["BLF_HOME"]))
    monkeypatch.chdir(config_path.parent)

    started = _invoke(["--config", "config.yml", "daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output
    assert (run_dir / "daemon.pid").is_file()
    assert not (Path(daemon_env["BLF_HOME"]) / ".blf" / "run" / "global").exists()
    assert not (config_path.parent / ".blf").exists()


def test_start_does_not_delete_runtime_home_when_mapping_file_is_in_home(
    tmp_path: Path,
    daemon_env: dict[str, str],
) -> None:
    """A mapping file in $HOME must not cause start to rmtree ~/.blf."""
    home = Path(daemon_env["BLF_HOME"])
    other_run = home / ".blf" / "run" / "file-other"
    other_run.mkdir(parents=True)
    marker = other_run / "keep.txt"
    marker.write_text("keep\n")
    managed = tmp_path / "proj-0"
    target = tmp_path / "target-0"
    managed.mkdir()
    target.mkdir()
    (managed / "shared.txt").write_text("hub")
    config_path = home / "config.yml"
    config_path.write_text(f"proj-0: {target}\n")
    try:
        started = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
        assert started.exit_code == 0, started.output
        assert marker.is_file()
        assert marker.read_text() == "keep\n"
        assert (_expected_run_dir(config_path, home) / "daemon.pid").is_file()
    finally:
        _stop_daemon(config_path, daemon_env)
