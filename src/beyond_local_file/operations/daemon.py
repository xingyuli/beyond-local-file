"""daemon subcommands — start, stop, status, logs, and reload."""

from __future__ import annotations

import click

from beyond_local_file.daemon.client import DAEMON_DOWN_HINT, call_daemon
from beyond_local_file.daemon.ingest import ingest_before_start, prepare_ingest
from beyond_local_file.daemon.process import (
    follow_log,
    is_running,
    print_status,
    read_pid,
    spawn_and_wait,
    stop_process,
)
from beyond_local_file.daemon.runtime import run_worker
from beyond_local_file.project_processor import load_config_projects


def start_daemon(config: str | None, *, worker: bool) -> int:
    """Start the daemon or run the worker loop.

    Args:
        config: Optional ``--config`` path.
        worker: When True, run the in-process worker instead of spawning.

    Returns:
        Process exit code.
    """
    result = load_config_projects(config)
    if result is None:
        return 1
    if worker:
        return run_worker(result.config_file)
    if is_running(result.config_file):
        click.echo(f"Error: daemon is already running (pid {read_pid(result.config_file)})")
        return 1
    ingest_code = ingest_before_start(result.config_file)
    if ingest_code != 0:
        return ingest_code
    return spawn_and_wait(result.config_file)


def reload_daemon(config: str | None) -> int:
    """Classify external mapping edits and ask the running daemon to commit.

    Args:
        config: Optional ``--config`` path.

    Returns:
        Process exit code.
    """
    result = load_config_projects(config)
    if result is None:
        return 1
    if not is_running(result.config_file):
        click.echo(DAEMON_DOWN_HINT)
        return 1
    code, _file_projects, snapshot_projects, diff = prepare_ingest(result.config_file)
    if code != 0:
        return code
    if snapshot_projects is None:
        click.echo("Error: mapping snapshot is missing")
        return 1
    if diff is None:
        click.echo("Mappings already match the snapshot")
        return 0
    return call_daemon(
        result.config_file,
        {"op": "reload", "confirmed": bool(diff.removals)},
    )


def stop_daemon(config: str | None) -> int:
    """Stop the running daemon.

    Args:
        config: Optional ``--config`` path.

    Returns:
        Process exit code.
    """
    result = load_config_projects(config)
    if result is None:
        return 1
    return stop_process(result.config_file)


def status_daemon(config: str | None) -> int:
    """Print whether the daemon is running.

    Args:
        config: Optional ``--config`` path.

    Returns:
        Process exit code.
    """
    result = load_config_projects(config)
    if result is None:
        return 1
    return print_status(result.config_file)


def follow_daemon_logs(config: str | None) -> int:
    """Follow the daemon log until interrupted.

    Args:
        config: Optional ``--config`` path.

    Returns:
        Process exit code.
    """
    result = load_config_projects(config)
    if result is None:
        return 1
    return follow_log(result.config_file)
