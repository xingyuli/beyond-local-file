"""Long-running daemon worker: catch-up, then serve shell requests until stop."""

from __future__ import annotations

import signal
import threading
from pathlib import Path
from types import FrameType

from beyond_local_file.config import Config
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
    shutdown = threading.Event()

    def _handle(signum: int, frame: FrameType | None) -> None:
        del signum, frame
        shutdown.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)

    print("daemon worker starting", flush=True)
    projects, trees = _catch_up_and_persist(config_path)
    live = LiveSync(projects, trees)

    def _tick() -> None:
        if live.tick():
            save_baseline(config_path, live.baseline)

    def _handle_request(request_config: Path, request: Request) -> Response:
        response = handle_request(request_config, request)
        mutating = request.get("op") in {"create", "restore", "remove"} and not request.get("dry_run")
        if mutating:
            snapshot = load_snapshot(request_config)
            baseline = load_baseline(request_config)
            if snapshot is not None and baseline is not None:
                live.reload(snapshot, baseline)
        return response

    serve_requests(config_path, _handle_request, shutdown, on_idle=_tick, before_request=_tick)
    print("daemon stopping", flush=True)
    return 0


def _catch_up_and_persist(config_path: Path) -> tuple[dict[str, ConfigProject], BaselineTrees]:
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
            "config file differs from mapping snapshot; YAML ingest is not implemented; starting from snapshot",
            flush=True,
        )
    else:
        projects = file_projects
        print("catch-up: mapping snapshot matches config file", flush=True)

    trees = run_catch_up(projects, config_path.parent, load_baseline(config_path))
    save_baseline(config_path, trees)
    save_snapshot(config_path, projects)
    return projects, trees
