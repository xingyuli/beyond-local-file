"""Long-running daemon worker: serve IPC, then catch-up, then live observe."""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import TextIO

from beyond_local_file.contribution import echo_item_path_overlaps
from beyond_local_file.model.config import ConfigProject
from beyond_local_file.project_processor import load_set_projects

from .catchup import run_catch_up
from .handlers import handle_request
from .ipc import ProgressCallback, Request, Response, ServeLoop, WorkerState, serve_requests
from .live import LiveSync
from .log import bind_worker_stream
from .process import state_dir, write_ready
from .store import BaselineTrees, load_baseline, load_snapshot, mappings_equal, save_baseline, save_snapshot

_TEST_HOLD_ENV = "BLF_TEST_CATCHUP_HOLD"
_TEST_IDLE_HOLD_ENV = "BLF_TEST_IDLE_HOLD"
_HOLD_POLL_S = 0.05
_HOLD_TIMEOUT_S = 60.0
IDLE_OBSERVE_S = 15.0

type ProgressFn = Callable[[int, int, str], None]


@dataclass
class _LiveRuntime:
    config_path: Path
    shutdown: threading.Event
    bound: threading.Event
    state: WorkerState
    live_holder: dict[str, LiveSync]
    live_lock: threading.Lock
    failed: threading.Event


def run_worker(config_path: Path) -> int:
    """Bind IPC, catch-up while serving status, then live-observe until stop.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        Process exit code.
    """
    _stamp_worker_streams()
    runtime = _LiveRuntime(
        config_path=config_path,
        shutdown=threading.Event(),
        bound=threading.Event(),
        state=WorkerState(),
        live_holder={},
        live_lock=threading.Lock(),
        failed=threading.Event(),
    )

    def _handle(signum: int, frame: FrameType | None) -> None:
        del signum, frame
        runtime.shutdown.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)

    print("daemon worker starting", flush=True)

    def _on_request(
        request_config: Path,
        request: Request,
        on_progress: ProgressCallback | None = None,
    ) -> Response:
        return _handle_live_request(request_config, request, on_progress, runtime)

    threading.Thread(target=_catch_up_worker, args=(runtime,), name="blf-catch-up", daemon=True).start()
    threading.Thread(target=_run_idle_loop, args=(runtime,), name="blf-idle", daemon=True).start()
    serve_requests(
        config_path,
        _on_request,
        ServeLoop(shutdown=runtime.shutdown, bound=runtime.bound, state=runtime.state),
    )
    print("daemon stopping", flush=True)
    return 1 if runtime.failed.is_set() else 0


def _tick_live(reason: str, runtime: _LiveRuntime) -> None:
    if not runtime.state.ready.is_set():
        return
    live = runtime.live_holder.get("live")
    if live is None:
        return
    with runtime.live_lock:
        if reason == "idle":
            _await_idle_hold()
        if live.tick(reason=reason):
            save_baseline(runtime.config_path, live.baseline, live.projects)


def _handle_live_request(
    request_config: Path,
    request: Request,
    on_progress: ProgressCallback | None,
    runtime: _LiveRuntime,
) -> Response:
    live = runtime.live_holder.get("live")
    op = request.get("op")
    if live is not None and op in {"create", "restore", "remove", "reload"}:
        with runtime.live_lock:
            applied = live.apply()
            if applied:
                save_baseline(request_config, live.baseline, live.projects, changed_rels=applied)
    response = handle_request(request_config, request, on_progress=on_progress)
    mutating = op in {"create", "restore", "remove", "reload"} and not request.get("dry_run")
    if live is not None and mutating and response.get("exit_code") == 0:
        snapshot = load_snapshot(request_config)
        baseline = load_baseline(request_config)
        if snapshot is not None and baseline is not None:
            with runtime.live_lock:
                live.reload(snapshot, baseline)
    return response


def _catch_up_worker(runtime: _LiveRuntime) -> None:
    if not runtime.bound.wait(timeout=10.0):
        runtime.failed.set()
        runtime.shutdown.set()
        return
    try:
        caught = _catch_up_and_persist(runtime.config_path, on_progress=runtime.state.set_progress)
    except Exception as error:
        print(f"catch-up: failed: {error}", flush=True)
        runtime.failed.set()
        runtime.shutdown.set()
        return
    if caught is None:
        runtime.failed.set()
        runtime.shutdown.set()
        return
    if runtime.shutdown.is_set():
        return
    projects, trees = caught
    runtime.live_holder["live"] = LiveSync(projects, trees)
    write_ready(runtime.config_path)
    print("daemon ready", flush=True)
    runtime.state.set_ready()


def _catch_up_and_persist(
    config_path: Path,
    on_progress: ProgressFn | None = None,
) -> tuple[dict[str, ConfigProject], BaselineTrees] | None:
    """Catch up committed mappings, or abort when items overlap on a target.

    Args:
        config_path: Path to the loaded config file.
        on_progress: Optional catch-up unit/item callback for IPC status lines.

    Returns:
        Projects and baseline trees, or None when start must not continue.
    """
    file_projects = load_set_projects(config_path)
    snapshot_projects = load_snapshot(config_path)
    if snapshot_projects is None:
        projects = file_projects
        print("catch-up: no mapping snapshot; using config file", flush=True)
    elif not mappings_equal(file_projects, snapshot_projects):
        projects = snapshot_projects
        print(
            "config file differs from mapping snapshot; starting from snapshot until reload",
            flush=True,
        )
    else:
        projects = file_projects
        print("catch-up: mapping snapshot matches config file", flush=True)

    if echo_item_path_overlaps(projects):
        return None

    trees = run_catch_up(
        projects,
        state_dir(config_path),
        load_baseline(config_path),
        on_progress=on_progress,
    )
    save_snapshot(config_path, projects)
    save_baseline(config_path, trees, projects)
    _await_test_hold()
    return projects, trees


def _await_test_hold() -> None:
    raw = os.environ.get(_TEST_HOLD_ENV)
    if not raw:
        return
    path = Path(raw)
    deadline = time.monotonic() + _HOLD_TIMEOUT_S
    while path.exists() and time.monotonic() < deadline:
        time.sleep(_HOLD_POLL_S)


def _run_idle_loop(runtime: _LiveRuntime) -> None:
    if not runtime.state.ready.wait(timeout=_HOLD_TIMEOUT_S):
        return
    while not runtime.shutdown.is_set():
        _tick_live("idle", runtime)
        if runtime.shutdown.wait(timeout=_idle_observe_s()):
            return


def _idle_observe_s() -> float:
    raw = os.environ.get("BLF_IDLE_OBSERVE_S")
    if not raw:
        return IDLE_OBSERVE_S
    try:
        return max(0.0, float(raw))
    except ValueError:
        return IDLE_OBSERVE_S


def _await_idle_hold() -> None:
    raw = os.environ.get(_TEST_IDLE_HOLD_ENV)
    if not raw:
        return
    path = Path(raw)
    Path(str(path) + ".entered").write_text("1", encoding="utf-8")
    deadline = time.monotonic() + _HOLD_TIMEOUT_S
    while path.exists() and time.monotonic() < deadline:
        time.sleep(_HOLD_POLL_S)


def _stamp_worker_streams() -> None:
    """Prefix each new stdout and stderr line with the host local time and offset."""
    sys.stdout = _TimestampedStream(sys.stdout)
    sys.stderr = _TimestampedStream(sys.stderr)
    bind_worker_stream(sys.stdout)


def _line_stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class _TimestampedStream:
    """Text stream that stamps each new line at write time."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._at_line_start = True

    def write(self, data: str | bytes) -> int:
        if not data:
            return 0
        written = len(data)
        if isinstance(data, bytes):
            encoding = getattr(self._stream, "encoding", None) or "utf-8"
            text = data.decode(encoding, errors="replace")
        else:
            text = data
        stamped: list[str] = []
        for chunk in text.splitlines(keepends=True):
            if self._at_line_start:
                stamped.append(f"{_line_stamp()} {chunk}")
            else:
                stamped.append(chunk)
            self._at_line_start = chunk.endswith(("\n", "\r"))
        self._stream.write("".join(stamped))
        return written

    def writelines(self, lines: Iterable[str | bytes]) -> None:
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name: str) -> object:
        return getattr(self._stream, name)
