"""Shared helpers for tests that start the copy-only daemon."""

from __future__ import annotations

import os
import signal
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from click.testing import CliRunner, Result

from beyond_local_file.cli import cli
from beyond_local_file.daemon.process import pid_path

_POLL_S = 0.05


def invoke_cli(
    args: list[str],
    env: dict[str, str] | None = None,
    *,
    input: str | None = None,
) -> Result:
    """Invoke the CLI in-process."""
    return CliRunner().invoke(cli, args, env=env, input=input)


def start_daemon(config_path: Path, env: dict[str, str] | None = None) -> None:
    """Start the daemon for *config_path* and fail if it does not become ready."""
    started = invoke_cli(["--config", str(config_path), "daemon", "start"], env=env)
    assert started.exit_code == 0, started.output


def stop_daemon(config_path: Path, env: dict[str, str] | None = None) -> None:
    """Stop the daemon if it is running."""
    invoke_cli(["--config", str(config_path), "daemon", "stop"], env=env)
    pid_file = pid_path(config_path)
    if not pid_file.exists():
        return
    text = pid_file.read_text(encoding="utf-8").strip()
    if not text:
        return
    pid = int(text.splitlines()[0])
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError, OSError):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        return
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, OSError):
            return
        time.sleep(_POLL_S)


def invoke_with_daemon(
    config_path: Path,
    args: list[str],
    env: dict[str, str] | None = None,
    *,
    input: str | None = None,
) -> Result:
    """Start the daemon, invoke *args* with ``--config``, then stop the daemon."""
    with daemon_running(config_path, env):
        return invoke_cli(["--config", str(config_path), *args], env=env, input=input)


@contextmanager
def daemon_running(config_path: Path, env: dict[str, str] | None = None) -> Iterator[None]:
    """Start the daemon for the duration of the with-block."""
    start_daemon(config_path, env)
    try:
        yield
    finally:
        stop_daemon(config_path, env)
