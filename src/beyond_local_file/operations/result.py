"""Structured results returned by daemon operations over IPC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FailedResult:
    """A request that did not complete, with the lines the shell prints.

    Request-lifecycle, not a create. The exit code is the process status
    the shell returns, not a classified error.
    """

    exit_code: int
    lines: tuple[str, ...]


type OpResult = FailedResult


def to_ipc(result: OpResult) -> dict[str, Any]:
    """Return the IPC payload for *result*.

    Args:
        result: Operation result to send to the shell.

    Returns:
        JSON-serialisable envelope with ``kind``, ``exit_code``, and ``lines``.
    """
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
        The failed result when ``kind`` is ``failed``.

    Raises:
        ValueError: If *payload* is not a failed result.
    """
    if payload.get("kind") != "failed":
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
    if not result.lines:
        return ""
    return "\n".join(result.lines) + "\n"


def payload_text(response: dict[str, Any]) -> str:
    """Return the shell transcript for an IPC *response*.

    Args:
        response: Daemon IPC payload. A failed envelope is rendered; leftover
            status/wait transcripts still use ``stdout``.

    Returns:
        Text the shell should print.
    """
    if response.get("kind") == "failed":
        return render(from_ipc(response))
    return str(response.get("stdout") or "")
