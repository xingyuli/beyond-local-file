"""Shared helpers for tests that start the copy-only daemon."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from click.testing import CliRunner, Result

from beyond_local_file.cli import cli
from beyond_local_file.daemon.process import PID_NAME, pid_path

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


def _is_blf_worker(pid: int) -> bool:
    """Return whether *pid* is a live daemon worker (guards against pid reuse)."""
    try:
        out = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
    except OSError:
        return False
    return "beyond_local_file" in out and "--worker" in out


def _has_exited(pid: int) -> bool:
    """Reap *pid* if it is our child, otherwise probe it; True once it is gone."""
    try:
        reaped, _status = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, OSError):
            return True
        return False
    return reaped == pid


def reap_daemons(run_root: Path) -> None:
    """Terminate every daemon whose pidfile sits under *run_root*.

    The daemon is spawned in its own session, so it outlives pytest when a test
    fails between ``daemon start`` and its own ``stop_daemon``. *run_root* is the
    per-test ``<BLF_HOME>/.blf/run`` directory, never the real home.
    """
    for pid_file in run_root.glob(f"*/{PID_NAME}"):
        try:
            pid = int(pid_file.read_text(encoding="utf-8").splitlines()[0])
        except (OSError, ValueError, IndexError):
            continue
        if not _is_blf_worker(pid):
            continue
        for sig, wait_s in ((signal.SIGTERM, 5.0), (signal.SIGKILL, 2.0)):
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, OSError):
                break
            deadline = time.monotonic() + wait_s
            while time.monotonic() < deadline and not _has_exited(pid):
                time.sleep(_POLL_S)
            if _has_exited(pid):
                break
