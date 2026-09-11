"""daemon subcommands — start, stop, status, and logs."""

from __future__ import annotations

from beyond_local_file.daemon.process import follow_log, print_status, spawn_and_wait, stop_process
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
    return spawn_and_wait(result.config_file)


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
