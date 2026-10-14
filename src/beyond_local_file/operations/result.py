"""Structured results returned by daemon operations over IPC."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from beyond_local_file.contribution import ItemOverlap, format_item_overlap
from beyond_local_file.options import OutputFormat

if TYPE_CHECKING:
    from .link_check import GitExcludeStatus, LinkCheckResult

type CheckSkip = Literal["missing_project", "missing_target"]


@dataclass(frozen=True)
class FailedResult:
    """A request that did not complete, with the lines the shell prints.

    Request-lifecycle, not a create. The exit code is the process status
    the shell returns, not a classified error.
    """

    exit_code: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class CheckRow:
    """One mapping-unit row from check, including skipped directories."""

    project_name: str
    target_path: str
    skip: CheckSkip | None
    copy: LinkCheckResult | None
    git: GitExcludeStatus | None


@dataclass(frozen=True)
class CheckResult:
    """Check findings for a configuration set, ready to render or send over IPC."""

    exit_code: int
    extra_exclude: bool
    output_format: OutputFormat
    rows: tuple[CheckRow, ...]
    not_found: str | None


type GitExcludeAction = Literal["added", "exists"]
type RestoreGitExcludeStatus = Literal["removed", "not_found"]
type RemoveArtifactKind = Literal["copy", "symlink"]
type RemoveConfigStatus = Literal["updated", "skipped", "repair"]
type ReloadProblem = Literal["snapshot_missing", "overlap", "missing_hub", "unconfirmed"]


@dataclass(frozen=True)
class CreateResult:
    """Create plan and yaml-splice outcome, ready to render or send over IPC."""

    exit_code: int
    dry_run: bool
    errors: tuple[str, ...]
    already_managed: str | None
    force_overwrite: str | None
    source: str
    dest: str
    git_excludes: tuple[tuple[str, str, GitExcludeAction], ...] = ()
    fan_out: tuple[tuple[str, str], ...] = ()
    holds: tuple[tuple[str, str], ...] = ()
    config_entry: str | None = None
    persist_warning: str | None = None


@dataclass(frozen=True)
class RestoreResult:
    """Restore plan and yaml-drop outcome, ready to render or send over IPC."""

    exit_code: int
    dry_run: bool
    errors: tuple[str, ...]
    leftover_symlink: bool
    source: str
    managed: str
    replica_deletes: tuple[str, ...]
    git_excludes: tuple[tuple[str, RestoreGitExcludeStatus], ...] = ()
    holds: tuple[tuple[str, str], ...] = ()
    config_removed: str | None = None
    persist_warning: str | None = None


@dataclass(frozen=True)
class RemoveResult:
    """Remove plan and yaml-drop outcome, ready to render or send over IPC."""

    exit_code: int
    dry_run: bool
    errors: tuple[str, ...]
    artifacts: tuple[tuple[str, RemoveArtifactKind | None, bool], ...]
    excludes: tuple[tuple[str, str, bool], ...]
    managed_copy: str
    config: RemoveConfigStatus | None = None
    config_path: str | None = None
    config_entry: str | None = None
    holds: tuple[tuple[str, str], ...] = ()
    persist_warning: str | None = None


@dataclass(frozen=True)
class ReloadResult:
    """Reload snapshot outcome, ready to render or send over IPC."""

    exit_code: int
    affected: tuple[str, ...]
    problem: ReloadProblem | None
    overlaps: tuple[ItemOverlap, ...]
    missing_hubs: tuple[str, ...]


type OpResult = FailedResult | CheckResult | CreateResult | RestoreResult | RemoveResult | ReloadResult

_CHECK_SKIPS = frozenset({"missing_project", "missing_target"})
_GIT_EXCLUDE_ACTIONS = frozenset({"added", "exists"})
_RESTORE_GIT_STATUSES = frozenset({"removed", "not_found"})
_REMOVE_ARTIFACT_KINDS = frozenset({"copy", "symlink"})
_REMOVE_CONFIG_STATUSES = frozenset({"updated", "skipped", "repair"})
_RELOAD_PROBLEMS = frozenset({"snapshot_missing", "overlap", "missing_hub", "unconfirmed"})
_KIND_ENVELOPES = frozenset({"failed", "check", "create", "restore", "remove", "reload"})


def to_ipc(result: OpResult) -> dict[str, Any]:
    """Return the IPC payload for *result*.

    Args:
        result: Operation result to send to the shell.

    Returns:
        JSON-serialisable envelope with ``kind`` and the result fields.
    """
    if isinstance(result, CheckResult):
        return _check_to_ipc(result)
    if isinstance(result, CreateResult):
        return _create_to_ipc(result)
    if isinstance(result, RestoreResult):
        return _restore_to_ipc(result)
    if isinstance(result, RemoveResult):
        return _remove_to_ipc(result)
    if isinstance(result, ReloadResult):
        return _reload_to_ipc(result)
    return {
        "exit_code": result.exit_code,
        "kind": "failed",
        "lines": list(result.lines),
    }


def from_ipc(payload: dict[str, Any]) -> OpResult:
    """Return the operation result carried in *payload*.

    Args:
        payload: Daemon IPC response.

    Returns:
        The failed, check, create, restore, remove, or reload result matching ``kind``.

    Raises:
        ValueError: If *payload* is not a known operation result.
    """
    kind = payload.get("kind")
    if kind == "check":
        return _check_from_ipc(payload)
    if kind == "create":
        return _create_from_ipc(payload)
    if kind == "restore":
        return _restore_from_ipc(payload)
    if kind == "remove":
        return _remove_from_ipc(payload)
    if kind == "reload":
        return _reload_from_ipc(payload)
    if kind != "failed":
        raise ValueError("expected failed operation result")
    raw_lines = payload.get("lines", ())
    if not isinstance(raw_lines, list | tuple):
        raise ValueError("failed operation result needs lines")
    raw_code = payload.get("exit_code", 1)
    if not isinstance(raw_code, int):
        raise ValueError("failed operation result needs an exit_code")
    return FailedResult(raw_code, tuple(str(line) for line in raw_lines))


def render(result: OpResult) -> str:
    """Return the shell transcript for *result*.

    Args:
        result: Operation result to print.

    Returns:
        Lines joined with newlines, and a trailing newline when lines is not empty.
    """
    if isinstance(result, CheckResult):
        return _render_check(result)
    if isinstance(result, CreateResult):
        return _render_create(result)
    if isinstance(result, RestoreResult):
        return _render_restore(result)
    if isinstance(result, RemoveResult):
        return _render_remove(result)
    if isinstance(result, ReloadResult):
        return _render_reload(result)
    return "" if not result.lines else "\n".join(result.lines) + "\n"


def payload_text(response: dict[str, Any]) -> str:
    """Return the shell transcript for an IPC *response*.

    Args:
        response: Daemon IPC payload. A failed, check, create, restore,
            remove, or reload envelope is rendered; leftover status/wait
            transcripts still use ``stdout``.

    Returns:
        Text the shell should print.
    """
    if response.get("kind") in _KIND_ENVELOPES:
        return render(from_ipc(response))
    return str(response.get("stdout") or "")


def _check_to_ipc(result: CheckResult) -> dict[str, Any]:
    return {
        "exit_code": result.exit_code,
        "extra_exclude": result.extra_exclude,
        "kind": "check",
        "not_found": result.not_found,
        "output_format": str(result.output_format),
        "rows": [_row_to_ipc(row) for row in result.rows],
    }


def _row_to_ipc(row: CheckRow) -> dict[str, Any]:
    return {
        "copy": None if row.copy is None else _copy_to_ipc(row.copy),
        "git": None if row.git is None else _git_to_ipc(row.git),
        "project_name": row.project_name,
        "skip": row.skip,
        "target_path": row.target_path,
    }


def _copy_to_ipc(copy: LinkCheckResult) -> dict[str, Any]:
    details = copy.details
    return {
        "details": {
            "both_changed": list(details.both_changed),
            "in_sync": list(details.in_sync),
            "managed_changed": list(details.managed_changed),
            "mismatched": list(details.mismatched),
            "target_changed": list(details.target_changed),
        },
        "exists": list(copy.exists),
        "incorrect": list(copy.incorrect),
        "missing": list(copy.missing),
    }


def _git_to_ipc(git: GitExcludeStatus) -> dict[str, Any]:
    return {
        "extra": sorted(git.extra),
        "missing": sorted(git.missing),
        "present": sorted(git.present),
    }


def _check_from_ipc(payload: dict[str, Any]) -> CheckResult:
    raw_code = payload.get("exit_code", 0)
    if not isinstance(raw_code, int):
        raise ValueError("check operation result needs an exit_code")
    raw_rows = payload.get("rows", ())
    if not isinstance(raw_rows, list | tuple):
        raise ValueError("check operation result needs rows")
    not_found = payload.get("not_found")
    if not_found is not None and not isinstance(not_found, str):
        raise ValueError("check operation result not_found must be a string")
    return CheckResult(
        exit_code=raw_code,
        extra_exclude=bool(payload.get("extra_exclude")),
        output_format=OutputFormat(str(payload.get("output_format") or OutputFormat.TABLE)),
        rows=tuple(_row_from_ipc(row) for row in raw_rows),
        not_found=not_found,
    )


def _row_from_ipc(raw: object) -> CheckRow:
    if not isinstance(raw, dict):
        raise ValueError("check row must be an object")
    skip = raw.get("skip")
    if skip is not None and skip not in _CHECK_SKIPS:
        raise ValueError("check row skip is not a known skip")
    return CheckRow(
        project_name=str(raw.get("project_name") or ""),
        target_path=str(raw.get("target_path") or ""),
        skip=skip,
        copy=_copy_from_ipc(raw.get("copy")),
        git=_git_from_ipc(raw.get("git")),
    )


def _copy_from_ipc(raw: object) -> LinkCheckResult | None:
    from .link_check import CopyCheckDetails, LinkCheckResult  # noqa: PLC0415

    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("check copy result must be an object")
    details_raw = raw.get("details") or {}
    if not isinstance(details_raw, dict):
        raise ValueError("check copy details must be an object")
    return LinkCheckResult(
        exists=_names_list(raw.get("exists")),
        missing=_names_list(raw.get("missing")),
        incorrect=_names_list(raw.get("incorrect")),
        details=CopyCheckDetails(
            in_sync=_names_list(details_raw.get("in_sync")),
            mismatched=_names_list(details_raw.get("mismatched")),
            managed_changed=_names_list(details_raw.get("managed_changed")),
            target_changed=_names_list(details_raw.get("target_changed")),
            both_changed=_names_list(details_raw.get("both_changed")),
        ),
    )


def _git_from_ipc(raw: object) -> GitExcludeStatus | None:
    from .link_check import GitExcludeStatus  # noqa: PLC0415

    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("check git status must be an object")
    return GitExcludeStatus(
        present=_names_set(raw.get("present")),
        missing=_names_set(raw.get("missing")),
        extra=_names_set(raw.get("extra")),
    )


def _names_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list | tuple):
        raise ValueError("check names must be a list")
    return [str(item) for item in raw]


def _names_set(raw: object) -> set[str]:
    return set(_names_list(raw))


def _render_check(result: CheckResult) -> str:
    from .link_check import CheckTableFormatter, LinkCheckFormatter  # noqa: PLC0415

    if result.not_found is not None:
        return result.not_found + "\n"
    if result.output_format == OutputFormat.VERBOSE:
        parts: list[str] = []
        for row in result.rows:
            skip_line = _skip_line(row)
            if skip_line is not None:
                parts.append(skip_line)
                continue
            if row.copy is None:
                continue
            formatter = LinkCheckFormatter(row.copy, row.git, result.extra_exclude)
            parts.append(formatter.render(row.project_name, row.target_path))
        return "".join(parts)
    parts = []
    data_rows: list[CheckRow] = []
    for row in result.rows:
        skip_line = _skip_line(row)
        if skip_line is not None:
            parts.append(skip_line)
            continue
        data_rows.append(row)
    if data_rows:
        parts.append(CheckTableFormatter(data_rows, result.extra_exclude).render())
    return "".join(parts)


def _skip_line(row: CheckRow) -> str | None:
    if row.skip == "missing_project":
        return f"Project directory does not exist: {row.target_path}\n"
    if row.skip == "missing_target":
        return f"Target directory does not exist: {row.target_path}\n"
    return None


def _story_line(dry_run: bool, message: str) -> str:
    """Prefix each line when *dry_run* is set."""
    prefix = "[dry-run] " if dry_run else ""
    return "\n".join(f"{prefix}{line}" for line in message.splitlines() or [""])


def _hold_lines(dry_run: bool, holds: tuple[tuple[str, str], ...]) -> list[str]:
    lines: list[str] = []
    for clause, slot in holds:
        lines.append(_story_line(dry_run, f"WARNING: {clause}"))
        lines.append(_story_line(dry_run, f"Held at {slot}"))
    return lines


def _create_to_ipc(result: CreateResult) -> dict[str, Any]:
    return {
        "already_managed": result.already_managed,
        "config_entry": result.config_entry,
        "dest": result.dest,
        "dry_run": result.dry_run,
        "errors": list(result.errors),
        "exit_code": result.exit_code,
        "fan_out": [list(pair) for pair in result.fan_out],
        "force_overwrite": result.force_overwrite,
        "git_excludes": [list(item) for item in result.git_excludes],
        "holds": [list(item) for item in result.holds],
        "kind": "create",
        "persist_warning": result.persist_warning,
        "source": result.source,
    }


def _create_excludes_from_ipc(raw: object) -> tuple[tuple[str, str, GitExcludeAction], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list | tuple):
        raise ValueError("create git_excludes must be a list")
    items: list[tuple[str, str, GitExcludeAction]] = []
    for item in raw:
        if not isinstance(item, list | tuple):
            raise ValueError("create git_exclude must have a root, name, and action")
        try:
            root, name, action = item
        except ValueError:
            raise ValueError("create git_exclude must have a root, name, and action") from None
        if action not in _GIT_EXCLUDE_ACTIONS:
            raise ValueError("create git_exclude is not a known status")
        items.append((str(root), str(name), "added" if action == "added" else "exists"))
    return tuple(items)


def _holds_from_ipc(raw: object) -> tuple[tuple[str, str], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list | tuple):
        raise ValueError("holds must be a list")
    items: list[tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, list | tuple):
            raise ValueError("hold must have a clause and a slot")
        try:
            clause, slot = item
        except ValueError:
            raise ValueError("hold must have a clause and a slot") from None
        items.append((str(clause), str(slot)))
    return tuple(items)


def _create_from_ipc(payload: dict[str, Any]) -> CreateResult:
    raw_code = payload.get("exit_code", 0)
    if not isinstance(raw_code, int):
        raise ValueError("create operation result needs an exit_code")
    return CreateResult(
        exit_code=raw_code,
        dry_run=bool(payload.get("dry_run")),
        errors=_str_tuple(payload.get("errors"), "errors"),
        already_managed=_opt_str(payload.get("already_managed"), "already_managed"),
        force_overwrite=_opt_str(payload.get("force_overwrite"), "force_overwrite"),
        source=str(payload.get("source") or ""),
        dest=str(payload.get("dest") or ""),
        git_excludes=_create_excludes_from_ipc(payload.get("git_excludes")),
        fan_out=_fan_out_from_ipc(payload.get("fan_out")),
        holds=_holds_from_ipc(payload.get("holds")),
        config_entry=_opt_str(payload.get("config_entry"), "config_entry"),
        persist_warning=_opt_str(payload.get("persist_warning"), "persist_warning"),
    )


def _str_tuple(raw: object, name: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list | tuple):
        raise ValueError(f"{name} must be a list")
    return tuple(str(item) for item in raw)


def _opt_str(raw: object, name: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError(f"{name} must be a string")
    return raw


def _fan_out_from_ipc(raw: object) -> tuple[tuple[str, str], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list | tuple):
        raise ValueError("create fan_out must be a list")
    pairs: list[tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, list | tuple):
            raise ValueError("create fan_out pair must have two paths")
        try:
            hub, replica = item
        except ValueError:
            raise ValueError("create fan_out pair must have two paths") from None
        pairs.append((str(hub), str(replica)))
    return tuple(pairs)


def _render_create(result: CreateResult) -> str:
    dry = result.dry_run
    lines: list[str] = []
    if result.errors:
        lines.extend(_story_line(dry, f"Error: {message}") for message in result.errors)
    elif result.already_managed is not None:
        lines.append(_story_line(dry, result.already_managed))
    else:
        if result.force_overwrite is not None:
            lines.append(_story_line(dry, f"Warning: overwriting existing managed copy at {result.force_overwrite}"))
        lines.append(_story_line(dry, f"Copying {result.source} -> {result.dest}"))
        lines.append(_story_line(dry, f"✓ Target path left in place: {result.source}"))
        for index, (root, name, action) in enumerate(result.git_excludes):
            if action == "added":
                text = f"Added {name!r} to .git/info/exclude"
            else:
                text = f"{name!r} already in .git/info/exclude"
            if index > 0:
                text = f"{text} ({root})"
            lines.append(_story_line(dry, text))
        if result.config_entry is not None:
            lines.append(_story_line(dry, f"Added {result.config_entry!r} to config subpath list"))
        for hub, replica in result.fan_out:
            lines.append(_story_line(dry, f"Fan-out {hub} -> {replica}"))
        lines.extend(_hold_lines(dry, result.holds))
    if result.persist_warning is not None:
        lines.append(f"Warning: could not persist mapping snapshot: {result.persist_warning}")
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _restore_to_ipc(result: RestoreResult) -> dict[str, Any]:
    return {
        "config_removed": result.config_removed,
        "dry_run": result.dry_run,
        "errors": list(result.errors),
        "exit_code": result.exit_code,
        "git_excludes": [list(item) for item in result.git_excludes],
        "holds": [list(item) for item in result.holds],
        "kind": "restore",
        "leftover_symlink": result.leftover_symlink,
        "managed": result.managed,
        "persist_warning": result.persist_warning,
        "replica_deletes": list(result.replica_deletes),
        "source": result.source,
    }


def _restore_from_ipc(payload: dict[str, Any]) -> RestoreResult:
    raw_code = payload.get("exit_code", 0)
    if not isinstance(raw_code, int):
        raise ValueError("restore operation result needs an exit_code")
    return RestoreResult(
        exit_code=raw_code,
        dry_run=bool(payload.get("dry_run")),
        errors=_str_tuple(payload.get("errors"), "errors"),
        leftover_symlink=bool(payload.get("leftover_symlink")),
        source=str(payload.get("source") or ""),
        managed=str(payload.get("managed") or ""),
        replica_deletes=_str_tuple(payload.get("replica_deletes"), "replica_deletes"),
        git_excludes=_restore_git_from_ipc(payload.get("git_excludes")),
        holds=_holds_from_ipc(payload.get("holds")),
        config_removed=_opt_str(payload.get("config_removed"), "config_removed"),
        persist_warning=_opt_str(payload.get("persist_warning"), "persist_warning"),
    )


def _restore_git_from_ipc(raw: object) -> tuple[tuple[str, RestoreGitExcludeStatus], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list | tuple):
        raise ValueError("restore git_excludes must be a list")
    items: list[tuple[str, RestoreGitExcludeStatus]] = []
    for item in raw:
        if not isinstance(item, list | tuple):
            raise ValueError("restore git_excludes pair must have a name and status")
        try:
            name, status = item
        except ValueError:
            raise ValueError("restore git_excludes pair must have a name and status") from None
        if status not in _RESTORE_GIT_STATUSES:
            raise ValueError("restore git_excludes status is not a known status")
        items.append((str(name), "removed" if status == "removed" else "not_found"))
    return tuple(items)


def _remove_to_ipc(result: RemoveResult) -> dict[str, Any]:
    return {
        "artifacts": [[path, kind, present] for path, kind, present in result.artifacts],
        "config": result.config,
        "config_entry": result.config_entry,
        "config_path": result.config_path,
        "dry_run": result.dry_run,
        "errors": list(result.errors),
        "excludes": [list(item) for item in result.excludes],
        "exit_code": result.exit_code,
        "holds": [list(item) for item in result.holds],
        "kind": "remove",
        "managed_copy": result.managed_copy,
        "persist_warning": result.persist_warning,
    }


def _remove_from_ipc(payload: dict[str, Any]) -> RemoveResult:
    raw_code = payload.get("exit_code", 0)
    if not isinstance(raw_code, int):
        raise ValueError("remove operation result needs an exit_code")
    config: RemoveConfigStatus | None = None
    raw_config = payload.get("config")
    if raw_config is not None:
        if raw_config not in _REMOVE_CONFIG_STATUSES:
            raise ValueError("remove config is not a known status")
        config = "updated" if raw_config == "updated" else "skipped" if raw_config == "skipped" else "repair"
    return RemoveResult(
        exit_code=raw_code,
        dry_run=bool(payload.get("dry_run")),
        errors=_str_tuple(payload.get("errors"), "errors"),
        artifacts=_remove_artifacts_from_ipc(payload.get("artifacts")),
        excludes=_remove_excludes_from_ipc(payload.get("excludes")),
        managed_copy=str(payload.get("managed_copy") or ""),
        config=config,
        config_path=_opt_str(payload.get("config_path"), "config_path"),
        config_entry=_opt_str(payload.get("config_entry"), "config_entry"),
        holds=_holds_from_ipc(payload.get("holds")),
        persist_warning=_opt_str(payload.get("persist_warning"), "persist_warning"),
    )


def _remove_artifacts_from_ipc(raw: object) -> tuple[tuple[str, RemoveArtifactKind | None, bool], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list | tuple):
        raise ValueError("remove artifacts must be a list")
    items: list[tuple[str, RemoveArtifactKind | None, bool]] = []
    for item in raw:
        if not isinstance(item, list | tuple):
            raise ValueError("remove artifact must have a path, kind, and present flag")
        try:
            path, kind, present = item
        except ValueError:
            raise ValueError("remove artifact must have a path, kind, and present flag") from None
        artifact_kind: RemoveArtifactKind | None
        if kind is None:
            artifact_kind = None
        elif kind not in _REMOVE_ARTIFACT_KINDS:
            raise ValueError("remove artifact kind is not a known strategy")
        else:
            artifact_kind = "copy" if kind == "copy" else "symlink"
        items.append((str(path), artifact_kind, bool(present)))
    return tuple(items)


def _remove_excludes_from_ipc(raw: object) -> tuple[tuple[str, str, bool], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list | tuple):
        raise ValueError("remove excludes must be a list")
    items: list[tuple[str, str, bool]] = []
    for item in raw:
        if not isinstance(item, list | tuple):
            raise ValueError("remove exclude must have an entry, path, and present flag")
        try:
            entry, exclude_file, present = item
        except ValueError:
            raise ValueError("remove exclude must have an entry, path, and present flag") from None
        items.append((str(entry), str(exclude_file), bool(present)))
    return tuple(items)


def _render_restore(result: RestoreResult) -> str:
    dry = result.dry_run
    lines: list[str] = []
    if result.errors:
        if result.leftover_symlink:
            lines.append(_story_line(dry, f"Removing symlink at {result.source}"))
        lines.extend(_story_line(dry, f"Error: {message}") for message in result.errors)
    else:
        if result.leftover_symlink:
            lines.append(_story_line(dry, f"Removing symlink at {result.source}"))
            lines.append(_story_line(dry, f"Copying {result.managed} -> {result.source}"))
        else:
            lines.append(_story_line(dry, f"Leaving target file in place: {result.source}"))
        lines.append(_story_line(dry, f"✓ Managed copy deleted: {result.managed}"))
        lines.extend(_story_line(dry, f"Deleted replica copy: {path}") for path in result.replica_deletes)
        for name, status in result.git_excludes:
            if status == "removed":
                lines.append(_story_line(dry, f"Removed {name!r} from .git/info/exclude"))
            else:
                lines.append(_story_line(dry, f"{name!r} not in .git/info/exclude"))
        if result.config_removed is not None:
            lines.append(_story_line(dry, f"Removed {result.config_removed!r} from config subpath list"))
        lines.extend(_hold_lines(dry, result.holds))
    if result.persist_warning is not None:
        lines.append(f"Warning: could not persist mapping snapshot: {result.persist_warning}")
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _render_remove(result: RemoveResult) -> str:  # noqa: PLR0912 -- story, repair, and error branches
    dry = result.dry_run
    lines: list[str] = []
    story = result.config == "repair" or not result.errors
    for path, kind, present in result.artifacts:
        if present and kind is not None:
            lines.append(_story_line(dry, f"Removed {kind} artifact: {path}"))
        else:
            lines.append(_story_line(dry, f"Skipping absent artifact: {path}"))
    for entry, exclude_file, present in result.excludes:
        if present:
            lines.append(_story_line(dry, f"Removed Git exclude entry {entry!r} from {exclude_file}"))
        else:
            lines.append(_story_line(dry, f"Skipping absent Git exclude entry {entry!r} in {exclude_file}"))
    if story:
        lines.append(_story_line(dry, f"Deleted managed copy: {result.managed_copy}"))
        if result.config == "repair":
            lines.extend(_story_line(dry, f"Error: {message}") for message in result.errors)
            if result.config_entry is not None:
                repair = (
                    f"Managed copy {result.managed_copy} was deleted; "
                    f"remove {result.config_entry!r} from configuration manually."
                )
                lines.append(_story_line(dry, repair))
        elif result.config == "updated" and result.config_entry is not None and result.config_path is not None:
            updated = f"Removed {result.config_entry!r} from selective-sync configuration: {result.config_path}"
            lines.append(_story_line(dry, updated))
        elif result.config == "skipped":
            lines.append(_story_line(dry, "Skipping configuration update: no participating selective mapping"))
        lines.extend(_hold_lines(dry, result.holds))
    else:
        lines.extend(_story_line(dry, f"Error: {message}") for message in result.errors)
    if result.persist_warning is not None:
        lines.append(f"Warning: could not persist mapping snapshot: {result.persist_warning}")
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _reload_to_ipc(result: ReloadResult) -> dict[str, Any]:
    return {
        "affected": list(result.affected),
        "exit_code": result.exit_code,
        "kind": "reload",
        "missing_hubs": list(result.missing_hubs),
        "overlaps": [
            [overlap.target.as_posix(), overlap.project_a, overlap.item_a, overlap.project_b, overlap.item_b]
            for overlap in result.overlaps
        ],
        "problem": result.problem,
    }


def _reload_from_ipc(payload: dict[str, Any]) -> ReloadResult:
    raw_code = payload.get("exit_code", 0)
    if not isinstance(raw_code, int):
        raise ValueError("reload operation result needs an exit_code")
    problem: ReloadProblem | None = None
    raw_problem = payload.get("problem")
    if raw_problem is not None:
        if raw_problem not in _RELOAD_PROBLEMS:
            raise ValueError("reload problem is not a known problem")
        problem = raw_problem
    return ReloadResult(
        exit_code=raw_code,
        affected=_str_tuple(payload.get("affected"), "affected"),
        problem=problem,
        overlaps=_overlaps_from_ipc(payload.get("overlaps")),
        missing_hubs=_str_tuple(payload.get("missing_hubs"), "missing_hubs"),
    )


def _overlaps_from_ipc(raw: object) -> tuple[ItemOverlap, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list | tuple):
        raise ValueError("reload overlaps must be a list")
    overlaps: list[ItemOverlap] = []
    for item in raw:
        if not isinstance(item, list | tuple):
            raise ValueError("reload overlap must have a target, two projects, and two items")
        try:
            target, project_a, item_a, project_b, item_b = item
        except ValueError:
            raise ValueError("reload overlap must have a target, two projects, and two items") from None
        overlaps.append(
            ItemOverlap(
                target=Path(str(target)),
                project_a=str(project_a),
                item_a=str(item_a),
                project_b=str(project_b),
                item_b=str(item_b),
            )
        )
    return tuple(overlaps)


def _render_reload(result: ReloadResult) -> str:
    if result.problem is None:
        return ""
    if result.problem == "snapshot_missing":
        lines = ["Error: mapping snapshot is missing"]
    elif result.problem == "overlap":
        lines = [f"Error: {format_item_overlap(overlap)}" for overlap in result.overlaps]
    elif result.problem == "missing_hub":
        lines = [f"Error: hub file does not exist: {path}" for path in result.missing_hubs]
    else:
        lines = ["Error: mapping removals require interactive confirmation"]
    if not lines:
        return ""
    return "\n".join(lines) + "\n"
