"""Dispatch shell requests to copy-only operations inside the daemon."""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import click

from beyond_local_file.model.config import ConfigProject
from beyond_local_file.model.translator import translate_config_to_processing
from beyond_local_file.operations.link_check import CheckOperation, ProcessingUnitResults
from beyond_local_file.operations.remove import RemoveFormatter, RemoveOperation
from beyond_local_file.operations.revlink import (
    CreateFormatter,
    CreateOperation,
    RestoreFormatter,
    RestoreOperation,
    RevlinkContext,
)
from beyond_local_file.options import OutputFormat
from beyond_local_file.project_processor import (
    ProjectProcessor,
    RevlinkResolveError,
    load_set_projects,
    resolve_revlink_context,
)

from .catchup import record_baseline, record_item_baseline
from .ingest import commit_reload
from .ipc import ProgressCallback, Request, Response, format_status_line
from .log import log_duration
from .process import state_dir
from .store import load_baseline, load_snapshot, save_baseline, save_snapshot

type Handler = Callable[[Path, Request], int]


def handle_request(
    config_path: Path,
    request: Request,
    on_progress: ProgressCallback | None = None,
) -> Response:
    """Run one daemon request and capture its stdout.

    Args:
        config_path: Path to the loaded config file.
        request: JSON request from a shell.
        on_progress: Optional callback for streamed status lines.

    Returns:
        ``exit_code`` and captured ``stdout``.
    """
    op = request.get("op")
    dispatch: dict[str, Handler] = {
        "check": lambda path, req: _handle_check(path, req, on_progress),
        "create": _handle_create,
        "restore": _handle_restore,
        "remove": _handle_remove,
        "reload": _handle_reload,
    }
    handler = dispatch.get(str(op) if op is not None else "")
    if handler is None:
        return {"exit_code": 1, "stdout": f"Error: unknown daemon operation {op!r}\n"}

    buffer = StringIO()
    with redirect_stdout(buffer):
        exit_code = handler(config_path, request)
        if exit_code == 0 and op in {"create", "restore", "remove"} and not request.get("dry_run"):
            try:
                if on_progress is not None:
                    on_progress("Writing baseline …")
                changed_rel = request.get("path")
                _persist_committed_state(
                    config_path,
                    changed_rel=str(changed_rel) if changed_rel else None,
                )
            except Exception as error:
                click.echo(f"Warning: could not persist mapping snapshot: {error}")
    return {"exit_code": exit_code, "stdout": buffer.getvalue()}


def _handle_reload(config_path: Path, request: Request) -> int:
    return commit_reload(config_path, confirmed=bool(request.get("confirmed")))


def _handle_check(
    config_path: Path,
    request: Request,
    on_progress: ProgressCallback | None = None,
) -> int:
    projects = load_snapshot(config_path)
    if projects is None:
        projects = load_set_projects(config_path)
    project_name = request.get("project_name")
    if project_name:
        projects = {key: project for key, project in projects.items() if project.managed_project_name == project_name}
        if not projects:
            click.echo(f"Project '{project_name}' not found in config")
            return 1
    extra_exclude = bool(request.get("extra_exclude"))
    output_format = OutputFormat(str(request.get("output_format") or OutputFormat.TABLE))
    units = translate_config_to_processing(projects)

    def emit_item(index: int, total: int, item: str) -> None:
        if on_progress is None:
            return
        on_progress(format_status_line("Checking", index, total, item))

    operation = CheckOperation(state_dir(config_path), extra_exclude, output_format)
    operation.baseline = load_baseline(config_path)
    operation.on_progress = emit_item
    operation.unit_count = len(units)
    ProjectProcessor.process_all_units(projects, operation)
    operation.render()
    return 0


def collect_check_results(
    config_path: Path,
    projects: dict[str, ConfigProject],
    request: Request,
    on_item: Callable[[int, int, str], None] | None,
    unit_count: int,
) -> tuple[list[ProcessingUnitResults], str]:
    """Check *projects* and return mapping-unit rows plus captured stdout.

    Args:
        config_path: Set identity path.
        projects: Managed projects this worker unit should check.
        request: Original check request (format and extra-exclude flags).
        on_item: Optional ``(index, total, item)`` progress callback.
        unit_count: Mapping-unit total for progress (set-wide when fan-out).

    Returns:
        Collected rows and any verbose stdout printed during the check.
    """
    extra_exclude = bool(request.get("extra_exclude"))
    output_format = OutputFormat(str(request.get("output_format") or OutputFormat.TABLE))
    _mark_check_started(projects)
    buffer = StringIO()
    with redirect_stdout(buffer):
        operation = CheckOperation(state_dir(config_path), extra_exclude, output_format)
        operation.baseline = load_baseline(config_path)
        operation.on_progress = on_item
        operation.unit_count = unit_count
        ProjectProcessor.process_all_units(projects, operation)
    return operation.results, buffer.getvalue()


def render_check_results(results: list[ProcessingUnitResults], request: Request) -> str:
    """Render merged check rows as the final table.

    Args:
        results: Rows from every worker unit.
        request: Original check request (format and extra-exclude flags).

    Returns:
        Table stdout, or empty when the format is verbose (already printed).
    """
    extra_exclude = bool(request.get("extra_exclude"))
    output_format = OutputFormat(str(request.get("output_format") or OutputFormat.TABLE))
    if output_format == OutputFormat.VERBOSE or not results:
        return ""
    operation = CheckOperation(Path("."), extra_exclude, output_format)
    operation.extend_results(results)
    buffer = StringIO()
    with redirect_stdout(buffer):
        operation.render()
    return buffer.getvalue()


def _mark_check_started(projects: dict[str, ConfigProject]) -> None:
    raw = os.environ.get("BLF_TEST_CHECK_STARTED")
    if not raw:
        return
    root = Path(raw)
    root.mkdir(parents=True, exist_ok=True)
    for project in projects.values():
        (root / project.managed_project_name).write_text("1", encoding="utf-8")


def _handle_create(config_path: Path, request: Request) -> int:
    cwd, path = _cwd_and_path(request)
    source = Path(path)
    source = source if source.is_absolute() else cwd / source
    source = source.resolve()
    rel_path = _rel_path_or_error(source, cwd, path)
    if isinstance(rel_path, int):
        return rel_path
    project_name = request.get("project_name")
    context = _resolve_context(
        config_path,
        cwd,
        project_name=str(project_name) if project_name else None,
    )
    if isinstance(context, int):
        return context
    dry_run = bool(request.get("dry_run"))
    dest_root = context.managed_project_path
    if dest_root is None:
        click.echo("Error: managed project path is missing")
        return 1
    return CreateOperation(
        source=source,
        dest_root=dest_root,
        rel_path=rel_path,
        dry_run=dry_run,
        force=bool(request.get("force")),
        formatter=CreateFormatter(dry_run=dry_run),
        context=context,
    ).run()


def _handle_restore(config_path: Path, request: Request) -> int:
    cwd, path = _cwd_and_path(request)
    source = (cwd / path).absolute()
    rel_path = _rel_path_or_error(source, cwd, path)
    if isinstance(rel_path, int):
        return rel_path
    context = _resolve_context(config_path, cwd, rel_path=rel_path)
    if isinstance(context, int):
        return context
    dest_root = context.managed_project_path
    if dest_root is None:
        click.echo("Error: managed project path is missing")
        return 1
    dry_run = bool(request.get("dry_run"))
    return RestoreOperation(
        source=source,
        dest_root=dest_root,
        rel_path=rel_path,
        dry_run=dry_run,
        formatter=RestoreFormatter(dry_run=dry_run),
        context=context,
    ).run()


def _handle_remove(config_path: Path, request: Request) -> int:
    cwd, path = _cwd_and_path(request)
    candidate = Path(path)
    candidate = candidate if candidate.is_absolute() else cwd / candidate
    source = Path(os.path.normpath(candidate))
    rel_path = _rel_path_or_error(source, cwd, path)
    if isinstance(rel_path, int):
        return rel_path
    context = _resolve_context(config_path, cwd, rel_path=rel_path)
    if isinstance(context, int):
        return context
    dry_run = bool(request.get("dry_run"))
    return RemoveOperation(
        source=source,
        rel_path=rel_path,
        dry_run=dry_run,
        formatter=RemoveFormatter(dry_run=dry_run),
        context=context,
    ).run()


def _cwd_and_path(request: Request) -> tuple[Path, str]:
    cwd = Path(str(request.get("cwd") or "")).resolve()
    path = str(request.get("path") or "")
    return cwd, path


def _rel_path_or_error(source: Path, cwd: Path, path: str) -> Path | int:
    try:
        return source.relative_to(cwd)
    except ValueError:
        click.echo(f"Error: PATH must be inside the current directory: {path}")
        return 1


def _resolve_context(
    config_path: Path,
    cwd: Path,
    *,
    project_name: str | None = None,
    rel_path: str | Path | None = None,
) -> RevlinkContext | int:
    result = resolve_revlink_context(
        str(config_path),
        cwd,
        project_name=project_name,
        rel_path=rel_path,
    )
    if isinstance(result, RevlinkResolveError):
        if result.message is not None:
            click.echo(result.message)
        return result.exit_code
    return result


def _persist_committed_state(config_path: Path, changed_rel: str | None = None) -> None:
    with log_duration("persist: done"):
        projects = load_set_projects(config_path)
        save_snapshot(config_path, projects)
        previous = load_baseline(config_path)
        if changed_rel:
            trees = record_item_baseline(projects, previous, changed_rel)
            save_baseline(config_path, trees, projects, changed_rels=[changed_rel])
            return
        trees = record_baseline(projects, previous)
        save_baseline(config_path, trees, projects)
