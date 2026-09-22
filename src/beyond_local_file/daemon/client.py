"""Shell-side helper that sends a request to the running daemon."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click

from .ipc import ProgressCallback, Request, RequestSession, Response, open_request_session, send_request
from .process import is_running, port_path
from .screen import ScreenQuestion, ScreenSkip, run_shell_screen

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


def shell_wants_screen() -> bool:
    """Return whether this shell should draw the shell screen."""
    return stdin_is_tty() and stdout_is_tty()


def call_daemon(
    config_path: Path,
    request: dict[str, Any],
    *,
    questions: tuple[ScreenQuestion, ...] = (),
    apply_answers: Callable[[tuple[str, ...], Request], ScreenSkip | None] | None = None,
    trailer: tuple[str, ...] = (),
) -> int:
    """Send *request* to the daemon and print its captured stdout.

    Create, restore, remove, check, reload, and status on a terminal open the
    shell screen and leave it up until the user closes it. A shell with no
    terminal prints the result and does not wait. Pre-request *questions* are
    asked on that screen; nothing is sent until they are answered.

    Args:
        config_path: Path to the loaded config file.
        request: JSON-serialisable daemon request.
        questions: Shell-screen questions asked before the request is sent.
        apply_answers: Writes answers into *request*, or returns a skip to
            finish without sending.
        trailer: Extra output lines appended after the daemon transcript.

    Returns:
        The daemon's exit code, or 1 when the daemon is not accepting requests.
    """
    if not is_running(config_path):
        click.echo(DAEMON_DOWN_HINT)
        return 1
    if _wants_shell_screen(request) and shell_wants_screen():
        return _call_on_shell_screen(
            config_path,
            request,
            questions=questions,
            apply_answers=apply_answers,
            trailer=trailer,
        )
    return _call_with_status_line(config_path, request)


def _wants_shell_screen(request: dict[str, Any]) -> bool:
    return request.get("op") in {"create", "restore", "remove", "check", "reload", "status"}


def _call_on_shell_screen(
    config_path: Path,
    request: dict[str, Any],
    *,
    questions: tuple[ScreenQuestion, ...] = (),
    apply_answers: Callable[[tuple[str, ...], Request], ScreenSkip | None] | None = None,
    trailer: tuple[str, ...] = (),
) -> int:
    def connect(answers: tuple[str, ...]) -> RequestSession:
        if apply_answers is not None:
            skipped = apply_answers(answers, request)
            if skipped is not None:
                raise skipped
        return _retry_while_down(config_path, lambda: open_request_session(config_path, request))

    if questions:
        return run_shell_screen(request, questions=questions, connect=connect, trailer=trailer)
    try:
        session = _retry_while_down(config_path, lambda: open_request_session(config_path, request))
    except OSError:
        click.echo(DAEMON_DOWN_HINT)
        return 1
    try:
        return run_shell_screen(request, session, trailer=trailer)
    finally:
        session.close()


def _call_with_status_line(config_path: Path, request: dict[str, Any]) -> int:
    status_line = _StatusLine(enabled=request.get("op") not in {"check", "reload"})
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


def open_wait_session(config_path: Path) -> RequestSession:
    """Open a wait request, retrying while the worker is alive but not yet listening."""
    return _retry_while_down(config_path, lambda: open_request_session(config_path, {"op": "wait"}))


def wait_until_ready(config_path: Path) -> int:
    """Block until the daemon reports phase ready.

    On a terminal this draws the shell screen through catch-up and leaves it
    up once the daemon is ready. Closing prints ``Daemon started (pid …)``.
    A shell with no terminal waits without a status line.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        0 when the daemon is ready, 1 if the connection fails.
    """
    if shell_wants_screen():
        return _wait_on_shell_screen(config_path)
    try:
        response = send_when_up(config_path, {"op": "wait"})
    except OSError:
        return 1
    try:
        return int(response.get("exit_code", 1))
    except (TypeError, ValueError):
        return 1


def _wait_on_shell_screen(config_path: Path) -> int:
    try:
        session = open_wait_session(config_path)
    except OSError:
        return 1
    try:
        return run_shell_screen({"op": "wait"}, session)
    finally:
        session.close()


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

    def __init__(self, *, enabled: bool = True) -> None:
        self._width = 0
        self._tty = enabled and stderr_is_tty()

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
