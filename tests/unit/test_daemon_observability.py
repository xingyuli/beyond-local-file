"""Daemon log records requests, op steps, and set-wide scan/write work."""

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

_LOG_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}) (.*)$")
_DURATION = re.compile(r"duration_ms=\d+")
_IDLE_KEEP_MS = 100
_DAEMON_COLOR = "\033[36m[daemon]\033[0m"
_IDLE_COLOR = "\033[33m[idle]\033[0m"
_REQUESTS_COLOR = "\033[32m[requests]\033[0m"


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


def _log_dir(config_path: Path) -> Path:
    return state_dir(config_path) / "logs"


def _stamped_log_messages(log_file: Path) -> list[str]:
    messages: list[str] = []
    for line in log_file.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        match = _LOG_STAMP.match(line)
        assert match, f"unstamped log line: {line!r}"
        messages.append(match.group(2))
    return messages


def _require_messages(log_file: Path) -> list[str]:
    messages = _stamped_log_messages(log_file)
    assert messages, f"{log_file} had no lines"
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


def test_create_writes_request_steps_and_times_to_the_request_log(
    tmp_path: Path,
    isolated_home: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tiny create leaves start, steps, and done in the request log, not CLI stdout."""
    managed = tmp_path / "managed"
    target = tmp_path / "target"
    managed.mkdir()
    target.mkdir()
    source = target / "item.txt"
    source.write_text("adopt me")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"managed:\n  target: {target}\n  subpath: []\n")
    logs = _log_dir(config_path)
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

        messages = _require_messages(logs / "requests.log")
        _assert_create_request(messages, target)
        _assert_start_lifecycle(logs / "daemon.log", messages)
    finally:
        stop_daemon(config_path, isolated_home)
        _assert_stopped(logs)


def test_dry_run_create_omits_persist_ms(
    tmp_path: Path,
    isolated_home: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dry-run still logs the worker unit and omits persist_ms."""
    _managed, target, config_path = _managed_target(tmp_path)
    (target / "item.txt").write_text("adopt me")
    monkeypatch.chdir(target)
    start_daemon(config_path, isolated_home)
    try:
        created = invoke_cli(
            ["--config", str(config_path), "revlink", "create", "--dry-run", "item.txt"],
            env=isolated_home,
        )
        assert created.exit_code == 0, created.output
        messages = _require_messages(_log_dir(config_path) / "requests.log")
        done_line = next(line for line in messages if line.startswith("request: done "))
        assert "unit=managed" in done_line
        assert "queue_ms=" in done_line
        assert "op_ms=" in done_line
        assert "persist_ms=" not in done_line
        assert "dry_run=true" in done_line
        assert not any(line.startswith("persist: done ") for line in messages)
    finally:
        stop_daemon(config_path, isolated_home)


def test_failed_create_still_logs_request_start_and_done(
    tmp_path: Path,
    isolated_home: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing PATH still records request start and exit=1 in the request log."""
    _managed, target, config_path = _managed_target(tmp_path)
    monkeypatch.chdir(target)
    start_daemon(config_path, isolated_home)
    try:
        created = invoke_cli(
            ["--config", str(config_path), "revlink", "create", "missing.txt"],
            env=isolated_home,
        )
        assert created.exit_code != 0

        messages = _require_messages(_log_dir(config_path) / "requests.log")
        start_line = next(line for line in messages if line.startswith("request: start "))
        done_line = next(line for line in messages if line.startswith("request: done "))
        assert "op=create" in start_line
        assert "path=missing.txt" in start_line
        assert "unit=managed" in start_line
        assert "unit=managed" in done_line
        assert "exit=1" in done_line
        assert "queue_ms=" in done_line
        assert "op_ms=" in done_line
        assert "persist_ms=" in done_line
        assert not any(line.startswith("live: tick reason=before-request ") for line in messages)
        assert not any(line.startswith("persist: done ") for line in messages)
    finally:
        stop_daemon(config_path, isolated_home)


def test_applying_idle_tick_lands_in_the_idle_log(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """An idle apply, its follow-on lines, and the worker unit go to the idle log."""
    managed = tmp_path / "proj-0"
    target = tmp_path / "target-0"
    managed.mkdir()
    target.mkdir()
    (managed / "shared.txt").write_text("hub-0")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"proj-0: {target}\n")
    env = {**isolated_home, "BLF_IDLE_OBSERVE_S": "0.2"}
    start_daemon(config_path, env)
    try:
        (managed / "shared.txt").write_text("from-hub")
        idle_log = _log_dir(config_path) / "idle.log"
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if idle_log.is_file() and "applied=true" in idle_log.read_text(encoding="utf-8"):
                break
            time.sleep(0.05)
        messages = _require_messages(idle_log)
        tick = next(line for line in messages if line.startswith("live: tick ") and "applied=true" in line)
        assert "reason=idle" in tick
        assert "unit=proj-0" in tick
        apply = next(line for line in messages if line.startswith("live: update "))
        assert "unit=proj-0" in apply
        persist = next(line for line in messages if line.startswith("baseline: write "))
        assert "unit=proj-0" in persist
        for line in messages:
            if line.startswith("live: tick ") and "applied=false" in line:
                match = re.search(r"duration_ms=(\d+)", line)
                assert match is not None
                assert int(match.group(1)) >= _IDLE_KEEP_MS
        request_text = (_log_dir(config_path) / "requests.log").read_text(encoding="utf-8")
        daemon_text = (_log_dir(config_path) / "daemon.log").read_text(encoding="utf-8")
        assert "reason=idle" not in request_text
        assert "reason=idle" not in daemon_text
    finally:
        stop_daemon(config_path, env)


def test_check_on_two_worker_units_lists_each_duration(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A set-wide check names each worker unit's duration on the done line."""
    alpha_hub = tmp_path / "alpha"
    beta_hub = tmp_path / "beta"
    alpha_target = tmp_path / "lab-app"
    beta_target = tmp_path / "lab-notes"
    for hub, target, name in (
        (alpha_hub, alpha_target, "a"),
        (beta_hub, beta_target, "b"),
    ):
        hub.mkdir()
        target.mkdir()
        (hub / f"shared-{name}.txt").write_text(name)
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"alpha: {alpha_target}\nbeta: {beta_target}\n")
    start_daemon(config_path, isolated_home)
    try:
        checked = invoke_cli(["--config", str(config_path), "link", "check"], env=isolated_home)
        assert checked.exit_code == 0, checked.output
        messages = _require_messages(_log_dir(config_path) / "requests.log")
        done_line = next(line for line in messages if line.startswith("request: done "))
        assert "op=check" in done_line
        assert "queue_ms=" in done_line
        assert "op_ms=" in done_line
        assert "persist_ms=" in done_line
        assert re.search(r"unit=alpha:\d+", done_line)
        assert re.search(r"unit=beta:\d+", done_line)
    finally:
        stop_daemon(config_path, isolated_home)


def test_blf_logs_merges_with_a_prefix_and_daemon_logs_does_not_follow(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Merged follow prefixes lines; one file does not; daemon logs names blf logs."""
    config_path = _write_log_fixture(tmp_path)
    env = {**os.environ, **isolated_home}
    merged = _follow_lines(config_path, ["logs"], env, count=3)
    assert merged == [
        "[daemon] 2026-09-21T18:55:09.100+08:00 daemon worker starting",
        "[requests] 2026-09-21T18:55:09.200+08:00 request: start op=create unit=hub",
        "[idle] 2026-09-21T18:55:09.300+08:00 live: tick reason=idle unit=hub",
    ]
    assert "\033[" not in "\n".join(merged)
    one = _follow_lines(config_path, ["logs", "daemon"], env, count=1)
    assert one == ["2026-09-21T18:55:09.100+08:00 daemon worker starting"]
    retired = subprocess.run(
        [sys.executable, "-m", "beyond_local_file", "--config", str(config_path), "daemon", "logs"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        timeout=5,
        check=False,
    )
    assert retired.returncode == 0
    assert "blf logs" in retired.stdout
    assert "daemon worker starting" not in retired.stdout


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_blf_logs_colors_record_names_on_a_terminal(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A terminal merge colors [daemon], [idle], and [requests]; the prefix stays."""
    config_path = _write_log_fixture(tmp_path)
    master, slave = pty.openpty()
    proc: subprocess.Popen[bytes] | None = None
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "beyond_local_file", "--config", str(config_path), "logs"],
            stdin=subprocess.DEVNULL,
            stdout=slave,
            stderr=slave,
            env={**os.environ, **isolated_home},
            close_fds=True,
        )
        os.close(slave)
        slave = -1
        chunks: list[bytes] = []
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and proc.poll() is None:
            ready, _, _ = select.select([master], [], [], 0.2)
            if not ready:
                continue
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)
            text = b"".join(chunks).decode("utf-8", errors="replace")
            if _DAEMON_COLOR in text and _IDLE_COLOR in text and _REQUESTS_COLOR in text:
                break
        text = b"".join(chunks).decode("utf-8", errors="replace")
        assert _DAEMON_COLOR in text
        assert _REQUESTS_COLOR in text
        assert _IDLE_COLOR in text
    finally:
        if slave >= 0:
            os.close(slave)
        os.close(master)
        if proc is not None and proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def _assert_create_request(messages: list[str], target: Path) -> None:
    start_line = next(line for line in messages if line.startswith("request: start "))
    done_line = next(line for line in messages if line.startswith("request: done "))
    assert "op=create" in start_line
    assert "path=item.txt" in start_line
    assert str(target) in start_line
    assert "unit=managed" in start_line
    assert "unit=managed" in done_line
    for line in (start_line, done_line):
        assert "queue_ms=" in line
        assert "op_ms=" in line
        assert "persist_ms=" in line
    assert "op=create" in done_line
    assert "exit=0" in done_line
    for step in ("validate", "copy", "checksum", "git-exclude", "config", "fan-out"):
        step_line = next(line for line in messages if line.startswith(f"create: {step} "))
        assert _DURATION.search(step_line)
        assert "unit=managed" in step_line
    assert not any(line.startswith("live: tick reason=before-request ") for line in messages)
    assert any(line.startswith("baseline: record ") and "paths=" in line for line in messages)
    assert any(line.startswith("baseline: write ") and "bytes=" in line for line in messages)
    assert any(line.startswith("snapshot: write ") and "bytes=" in line for line in messages)
    assert any(line.startswith("persist: done ") for line in messages)
    assert not any(line.startswith("live: scan reason=reload ") for line in messages)


def _assert_start_lifecycle(daemon_log: Path, request_messages: list[str]) -> None:
    daemon_messages = _require_messages(daemon_log)
    assert "daemon worker starting" in daemon_messages
    assert any(line.startswith("catch-up:") for line in daemon_messages)
    assert "daemon ready" in daemon_messages
    assert not any(line.startswith("request: ") for line in daemon_messages)
    assert "daemon worker starting" not in request_messages
    assert "daemon ready" not in request_messages


def _assert_stopped(logs: Path) -> None:
    daemon_log = logs / "daemon.log"
    request_log = logs / "requests.log"
    if not daemon_log.is_file() or not request_log.is_file():
        return
    assert "daemon stopping" in _stamped_log_messages(daemon_log)
    assert "daemon stopping" not in _stamped_log_messages(request_log)


def _managed_target(tmp_path: Path) -> tuple[Path, Path, Path]:
    managed = tmp_path / "managed"
    target = tmp_path / "target"
    managed.mkdir()
    target.mkdir()
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"managed:\n  target: {target}\n  subpath: []\n")
    return managed, target, config_path


def _write_log_fixture(tmp_path: Path) -> Path:
    managed = tmp_path / "hub"
    target = tmp_path / "target"
    managed.mkdir()
    target.mkdir()
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"hub: {target}\n")
    logs = _log_dir(config_path)
    logs.mkdir(parents=True)
    (logs / "daemon.log").write_text("2026-09-21T18:55:09.100+08:00 daemon worker starting\n", encoding="utf-8")
    (logs / "requests.log").write_text(
        "2026-09-21T18:55:09.200+08:00 request: start op=create unit=hub\n",
        encoding="utf-8",
    )
    (logs / "idle.log").write_text(
        "2026-09-21T18:55:09.300+08:00 live: tick reason=idle unit=hub\n",
        encoding="utf-8",
    )
    return config_path


def _follow_lines(config_path: Path, args: list[str], env: dict[str, str], *, count: int) -> list[str]:
    proc = subprocess.Popen(
        [sys.executable, "-m", "beyond_local_file", "--config", str(config_path), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    collected: list[str] = []
    try:
        assert proc.stdout is not None
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and len(collected) < count:
            line = proc.stdout.readline()
            if line:
                collected.append(line.rstrip("\n"))
                continue
            if proc.poll() is not None:
                break
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=5)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
    assert len(collected) == count, collected
    return collected
