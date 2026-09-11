"""Long-running daemon worker: catch-up, then idle until stop."""

from __future__ import annotations

import signal
import threading
from pathlib import Path
from types import FrameType

from beyond_local_file.config import Config

from .catchup import run_catch_up
from .process import write_ready
from .store import load_baseline, load_snapshot, mappings_equal, save_baseline, save_snapshot


def run_worker(config_path: Path) -> int:
    """Catch-up copy projections, then idle until SIGTERM/SIGINT.

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
    _catch_up_and_persist(config_path)
    write_ready(config_path)
    print("daemon ready", flush=True)
    while not shutdown.is_set():
        shutdown.wait(timeout=0.25)
    print("daemon stopping", flush=True)
    return 0


def _catch_up_and_persist(config_path: Path) -> None:
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
