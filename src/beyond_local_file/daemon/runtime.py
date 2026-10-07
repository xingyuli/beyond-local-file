"""Long-running daemon worker: serve IPC, then catch-up, then live observe."""

from __future__ import annotations

import os
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType

from beyond_local_file.configuration_set import ConfigurationSet
from beyond_local_file.contribution import echo_item_path_overlaps
from beyond_local_file.model.config import ConfigProject
from beyond_local_file.model.translator import translate_config_to_mapping_units
from beyond_local_file.operations.link_check import check, check_concat
from beyond_local_file.operations.result import CheckResult, FailedResult, to_ipc
from beyond_local_file.options import OutputFormat

from .catchup import catch_up_live, run_catch_up
from .handlers import handle_request
from .ingest import prepare_reload
from .ipc import (
    ProgressCallback,
    Request,
    RequestTimes,
    Response,
    ServeLoop,
    WorkerState,
    format_status_line,
    log_request_boundary,
    serve_requests,
)
from .log import (
    RequestLogState,
    bind_persist_samples,
    current_request_state,
    duration_ms,
    log_scope,
    open_worker_logs,
    reset_persist_samples,
)
from .notice import emit_desktop_notices
from .oos_held import list_oos_and_held
from .process import write_ready
from .resolve_ui import ResolveHttp, start_resolve_ui, stop_resolve_ui
from .store import BaselineTrees, load_baseline, load_snapshot, mappings_equal, save_baseline, save_snapshot
from .workers import WorkerUnit, build_worker_units, route_worker_unit

_TEST_HOLD_ENV = "BLF_TEST_CATCHUP_HOLD"
_HOLD_POLL_S = 0.05
_HOLD_TIMEOUT_S = 60.0

type ProgressFn = Callable[[int, int, str], None]


@dataclass
class _ReloadProgress:
    """Per-unit timings and shell-screen lines for one reload."""

    durations: dict[str, int]
    on_line: ProgressCallback | None


@dataclass
class _LiveRuntime:
    config_path: Path
    shutdown: threading.Event
    bound: threading.Event
    state: WorkerState
    units: dict[str, WorkerUnit]
    failed: threading.Event
    resolve_http: ResolveHttp | None = None


def run_worker(config_path: Path) -> int:
    """Bind IPC, catch-up while serving status, then live-observe until stop.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        Process exit code.
    """
    open_worker_logs(ConfigurationSet(config_path).run_directory)
    runtime = _LiveRuntime(
        config_path=config_path,
        shutdown=threading.Event(),
        bound=threading.Event(),
        state=WorkerState(),
        units={},
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
    serve_requests(
        config_path,
        _on_request,
        ServeLoop(shutdown=runtime.shutdown, bound=runtime.bound, state=runtime.state),
    )
    stop_resolve_ui(runtime.resolve_http)
    print("daemon stopping", flush=True)
    return 1 if runtime.failed.is_set() else 0


def _handle_live_request(
    request_config: Path,
    request: Request,
    on_progress: ProgressCallback | None,
    runtime: _LiveRuntime,
) -> Response:
    if request.get("op") == "reload" and runtime.units:
        return _reload_changed_units(request_config, request, runtime, on_progress)
    if request.get("op") == "check" and runtime.units:
        return _fanout_check(request_config, request, on_progress, runtime)
    unit = route_worker_unit(request, runtime.units, request_config)
    if unit is None:
        return _run_direct_request(request_config, request, on_progress)
    scoped = _with_unit(on_progress, unit.name)
    if unit.busy and scoped is not None and request.get("op") in {"create", "restore", "remove"}:
        scoped("Waiting …")
    state = current_request_state()
    return unit.submit(lambda: _run_unit_request(request_config, request, scoped, unit, state))


def _reload_changed_units(
    request_config: Path,
    request: Request,
    runtime: _LiveRuntime,
    on_progress: ProgressCallback | None,
) -> Response:
    state = _claim_request_state()
    enqueued = state.enqueued if state is not None else time.perf_counter()
    dry_run = bool(request.get("dry_run"))
    persist_at_start = None if dry_run else 0
    names: list[str] = []
    durations: dict[str, int] = {}
    response: Response = {"exit_code": 1, "stdout": ""}
    start_logged = False
    with log_scope("requests"):
        queue_ms = duration_ms(enqueued)
        try:
            result = prepare_reload(request_config, confirmed=bool(request.get("confirmed")))
            names = sorted(result.affected)
            started_times = RequestTimes(queue_ms, 0, persist_at_start)
            log_request_boundary("request: start", request, names, started_times)
            start_logged = True
            started = time.perf_counter()
            if result.problem is not None or not result.affected:
                response = to_ipc(result)
            else:
                _reload_units(
                    request_config,
                    runtime,
                    names,
                    _ReloadProgress(durations, on_progress),
                )
                response = to_ipc(result)
            op_ms, persist_ms = _op_and_persist(duration_ms(started), 0, dry_run=dry_run)
        except Exception as error:
            response = {"exit_code": 1, "stdout": f"Error: {error}\n"}
            op_ms, persist_ms = 0, persist_at_start
            if not start_logged:
                log_request_boundary("request: start", request, names, RequestTimes(queue_ms, 0, persist_at_start))
        listed = [f"{name}:{durations.get(name, 0)}" for name in names]
        log_request_boundary(
            "request: done",
            request,
            listed,
            RequestTimes(queue_ms, op_ms, persist_ms, response.get("exit_code")),
        )
    return response


def _reload_units(
    request_config: Path,
    runtime: _LiveRuntime,
    names: list[str],
    progress: _ReloadProgress,
) -> None:
    on_line = progress.on_line
    if on_line is not None:
        for name in names:
            on_line(f"Waiting · {name}")
    snapshot = load_snapshot(request_config) or {}
    present = {project.managed_project_name: project for project in snapshot.values()}
    for name in list(runtime.units):
        if name not in present:
            runtime.units[name].stop()
            del runtime.units[name]
            if on_line is not None and name in names:
                on_line(f"Done · {name}")
    waits = []
    for name in names:
        project = present.get(name)
        if project is None:
            continue
        if name in runtime.units:
            unit = runtime.units[name]
            waits.append(unit.submit_async(lambda current=unit: _timed_catch_up(request_config, current, progress)))
            continue
        subset = {key: item for key, item in snapshot.items() if item.managed_project_name == name}
        _timed_new_unit(request_config, subset, runtime, progress)
    for wait in waits:
        wait()


def _timed_catch_up(config_path: Path, unit: WorkerUnit, progress: _ReloadProgress) -> None:
    started = time.perf_counter()
    try:
        _catch_up_unit(config_path, unit, progress.on_line)
    finally:
        progress.durations[unit.name] = duration_ms(started)


def _timed_new_unit(
    config_path: Path,
    subset: dict[str, ConfigProject],
    runtime: _LiveRuntime,
    progress: _ReloadProgress,
) -> None:
    name = next(iter(subset.values())).managed_project_name if subset else ""
    started = time.perf_counter()
    try:
        _catch_up_new_unit(config_path, subset, runtime, progress.on_line)
    finally:
        if name:
            progress.durations[name] = duration_ms(started)


def _catch_up_unit(config_path: Path, unit: WorkerUnit, on_line: ProgressCallback | None) -> None:
    projects = ConfigurationSet(config_path).projects()
    subset = {key: project for key, project in projects.items() if project.managed_project_name == unit.name}
    if not subset:
        if on_line is not None:
            on_line(f"Done · {unit.name}")
        return
    unit.live.replace_projects(subset)
    trees = catch_up_live(unit.live, started_with_baseline=True, on_line=on_line)
    save_baseline(config_path, trees, subset)


def _catch_up_new_unit(
    config_path: Path,
    subset: dict[str, ConfigProject],
    runtime: _LiveRuntime,
    on_line: ProgressCallback | None,
) -> None:
    name = next(iter(subset.values())).managed_project_name if subset else None
    with log_scope("requests", name):
        trees = run_catch_up(
            subset, ConfigurationSet(config_path).run_directory, load_baseline(config_path), on_line=on_line
        )
        save_baseline(config_path, trees, subset)
        built = build_worker_units(subset, trees, config_path, runtime.shutdown)
        for unit in built.values():
            runtime.units[unit.name] = unit
            unit.start()


def _fanout_check(
    request_config: Path,
    request: Request,
    on_progress: ProgressCallback | None,
    runtime: _LiveRuntime,
) -> Response:
    name = request.get("project_name")
    if name:
        unit = runtime.units.get(str(name))
        if unit is None:
            return _run_direct_request(request_config, request, on_progress)
        selected = [unit]
    else:
        selected = [runtime.units[key] for key in sorted(runtime.units)]
    state = _claim_request_state()
    enqueued = state.enqueued if state is not None else time.perf_counter()
    names = [item.name for item in selected]
    dry_run = bool(request.get("dry_run"))
    persist_at_start = None if dry_run else 0
    fanout = _CheckFanout(
        request_config=request_config,
        request=request,
        on_progress=on_progress,
        total=sum(len(translate_config_to_mapping_units(item.live.projects)) for item in selected),
    )
    if on_progress is not None:
        for unit in selected:
            on_progress(f"Waiting · {unit.name}")
    response: Response = {"exit_code": 1, "stdout": ""}
    with log_scope("requests"):
        queue_ms = duration_ms(enqueued)
        log_request_boundary("request: start", request, names, RequestTimes(queue_ms, 0, persist_at_start))
        started = time.perf_counter()
        try:
            response = _merge_unit_checks(selected, fanout)
        except Exception as error:
            response = {"exit_code": 1, "stdout": f"Error: {error}\n"}
        op_ms, persist_ms = _op_and_persist(duration_ms(started), 0, dry_run=dry_run)
        listed = [f"{unit_name}:{fanout.durations.get(unit_name, 0)}" for unit_name in names]
        log_request_boundary(
            "request: done",
            request,
            listed,
            RequestTimes(queue_ms, op_ms, persist_ms, response.get("exit_code")),
        )
    return response


@dataclass
class _CheckFanout:
    """Shared progress and cancel state for one multi-unit check."""

    request_config: Path
    request: Request
    on_progress: ProgressCallback | None
    total: int
    completed: int = 0
    skipped: list[str] = field(default_factory=list)
    durations: dict[str, int] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)


def _merge_unit_checks(selected: list[WorkerUnit], fanout: _CheckFanout) -> Response:
    waits = [item.submit_async(lambda current=item: _timed_unit_check(current, fanout)) for item in selected]
    parts: list[CheckResult] = []
    for wait in waits:
        parts.append(wait())
    if fanout.skipped and _is_cancelled(fanout.request):
        return to_ipc(FailedResult(1, ("Stopped",)))
    return to_ipc(check_concat(parts))


def _timed_unit_check(unit: WorkerUnit, fanout: _CheckFanout) -> CheckResult:
    job_started = time.perf_counter()
    extra_exclude = bool(fanout.request.get("extra_exclude"))
    output_format = OutputFormat(str(fanout.request.get("output_format") or OutputFormat.TABLE))
    try:
        if _is_cancelled(fanout.request):
            with fanout.lock:
                fanout.skipped.append(unit.name)
            return CheckResult(
                exit_code=0,
                extra_exclude=extra_exclude,
                output_format=output_format,
                rows=(),
                not_found=None,
            )
        try:
            result = check(
                unit.live.projects,
                load_baseline(fanout.request_config),
                extra_exclude=extra_exclude,
                output_format=output_format,
                on_progress=_check_item_progress(unit.name, fanout),
                unit_count=fanout.total,
            )
        except Exception:
            if fanout.on_progress is not None:
                fanout.on_progress(f"Failed · {unit.name}")
            raise
        if fanout.on_progress is not None:
            fanout.on_progress(f"Done · {unit.name}")
        return result
    finally:
        fanout.durations[unit.name] = duration_ms(job_started)


def _check_item_progress(unit_name: str, fanout: _CheckFanout) -> Callable[[int, int, str], None]:
    def on_item(_index: int, _total: int, item: str) -> None:
        with fanout.lock:
            fanout.completed += 1
            index = fanout.completed
        if fanout.on_progress is not None:
            fanout.on_progress(format_status_line("Checking", index, fanout.total, item))
            fanout.on_progress(f"Checking {item} · {unit_name}")

    return on_item


def _run_direct_request(
    request_config: Path,
    request: Request,
    on_progress: ProgressCallback | None,
) -> Response:
    state = _claim_request_state()
    with log_scope("requests"):
        return _finish_request(
            request,
            state,
            units=[],
            body=lambda: _execute_direct(request_config, request, on_progress),
        )


def _run_unit_request(
    request_config: Path,
    request: Request,
    on_progress: ProgressCallback | None,
    unit: WorkerUnit,
    state: RequestLogState | None,
) -> Response:
    return _finish_request(
        request,
        state,
        units=[unit.name],
        body=lambda: _execute_unit_request(request_config, request, on_progress, unit),
    )


def _execute_direct(
    request_config: Path,
    request: Request,
    on_progress: ProgressCallback | None,
) -> Response:
    return handle_request(request_config, request, on_progress=on_progress)


def _execute_unit_request(
    request_config: Path,
    request: Request,
    on_progress: ProgressCallback | None,
    unit: WorkerUnit,
) -> Response:
    if _is_cancelled(request):
        return to_ipc(FailedResult(1, ("Stopped",)))
    op = request.get("op")
    skip_notice = bool(request.get("tty"))
    before = (
        list_oos_and_held(unit.live.baseline, unit.live.projects)
        if op in {"create", "restore", "remove", "reload"}
        else None
    )
    if op in {"create", "restore", "remove"} and on_progress is not None:
        verbs = {"create": "Creating", "restore": "Restoring", "remove": "Removing"}
        item = str(request.get("path") or "").strip()
        on_progress(f"{verbs[str(op)]} … {item}".rstrip())
    if op in {"create", "restore", "remove", "reload"}:
        applied = unit.live.apply()
        if applied:
            save_baseline(request_config, unit.live.baseline, unit.live.projects, changed_rels=applied)
    mutating_shell = op in {"create", "restore", "remove"}
    response = handle_request(
        request_config,
        request,
        on_progress=on_progress,
        previous_trees=unit.live.baseline if mutating_shell else None,
        live=unit.live if mutating_shell else None,
    )
    mutating = mutating_shell and not request.get("dry_run")
    if mutating and response.get("exit_code") == 0:
        snapshot = load_snapshot(request_config)
        if snapshot is not None:
            subset = {key: project for key, project in snapshot.items() if project.managed_project_name == unit.name}
            if subset:
                unit.live.replace_projects(subset)
    if before is not None:
        emit_desktop_notices(
            project=unit.name,
            before=before,
            after=list_oos_and_held(unit.live.baseline, unit.live.projects),
            skip=skip_notice,
        )
    return response


def _claim_request_state() -> RequestLogState | None:
    state = current_request_state()
    if state is not None:
        state.logged = True
    return state


def _op_and_persist(elapsed_ms: int, persisted_ms: int, *, dry_run: bool) -> tuple[int, int | None]:
    if dry_run:
        return elapsed_ms, None
    return max(0, elapsed_ms - persisted_ms), persisted_ms


def _finish_request(
    request: Request,
    state: RequestLogState | None,
    *,
    units: list[str],
    body: Callable[[], Response],
) -> Response:
    if state is not None:
        state.logged = True
    enqueued = state.enqueued if state is not None else time.perf_counter()
    dry_run = bool(request.get("dry_run"))
    persist_at_start = None if dry_run else 0
    queue_ms = duration_ms(enqueued)
    response: Response = {"exit_code": 1, "stdout": ""}
    samples: list[int] = []
    token = bind_persist_samples(samples)
    try:
        log_request_boundary("request: start", request, units, RequestTimes(queue_ms, 0, persist_at_start))
        started = time.perf_counter()
        try:
            response = body()
        except Exception as error:
            response = {"exit_code": 1, "stdout": f"Error: {error}\n"}
        op_ms, persist_ms = _op_and_persist(duration_ms(started), sum(samples), dry_run=dry_run)
        log_request_boundary(
            "request: done",
            request,
            units,
            RequestTimes(queue_ms, op_ms, persist_ms, response.get("exit_code")),
        )
    finally:
        reset_persist_samples(token)
    return response


def _with_unit(on_progress: ProgressCallback | None, project: str) -> ProgressCallback | None:
    """Append the worker-unit name so a shell screen can name the row."""
    if on_progress is None:
        return None

    def emit(line: str) -> None:
        if " · " not in line:
            line = f"{line} · {project}"
        on_progress(line)

    return emit


def _is_cancelled(request: Request) -> bool:
    """Return whether the shell confirmed a stop before this job began."""
    token = request.get("_cancel")
    return isinstance(token, threading.Event) and token.is_set()


def _catch_up_worker(runtime: _LiveRuntime) -> None:
    if not runtime.bound.wait(timeout=10.0):
        runtime.failed.set()
        runtime.shutdown.set()
        return
    try:
        caught = _catch_up_and_persist(runtime.config_path, on_line=runtime.state.emit)
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
    runtime.units.update(build_worker_units(projects, trees, runtime.config_path, runtime.shutdown))
    for unit in runtime.units.values():
        unit.start()
    try:
        runtime.resolve_http = start_resolve_ui(runtime.config_path, apply_resolve=_enqueue_resolve(runtime))
    except OSError as error:
        print(f"resolve UI: failed to bind: {error}", flush=True)
    write_ready(runtime.config_path)
    print("daemon ready", flush=True)
    runtime.state.set_ready()


def _catch_up_and_persist(
    config_path: Path,
    on_progress: ProgressFn | None = None,
    on_line: Callable[[str], None] | None = None,
) -> tuple[dict[str, ConfigProject], BaselineTrees] | None:
    """Catch up committed mappings, or abort when items overlap on a target.

    Args:
        config_path: Path to the loaded config file.
        on_progress: Optional catch-up unit/item callback for IPC status lines.
        on_line: Optional shell-screen progress line.

    Returns:
        Projects and baseline trees, or None when start must not continue.
    """
    file_projects = ConfigurationSet(config_path).projects()
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
        ConfigurationSet(config_path).run_directory,
        load_baseline(config_path),
        on_progress=on_progress,
        on_line=on_line,
    )
    save_snapshot(config_path, projects)
    save_baseline(config_path, trees, projects)
    _await_test_hold()
    return projects, trees


def _enqueue_resolve(runtime: _LiveRuntime) -> Callable[[str, str, bytes], dict]:
    """Return a callback that runs resolve as a job on the owning worker unit."""

    def apply_resolve(project: str, rel: str, content: bytes) -> dict:
        unit = runtime.units.get(project)
        if unit is None:
            return {"ok": False, "error": "worker unit cannot take the op"}
        try:
            unit.submit(lambda: _run_resolve(runtime.config_path, unit, rel, content))
        except Exception as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "applied": True}

    return apply_resolve


def _run_resolve(config_path: Path, unit: WorkerUnit, rel: str, content: bytes) -> None:
    unit.live.resolve(rel, content)
    save_baseline(config_path, unit.live.baseline, unit.live.projects, changed_rels=[rel])


def _await_test_hold() -> None:
    raw = os.environ.get(_TEST_HOLD_ENV)
    if not raw:
        return
    path = Path(raw)
    deadline = time.monotonic() + _HOLD_TIMEOUT_S
    while path.exists() and time.monotonic() < deadline:
        time.sleep(_HOLD_POLL_S)
