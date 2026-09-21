"""One worker unit per managed project: a queue, a live observer, and idle observe."""

from __future__ import annotations

import os
import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from beyond_local_file.contribution import contribution_owner, projects_targeting
from beyond_local_file.model.config import ConfigProject

from .live import LiveSync
from .store import BaselineTrees, load_snapshot, save_baseline

IDLE_OBSERVE_S = 15.0
_TEST_IDLE_HOLD_ENV = "BLF_TEST_IDLE_HOLD"
_TEST_IDLE_HOLD_PROJECT_ENV = "BLF_TEST_IDLE_HOLD_PROJECT"
_HOLD_POLL_S = 0.05
_HOLD_TIMEOUT_S = 60.0

type Job = Callable[[], None]
T = TypeVar("T")


class WorkerUnit:
    """Queue and live observer for one managed project (hub and every target)."""

    def __init__(
        self,
        name: str,
        live: LiveSync,
        config_path: Path,
        shutdown: threading.Event,
        offset: float,
    ) -> None:
        self.name = name
        self.live = live
        self.config_path = config_path
        self.shutdown = shutdown
        self.offset = offset
        self._jobs: queue.Queue[Job | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, name=f"blf-unit-{name}", daemon=True)

    def start(self) -> None:
        """Start the unit thread."""
        self._thread.start()

    def submit(self, fn: Callable[[], T]) -> T:
        """Run *fn* on this unit's thread and return its result.

        Args:
            fn: Work that must not run concurrently with this unit's observe.

        Returns:
            The return value of *fn*.

        Raises:
            Exception: Propagates whatever *fn* raises.
        """
        return self.submit_async(fn)()

    def submit_async(self, fn: Callable[[], T]) -> Callable[[], T]:
        """Queue *fn* on this unit and return a waiter for its result.

        Args:
            fn: Work that must not run concurrently with this unit's observe.

        Returns:
            A callable that blocks until *fn* finishes and returns its value.
        """
        done = threading.Event()
        slot: dict[str, object] = {}

        def job() -> None:
            try:
                slot["value"] = fn()
            except Exception as error:
                slot["error"] = error
            finally:
                done.set()

        self._jobs.put(job)

        def wait() -> T:
            done.wait()
            error = slot.get("error")
            if isinstance(error, Exception):
                raise error
            return slot["value"]  # type: ignore[return-value]

        return wait

    def _run(self) -> None:
        next_idle = time.monotonic() + self.offset
        while not self.shutdown.is_set():
            timeout = max(0.0, next_idle - time.monotonic())
            try:
                job = self._jobs.get(timeout=timeout)
            except queue.Empty:
                self._idle()
                next_idle = time.monotonic() + idle_observe_s()
                continue
            if job is None:
                return
            job()

    def _idle(self) -> None:
        await_idle_hold(self.name)
        if self.live.tick(reason="idle"):
            save_baseline(self.config_path, self.live.baseline, self.live.projects)


def build_worker_units(
    projects: dict[str, ConfigProject],
    trees: BaselineTrees,
    config_path: Path,
    shutdown: threading.Event,
) -> dict[str, WorkerUnit]:
    """Build one worker unit per managed project.

    Args:
        projects: Committed mappings.
        trees: Catch-up baseline for the whole set.
        config_path: Set identity path for persist.
        shutdown: Event that stops unit threads.

    Returns:
        Units keyed by managed project name.
    """
    by_name: dict[str, ConfigProject] = {}
    for project in projects.values():
        by_name[project.managed_project_name] = project
    names = sorted(by_name)
    interval = idle_observe_s()
    units: dict[str, WorkerUnit] = {}
    for index, name in enumerate(names):
        project = by_name[name]
        subset = {key: item for key, item in projects.items() if item.managed_project_name == name}
        live = LiveSync(subset, trees_for_project(project, trees))
        offset = 0.0 if len(names) == 1 else index * interval / len(names)
        units[name] = WorkerUnit(name, live, config_path, shutdown, offset)
    return units


def trees_for_project(project: ConfigProject, trees: BaselineTrees) -> BaselineTrees:
    """Return baseline trees for one managed project's hub and targets.

    Args:
        project: The managed project.
        trees: Set-wide baseline.

    Returns:
        Trees keyed by that project's replica roots.
    """
    roots = {str(project.managed_project_path)}
    for mapping in project.mappings:
        roots.update(str(target) for target in mapping.targets)
    return {root: dict(paths) for root, paths in trees.items() if root in roots}


def route_worker_unit(request: dict[str, object], units: dict[str, WorkerUnit], config_path: Path) -> WorkerUnit | None:
    """Return the worker unit that should run *request*, or None.

    Args:
        request: Daemon IPC request.
        units: Units keyed by managed project name.
        config_path: Set identity path for the mapping snapshot.

    Returns:
        The owning unit, or None when the request is not bound to one project.
    """
    if not units:
        return None
    name = request.get("project_name")
    if isinstance(name, str) and name in units:
        return units[name]
    op = request.get("op")
    if op not in {"create", "restore", "remove"}:
        return None
    cwd = Path(str(request.get("cwd") or "")).resolve()
    rel = str(request.get("path") or "")
    snapshot = load_snapshot(config_path) or {}
    owner = contribution_owner(snapshot, cwd, rel)
    if owner is not None and owner.managed_project_name in units:
        return units[owner.managed_project_name]
    matches = projects_targeting(snapshot, cwd)
    if len(matches) == 1 and matches[0].managed_project_name in units:
        return units[matches[0].managed_project_name]
    return None


def idle_observe_s() -> float:
    """Return the idle-observe interval in seconds."""
    raw = os.environ.get("BLF_IDLE_OBSERVE_S")
    if not raw:
        return IDLE_OBSERVE_S
    try:
        return max(0.0, float(raw))
    except ValueError:
        return IDLE_OBSERVE_S


def await_idle_hold(project_name: str) -> None:
    """Block when a test hold file exists for this worker unit.

    Args:
        project_name: Managed project name of the unit that is about to observe.
    """
    raw = os.environ.get(_TEST_IDLE_HOLD_ENV)
    if not raw:
        return
    wanted = os.environ.get(_TEST_IDLE_HOLD_PROJECT_ENV)
    if wanted and wanted != project_name:
        return
    path = Path(raw)
    Path(str(path) + ".entered").write_text("1", encoding="utf-8")
    deadline = time.monotonic() + _HOLD_TIMEOUT_S
    while path.exists() and time.monotonic() < deadline:
        time.sleep(_HOLD_POLL_S)
