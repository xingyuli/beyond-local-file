"""Shell-side helper that sends a request to the running daemon."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from .ipc import send_request
from .process import is_running

DAEMON_DOWN_HINT = "Error: daemon is not running. Start it with: blf daemon start"
DAEMON_RUNNING_HINT = "Error: daemon is running. Stop it with: blf daemon stop"


def call_daemon(config_path: Path, request: dict[str, Any]) -> int:
    """Send *request* to the daemon and print its captured stdout.

    Args:
        config_path: Path to the loaded config file.
        request: JSON-serialisable daemon request.

    Returns:
        The daemon's exit code, or 1 when the daemon is not accepting requests.
    """
    if not is_running(config_path):
        click.echo(DAEMON_DOWN_HINT)
        return 1
    try:
        response = send_request(config_path, request)
    except OSError:
        click.echo(DAEMON_DOWN_HINT)
        return 1
    stdout = response.get("stdout") or ""
    if stdout:
        click.echo(stdout, nl=not str(stdout).endswith("\n"))
    try:
        return int(response.get("exit_code", 1))
    except (TypeError, ValueError):
        return 1
