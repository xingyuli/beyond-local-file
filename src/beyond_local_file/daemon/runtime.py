"""Long-running daemon worker: catch-up, then serve shell requests until stop."""

from __future__ import annotations

import signal
import sys
import threading
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import TextIO

from beyond_local_file.config import Config
from beyond_local_file.contribution import echo_item_path_overlaps
from beyond_local_file.model.config import ConfigProject

from .catchup import run_catch_up
from .handlers import handle_request
from .ipc import Request, Response, serve_requests
from .live import LiveSync
from .store import BaselineTrees, load_baseline, load_snapshot, mappings_equal, save_baseline, save_snapshot


def run_worker(config_path: Path) -> int:
    """Catch-up copy projections, then serve requests until SIGTERM/SIGINT.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        Process exit code.
    """
    _stamp_worker_streams()
    shutdown = threading.Event()

    def _handle(signum: int, frame: FrameType | None) -> None:
        del signum, frame
        shutdown.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)

    print("daemon worker starting", flush=True)
    caught = _catch_up_and_persist(config_path)
    if caught is None:
        return 1
    projects, trees = caught
    live = LiveSync(projects, trees)

    def _tick() -> None:
        if live.tick():
            save_baseline(config_path, live.baseline)

    def _handle_request(request_config: Path, request: Request) -> Response:
        response = handle_request(request_config, request)
        mutating = request.get("op") in {"create", "restore", "remove", "reload"} and not request.get("dry_run")
        if mutating and response.get("exit_code") == 0:
            snapshot = load_snapshot(request_config)
            baseline = load_baseline(request_config)
            if snapshot is not None and baseline is not None:
                live.reload(snapshot, baseline)
        return response

    serve_requests(config_path, _handle_request, shutdown, on_idle=_tick, before_request=_tick)
    print("daemon stopping", flush=True)
    return 0


def _catch_up_and_persist(
    config_path: Path,
) -> tuple[dict[str, ConfigProject], BaselineTrees] | None:
    """Catch up committed mappings, or abort when items overlap on a target.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        Projects and baseline trees, or None when start must not continue.
    """
    cfg = Config(config_path)
    cfg.load()
    file_projects = cfg.get_config_projects()
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

    trees = run_catch_up(projects, config_path.parent, load_baseline(config_path))
    save_baseline(config_path, trees)
    save_snapshot(config_path, projects)
    return projects, trees


def _stamp_worker_streams() -> None:
    """Prefix each new stdout and stderr line with the host local time and offset."""
    sys.stdout = _TimestampedStream(sys.stdout)
    sys.stderr = _TimestampedStream(sys.stderr)


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
