"""Structured results returned by daemon operations over IPC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

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


type OpResult = FailedResult | CheckResult

_CHECK_SKIPS = frozenset({"missing_project", "missing_target"})


def to_ipc(result: OpResult) -> dict[str, Any]:
    """Return the IPC payload for *result*.

    Args:
        result: Operation result to send to the shell.

    Returns:
        JSON-serialisable envelope with ``kind`` and the result fields.
    """
    if isinstance(result, CheckResult):
        return _check_to_ipc(result)
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
        The failed or check result matching ``kind``.

    Raises:
        ValueError: If *payload* is not a known operation result.
    """
    kind = payload.get("kind")
    if kind == "check":
        return _check_from_ipc(payload)
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
    if not result.lines:
        return ""
    return "\n".join(result.lines) + "\n"


def payload_text(response: dict[str, Any]) -> str:
    """Return the shell transcript for an IPC *response*.

    Args:
        response: Daemon IPC payload. A failed or check envelope is rendered;
            leftover status/wait transcripts still use ``stdout``.

    Returns:
        Text the shell should print.
    """
    if response.get("kind") in {"failed", "check"}:
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
