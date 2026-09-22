"""Shell-side helper that sends a request to the running daemon."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click

from .ipc import ProgressCallback, Request, Response, open_request_session, send_request
from .process import is_running, port_path
from .screen import run_shell_screen

DAEMON_DOWN_HINT = "Error: daemon is not running. Start it with: blf daemon start"
DAEMON_RUNNING_HINT = "Error: daemon is running. Stop it with: blf daemon stop"

_CONNECT_RETRY_S = 30.0
_POLL_S = 0.05


def stderr_is_tty() -> bool:
    """Return whether the shell stderr can render a rewritten status line."""
    try:
        return sys.stderr.isatty()
    except ValueError:
        return False


def stdout_is_tty() -> bool:
    """Return whether the shell stdout is a terminal."""
    try:
        return sys.stdout.isatty()
    except ValueError:
        return False


def stdin_is_tty() -> bool:
    """Return whether the shell stdin is a terminal."""
    try:
        return sys.stdin.isatty()
    except ValueError:
        return False


def call_daemon(config_path: Path, request: dict[str, Any]) -> int:
    """Send *request* to the daemon and print its captured stdout.

    Create, restore, and remove on a terminal open the shell screen and leave
    it up until the user closes it. Other shells keep one TTY status line.
    A shell with no terminal prints the result and does not wait.

    Args:
        config_path: Path to the loaded config file.
        request: JSON-serialisable daemon request.

    Returns:
        The daemon's exit code, or 1 when the daemon is not accepting requests.
    """
    if not is_running(config_path):
        click.echo(DAEMON_DOWN_HINT)
        return 1
    if _wants_shell_screen(request) and stdin_is_tty() and stdout_is_tty():
        return _call_on_shell_screen(config_path, request)
    return _call_with_status_line(config_path, request)


def _wants_shell_screen(request: dict[str, Any]) -> bool:
    return request.get("op") in {"create", "restore", "remove"}


def _call_on_shell_screen(config_path: Path, request: dict[str, Any]) -> int:
    try:
        session = _retry_while_down(config_path, lambda: open_request_session(config_path, request))
    except OSError:
        click.echo(DAEMON_DOWN_HINT)
        return 1
    try:
        return run_shell_screen(request, session)
    finally:
        session.close()


def _call_with_status_line(config_path: Path, request: dict[str, Any]) -> int:
    status_line = _StatusLine()
    try:
        response = send_when_up(config_path, request, on_progress=status_line.update)
    except OSError:
        click.echo(DAEMON_DOWN_HINT)
        return 1
    finally:
        status_line.clear()
    return _print_response(response)


def _print_response(response: Response) -> int:
    stdout = response.get("stdout") or ""
    if stdout:
        click.echo(stdout, nl=not str(stdout).endswith("\n"))
    try:
        return int(response.get("exit_code", 1))
    except (TypeError, ValueError):
        return 1


def wait_until_ready(config_path: Path) -> int:
    """Block until the daemon reports phase ready, rendering catch-up progress.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        0 when the daemon is ready, 1 if the connection fails.
    """
    status_line = _StatusLine()
    try:
        response = send_when_up(config_path, {"op": "wait"}, on_progress=status_line.update)
    except OSError:
        return 1
    finally:
        status_line.clear()
    try:
        return int(response.get("exit_code", 1))
    except (TypeError, ValueError):
        return 1


def send_when_up(
    config_path: Path,
    request: Request,
    on_progress: ProgressCallback | None = None,
) -> Response:
    """Connect, retrying while the worker is alive but not yet listening.

    Args:
        config_path: Path to the loaded config file.
        request: JSON-serialisable request object.
        on_progress: Optional callback for streamed status lines.

    Returns:
        The daemon's JSON response.

    Raises:
        OSError: If the daemon dies or does not accept before the retry deadline.
    """
    return _retry_while_down(
        config_path,
        lambda: send_request(config_path, request, on_progress=on_progress),
    )


def _retry_while_down[T](config_path: Path, attempt: Callable[[], T]) -> T:
    """Retry *attempt* while the daemon is alive but not yet accepting.

    Args:
        config_path: Path to the loaded config file.
        attempt: One connection attempt.

    Returns:
        Whatever *attempt* returns.

    Raises:
        OSError: If the daemon dies or does not accept before the retry deadline.
    """
    deadline = time.monotonic() + _CONNECT_RETRY_S
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        try:
            return attempt()
        except OSError as error:
            last_error = error
            if not is_running(config_path):
                break
            if _port_is_ready(config_path) and not _is_connect_error(error):
                break
            time.sleep(_POLL_S)
    if last_error is not None:
        raise last_error
    raise OSError("daemon is not accepting requests")


def _port_is_ready(config_path: Path) -> bool:
    path = port_path(config_path)
    if not path.exists():
        return False
    try:
        return bool(path.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def _is_connect_error(error: OSError) -> bool:
    return isinstance(error, ConnectionRefusedError | FileNotFoundError)


class _StatusLine:
    """Rewrites one status line on a TTY stderr."""

    def __init__(self) -> None:
        self._width = 0
        self._tty = stderr_is_tty()

    def update(self, line: str) -> None:
        if not self._tty:
            return
        visible = max(self._width, len(line))
        sys.stderr.write("\r" + line + " " * (visible - len(line)))
        sys.stderr.flush()
        self._width = visible

    def clear(self) -> None:
        if not self._tty or self._width == 0:
            return
        sys.stderr.write("\r" + " " * self._width + "\r")
        sys.stderr.flush()
        self._width = 0
