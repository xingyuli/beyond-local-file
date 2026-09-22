"""daemon subcommands — start, stop, status, logs, and reload."""

from __future__ import annotations

from pathlib import Path

import click

from beyond_local_file.blfrc import is_global_config_path
from beyond_local_file.daemon.client import DAEMON_DOWN_HINT, call_daemon
from beyond_local_file.daemon.ingest import (
    affected_unit_names,
    ingest_before_start,
    prepare_ingest,
    stdin_is_tty,
)
from beyond_local_file.daemon.process import (
    follow_logs,
    is_running,
    overlapping_running_set,
    print_status,
    read_pid,
    spawn_and_wait,
    stop_process,
)
from beyond_local_file.daemon.runtime import run_worker
from beyond_local_file.daemon.store import iter_out_of_sync, load_baseline, load_snapshot
from beyond_local_file.held import list_held_copies
from beyond_local_file.model.config import ConfigProject
from beyond_local_file.project_processor import load_config_projects, load_set_projects, resolve_configuration_set


def start_daemon(config: str | None, *, worker: bool) -> int:
    """Start the daemon or run the worker loop.

    Args:
        config: Optional ``--config`` path.
        worker: When True, run the in-process worker instead of spawning.

    Returns:
        Process exit code.
    """
    result = resolve_configuration_set(config)
    if result is None:
        return 1
    if worker:
        return run_worker(result.config_file)
    if is_running(result.config_file):
        click.echo(f"Error: daemon is already running (pid {read_pid(result.config_file)})")
        return 1
    overlap = overlapping_running_set(list(result.mapping_files))
    if overlap is not None:
        identity, pid, mapping = overlap
        owner = "global set" if is_global_config_path(identity) else f"set {identity}"
        click.echo(f"Error: mapping file {mapping} is already loaded by the running {owner} (pid {pid})")
        return 1
    ingest_code = ingest_before_start(result.config_file)
    if ingest_code != 0:
        return ingest_code
    _warn_and_ack_isolation(result.config_file)
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
    code, file_projects, snapshot_projects, diff = prepare_ingest(result.config_file)
    if code != 0:
        return code
    if snapshot_projects is None:
        click.echo("Error: mapping snapshot is missing")
        return 1
    _warn_and_ack_isolation(result.config_file)
    if diff is None or file_projects is None or snapshot_projects is None:
        click.echo("Mappings already match the snapshot")
        return 0
    names = sorted(affected_unit_names(snapshot_projects, file_projects, diff))
    target = names[0] if len(names) == 1 else "all projects"
    return call_daemon(
        result.config_file,
        {"op": "reload", "confirmed": bool(diff.removals), "screen_target": target},
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
    """Print whether the daemon is running, plus out-of-sync paths and held copies.

    Args:
        config: Optional ``--config`` path.

    Returns:
        Process exit code.
    """
    result = load_config_projects(config)
    if result is None:
        return 1
    code = print_status(result.config_file)
    _echo_isolation(result.config_file, warning=False)
    return code


def follow_daemon_logs(config: str | None) -> int:
    """Tell the caller that ``daemon logs`` is retired.

    The command does not open or follow a log file.

    Args:
        config: Ignored. Kept so existing callers can pass ``--config``.

    Returns:
        0 after naming ``blf logs``.
    """
    del config
    click.echo("daemon logs is retired; use blf logs")
    return 0


def follow_blf_logs(config: str | None, record: str | None = None) -> int:
    """Follow one worker log, or the three logs merged by stamp.

    Args:
        config: Optional ``--config`` path.
        record: ``requests``, ``idle``, ``daemon``, or None to merge all three.

    Returns:
        Process exit code.
    """
    result = load_config_projects(config)
    if result is None:
        return 1
    return follow_logs(result.config_file, record)


def _warn_and_ack_isolation(config_path: Path) -> None:
    """Print held/out-of-sync WARNINGs and require ack without aborting."""
    if not _echo_isolation(config_path, warning=True):
        return
    if stdin_is_tty():
        click.confirm(
            "Continue without resolving held copies and out-of-sync paths?",
            default=True,
        )


def _echo_isolation(config_path: Path, *, warning: bool) -> bool:
    """Print out-of-sync paths and held-copy clauses.

    Args:
        config_path: Path to the loaded config file.
        warning: When True, prefix lines with ``WARNING:``.

    Returns:
        True when any out-of-sync path or held copy was printed.
    """
    oos = iter_out_of_sync(load_baseline(config_path) or {})
    held = [
        copy
        for project in _projects_for_isolation(config_path).values()
        for copy in list_held_copies(project.managed_project_path)
    ]
    prefix = "WARNING: " if warning else ""
    if oos:
        if not warning:
            click.echo("Out-of-sync:")
        for replica, rel in oos:
            line = f"out-of-sync {replica.as_posix()} {rel}"
            click.echo(f"{prefix}{line}" if warning else f"  {replica.as_posix()}  {rel}")
    if held:
        if not warning:
            click.echo("Held copies:")
        for copy in held:
            click.echo(f"{prefix}{copy.clause}" if warning else f"  {copy.clause}")
            click.echo(f"Held at {copy.slot.as_posix()}")
    return bool(oos or held)


def _projects_for_isolation(config_path: Path) -> dict[str, ConfigProject]:
    """Return committed mappings, falling back to the config file.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        Config projects whose runtime-home attics are listed for held copies.
    """
    snapshot = load_snapshot(config_path)
    if snapshot is not None:
        return snapshot
    return load_set_projects(config_path)
