"""Daemon log records requests, op steps, and set-wide scan/write work."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from beyond_local_file.daemon.catchup import ScanStats, record_baseline, run_catch_up, scan_items
from beyond_local_file.daemon.live import LiveSync
from beyond_local_file.daemon.log import bind_worker_stream, worker_print
from beyond_local_file.daemon.process import state_dir
from beyond_local_file.daemon.store import save_baseline, save_snapshot
from beyond_local_file.model.config import ConfigProject, Mapping
from tests.daemon_support import invoke_cli, start_daemon, stop_daemon

_LOG_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}) (.*)$")
_DURATION = re.compile(r"duration_ms=\d+")


@pytest.fixture
def worker_log() -> Iterator[StringIO]:
    buffer = StringIO()
    bind_worker_stream(buffer)
    try:
        yield buffer
    finally:
        bind_worker_stream(None)


def _messages(buffer: StringIO) -> list[str]:
    return [line for line in buffer.getvalue().splitlines() if line]


def _stamped_log_messages(log_file: Path) -> list[str]:
    messages: list[str] = []
    for line in log_file.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        match = _LOG_STAMP.match(line)
        assert match, f"unstamped log line: {line!r}"
        messages.append(match.group(2))
    assert messages, "daemon.log had no lines"
    return messages


def _one_file_projects(tmp_path: Path) -> tuple[Path, dict[str, ConfigProject]]:
    managed = tmp_path / "hub"
    target = tmp_path / "target"
    managed.mkdir()
    target.mkdir()
    (managed / "shared.txt").write_bytes(b"hello")
    (target / "shared.txt").write_bytes(b"hello")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"hub: {target}\n")
    projects = {
        "hub": ConfigProject(
            managed_project_name="hub",
            managed_project_path=managed,
            mappings=[Mapping(targets=[target], subpaths=None)],
        )
    }
    return config_path, projects


def test_worker_print_bypasses_redirected_stdout(worker_log: StringIO) -> None:
    """Worker log lines are not captured as CLI stdout."""
    captured = StringIO()
    with redirect_stdout(captured):
        worker_print("request: start op=create")
        print("Copying item.txt")

    assert "request: start op=create" in worker_log.getvalue()
    assert "Copying item.txt" in captured.getvalue()
    assert "request: start" not in captured.getvalue()
    assert "Copying" not in worker_log.getvalue()


def test_worker_print_is_silent_when_unbound(capsys: pytest.CaptureFixture[str]) -> None:
    """In-process callers without a bound worker stream do not print log lines."""
    bind_worker_stream(None)
    worker_print("secret-observability")
    print("visible")
    captured = capsys.readouterr()
    assert "secret-observability" not in captured.out
    assert "visible" in captured.out


def test_scan_items_counts_paths_files_and_hashed_bytes(tmp_path: Path) -> None:
    """A directory item reports the tree size that a slow scan would hash."""
    root = tmp_path / "hub"
    item = root / "docs"
    item.mkdir(parents=True)
    files = (item / "a.md", item / "b.md")
    files[0].write_bytes(b"aa")
    files[1].write_bytes(b"bbbb")
    stats = ScanStats()

    tree = scan_items(root, ["docs"], stats)

    assert "docs" in tree
    assert stats.files == len(files)
    assert stats.paths == 1 + stats.files
    assert stats.hashed_bytes == len(b"aa") + len(b"bbbb")


def test_record_and_write_log_size_and_duration(tmp_path: Path, worker_log: StringIO) -> None:
    """Baseline record/write and snapshot write log duration and size context."""
    config_path, projects = _one_file_projects(tmp_path)

    trees = record_baseline(projects)
    save_snapshot(config_path, projects)
    save_baseline(config_path, trees)

    messages = _messages(worker_log)
    record_line = next(line for line in messages if line.startswith("baseline: record "))
    snapshot_line = next(line for line in messages if line.startswith("snapshot: write "))
    write_line = next(line for line in messages if line.startswith("baseline: write "))
    assert "paths=" in record_line
    assert "files=" in record_line
    assert "hashed_bytes=" in record_line
    assert _DURATION.search(record_line)
    assert "bytes=" in snapshot_line
    assert _DURATION.search(snapshot_line)
    assert "bytes=" in write_line
    assert _DURATION.search(write_line)


def test_tick_logs_before_request_with_scan_size(tmp_path: Path, worker_log: StringIO) -> None:
    """A before-request tick always logs roots, scan size, duration, and applied."""
    _config_path, projects = _one_file_projects(tmp_path)
    baseline = run_catch_up(projects, tmp_path, None)
    live = LiveSync(projects, baseline)
    worker_log.truncate(0)
    worker_log.seek(0)

    live.tick(reason="before-request")

    tick_line = next(line for line in _messages(worker_log) if line.startswith("live: tick "))
    assert "reason=before-request" in tick_line
    assert "roots=" in tick_line
    assert "paths=" in tick_line
    assert "files=" in tick_line
    assert "hashed_bytes=" in tick_line
    assert "applied=false" in tick_line
    assert _DURATION.search(tick_line)


def test_fast_idle_tick_is_not_logged(tmp_path: Path, worker_log: StringIO) -> None:
    """Idle ticks that apply nothing and finish quickly do not flood the log."""
    _config_path, projects = _one_file_projects(tmp_path)
    baseline = run_catch_up(projects, tmp_path, None)
    live = LiveSync(projects, baseline)
    worker_log.truncate(0)
    worker_log.seek(0)

    live.tick(reason="idle")

    assert not any(line.startswith("live: tick ") for line in _messages(worker_log))


def test_create_writes_request_steps_and_set_wide_work_to_daemon_log(
    tmp_path: Path,
    isolated_home: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tiny create leaves a complete trail in daemon.log, not only CLI stdout."""
    managed = tmp_path / "managed"
    target = tmp_path / "target"
    managed.mkdir()
    target.mkdir()
    source = target / "item.txt"
    source.write_text("adopt me")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"managed:\n  target: {target}\n  subpath: []\n")
    log_file = state_dir(config_path) / "daemon.log"
    monkeypatch.chdir(target)
    start_daemon(config_path, isolated_home)
    try:
        created = invoke_cli(
            ["--config", str(config_path), "revlink", "create", "item.txt"],
            env=isolated_home,
        )
        assert created.exit_code == 0, created.output
        assert "Copying" in created.output
        assert "request: start" not in created.output

        messages = _stamped_log_messages(log_file)
        start_line = next(line for line in messages if line.startswith("request: start "))
        done_line = next(line for line in messages if line.startswith("request: done "))
        assert "op=create" in start_line
        assert "path=item.txt" in start_line
        assert str(target) in start_line
        assert "op=create" in done_line
        assert "exit=0" in done_line
        assert _DURATION.search(done_line)
        for step in ("validate", "copy", "checksum", "git-exclude", "config", "fan-out"):
            step_line = next(line for line in messages if line.startswith(f"create: {step} "))
            assert _DURATION.search(step_line)
        assert not any(line.startswith("live: tick reason=before-request ") for line in messages)
        assert any(line.startswith("baseline: record ") and "paths=" in line for line in messages)
        assert any(line.startswith("baseline: write ") and "bytes=" in line for line in messages)
        assert any(line.startswith("snapshot: write ") and "bytes=" in line for line in messages)
        assert any(line.startswith("persist: done ") for line in messages)
        assert not any(line.startswith("live: scan reason=reload ") for line in messages)
    finally:
        stop_daemon(config_path, isolated_home)


def test_failed_create_still_logs_request_start_and_done(
    tmp_path: Path,
    isolated_home: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing PATH still records request start and exit=1."""
    managed = tmp_path / "managed"
    target = tmp_path / "target"
    managed.mkdir()
    target.mkdir()
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"managed:\n  target: {target}\n  subpath: []\n")
    log_file = state_dir(config_path) / "daemon.log"
    monkeypatch.chdir(target)
    start_daemon(config_path, isolated_home)
    try:
        created = invoke_cli(
            ["--config", str(config_path), "revlink", "create", "missing.txt"],
            env=isolated_home,
        )
        assert created.exit_code != 0

        messages = _stamped_log_messages(log_file)
        start_line = next(line for line in messages if line.startswith("request: start "))
        done_line = next(line for line in messages if line.startswith("request: done "))
        assert "op=create" in start_line
        assert "path=missing.txt" in start_line
        assert "exit=1" in done_line
        assert not any(line.startswith("live: tick reason=before-request ") for line in messages)
        assert not any(line.startswith("persist: done ") for line in messages)
    finally:
        stop_daemon(config_path, isolated_home)
