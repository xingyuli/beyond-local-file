"""Dispatch shell requests to copy-only operations inside the daemon."""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import click

from beyond_local_file.configuration_set import ConfigurationSet
from beyond_local_file.model.config import ConfigProject
from beyond_local_file.operations.link_check import check
from beyond_local_file.operations.remove import RemoveFormatter, RemoveOperation
from beyond_local_file.operations.result import CheckResult, FailedResult, to_ipc
from beyond_local_file.operations.revlink import (
    CreateFormatter,
    CreateOperation,
    RestoreFormatter,
    RestoreOperation,
    RevlinkContext,
)
from beyond_local_file.options import OutputFormat
from beyond_local_file.project_processor import (
    RevlinkResolveError,
    resolve_revlink_context,
)

from .catchup import record_baseline, record_item_baseline
from .ingest import commit_reload
from .ipc import ProgressCallback, Request, Response, format_status_line
from .live import LiveSync
from .log import log_duration, note_persist_ms
from .store import BaselineTrees, load_baseline, load_snapshot, save_baseline, save_snapshot

type Handler = Callable[[Path, Request], int]


def handle_request(
    config_path: Path,
    request: Request,
    on_progress: ProgressCallback | None = None,
    previous_trees: BaselineTrees | None = None,
    live: LiveSync | None = None,
) -> Response:
    """Run one daemon request and capture its stdout.

    Args:
        config_path: Path to the loaded config file.
        request: JSON request from a shell.
        on_progress: Optional callback for streamed status lines.
        previous_trees: In-memory baseline to keep when persisting a mutating
            shell. When omitted, persist loads the on-disk baseline.
        live: Worker-unit observer. Create splices yaml then names item-add
            on this LiveSync. Restore and remove name the disk job then splice
            the yaml drop. When omitted, mutating shells build a throwaway observer.

    Returns:
        A check or failed envelope, or ``exit_code`` and captured ``stdout``
        for mutating ops that still print.
    """
    op = request.get("op")
    created: dict[str, LiveSync] = {}
    if live is not None:
        created["live"] = live
    if op == "check":
        return _handle_check(config_path, request, on_progress)
    dispatch: dict[str, Handler] = {
        "create": lambda path, req: _handle_create(path, req, created),
        "restore": lambda path, req: _handle_restore(path, req, created),
        "remove": lambda path, req: _handle_remove(path, req, created),
        "reload": _handle_reload,
    }
    handler = dispatch.get(str(op) if op is not None else "")
    if handler is None:
        return to_ipc(FailedResult(1, (f"Error: unknown daemon operation {op!r}",)))

    buffer = StringIO()
    with redirect_stdout(buffer):
        exit_code = handler(config_path, request)
        if exit_code == 0 and op in {"create", "restore", "remove"} and not request.get("dry_run"):
            try:
                if on_progress is not None:
                    on_progress("Writing baseline …")
                changed_rel = request.get("path")
                rel = str(changed_rel) if changed_rel else None
                observer = created.get("live")
                if observer is not None:
                    _persist_live_state(config_path, observer, changed_rel=rel)
                else:
                    _persist_committed_state(
                        config_path,
                        changed_rel=rel,
                        previous=previous_trees,
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
) -> Response:
    projects = load_snapshot(config_path)
    if projects is None:
        projects = ConfigurationSet(config_path).projects()
    extra_exclude = bool(request.get("extra_exclude"))
    output_format = OutputFormat(str(request.get("output_format") or OutputFormat.TABLE))
    project_name = request.get("project_name")
    if project_name:
        projects = {key: project for key, project in projects.items() if project.managed_project_name == project_name}
        if not projects:
            return to_ipc(
                CheckResult(
                    exit_code=1,
                    extra_exclude=extra_exclude,
                    output_format=output_format,
                    rows=(),
                    not_found=f"Project '{project_name}' not found in config",
                )
            )

    def emit_item(index: int, total: int, item: str) -> None:
        if on_progress is None:
            return
        on_progress(format_status_line("Checking", index, total, item))

    return to_ipc(
        check(
            projects,
            load_baseline(config_path),
            extra_exclude=extra_exclude,
            output_format=output_format,
            on_progress=emit_item,
        )
    )


def _handle_create(config_path: Path, request: Request, created: dict[str, LiveSync]) -> int:
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
    code = CreateOperation(
        source=source,
        dest_root=dest_root,
        rel_path=rel_path,
        dry_run=dry_run,
        force=bool(request.get("force")),
        formatter=CreateFormatter(dry_run=dry_run),
        context=context,
    ).run()
    if code != 0 or dry_run:
        return code
    observer, subset = _observer_for(config_path, created, context)
    if subset:
        observer.replace_projects(subset)
    observer.install_item(cwd, rel_path.as_posix())
    return 0


def _handle_restore(config_path: Path, request: Request, created: dict[str, LiveSync]) -> int:
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
    operation = RestoreOperation(
        source=source,
        dest_root=dest_root,
        rel_path=rel_path,
        dry_run=dry_run,
        formatter=RestoreFormatter(dry_run=dry_run),
        context=context,
    )
    code = operation.run()
    if code != 0 or dry_run:
        return code
    observer, subset = _observer_for(config_path, created, context)
    if subset:
        observer.replace_projects(subset)
    observer.restore_item(cwd, rel_path.as_posix())
    operation.drop_mapping()
    return _replace_after_mapping_drop(config_path, created, context)


def _handle_remove(config_path: Path, request: Request, created: dict[str, LiveSync]) -> int:
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
    operation = RemoveOperation(
        source=source,
        rel_path=rel_path,
        dry_run=dry_run,
        formatter=RemoveFormatter(dry_run=dry_run),
        context=context,
    )
    code = operation.run()
    if code != 0 or dry_run:
        return code
    observer, subset = _observer_for(config_path, created, context)
    if subset:
        observer.replace_projects(subset)
    observer.remove_item(cwd, rel_path.as_posix())
    code = operation.drop_mapping()
    if code != 0:
        return code
    return _replace_after_mapping_drop(config_path, created, context)


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


def _observer_for(
    config_path: Path,
    created: dict[str, LiveSync],
    context: RevlinkContext,
) -> tuple[LiveSync, dict[str, ConfigProject]]:
    """Return the worker LiveSync, or a throwaway observer for this project.

    Args:
        config_path: Path to the loaded config file.
        created: Handler-scoped LiveSync slot, filled when the worker omitted one.
        context: Resolved project for this request.

    Returns:
        Observer and the committed mappings for this managed project.
    """
    projects = ConfigurationSet(config_path).projects()
    subset = {key: project for key, project in projects.items() if project.managed_project_name == context.project_name}
    observer = created.get("live")
    if observer is None:
        trees = load_baseline(config_path) or {}
        observer = LiveSync(subset or projects, trees, last_seen_from_baseline=True)
        created["live"] = observer
    return observer, subset


def _replace_after_mapping_drop(
    config_path: Path,
    created: dict[str, LiveSync],
    context: RevlinkContext,
) -> int:
    """Rebuild watch roots after restore/remove spliced the mapping yaml drop.

    Args:
        config_path: Path to the loaded config file.
        created: Handler-scoped LiveSync slot.
        context: Resolved project for this request.

    Returns:
        Zero after watch roots match the new mappings.
    """
    observer = created.get("live")
    if observer is None:
        return 0
    projects = ConfigurationSet(config_path).projects()
    subset = {key: project for key, project in projects.items() if project.managed_project_name == context.project_name}
    if subset:
        observer.replace_projects(subset)
    return 0


def _persist_live_state(config_path: Path, live: LiveSync, changed_rel: str | None) -> None:
    """Persist snapshot and LiveSync baseline after a named mutating job."""
    with log_duration("persist: done") as fields:
        projects = ConfigurationSet(config_path).projects()
        save_snapshot(config_path, projects)
        rels = [changed_rel] if changed_rel else None
        save_baseline(config_path, live.baseline, projects, changed_rels=rels)
    elapsed = fields.get("duration_ms")
    if isinstance(elapsed, int):
        note_persist_ms(elapsed)


def _persist_committed_state(
    config_path: Path,
    changed_rel: str | None = None,
    previous: BaselineTrees | None = None,
) -> None:
    with log_duration("persist: done") as fields:
        projects = ConfigurationSet(config_path).projects()
        save_snapshot(config_path, projects)
        if previous is None:
            previous = load_baseline(config_path)
        if changed_rel:
            trees = record_item_baseline(projects, previous, changed_rel)
            save_baseline(config_path, trees, projects, changed_rels=[changed_rel])
        else:
            trees = record_baseline(projects, previous)
            save_baseline(config_path, trees, projects)
    elapsed = fields.get("duration_ms")
    if isinstance(elapsed, int):
        note_persist_ms(elapsed)
