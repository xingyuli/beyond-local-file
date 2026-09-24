"""daemon subcommands — start, stop, status, logs, and reload."""

from __future__ import annotations

from pathlib import Path

import click

from beyond_local_file.blfrc import is_global_config_path
from beyond_local_file.daemon.client import (
    DAEMON_DOWN_HINT,
    call_daemon,
    open_wait_session,
    shell_wants_screen,
)
from beyond_local_file.daemon.ingest import (
    affected_unit_names,
    commit_ingest,
    format_removal_plan,
    ingest_before_start,
    prepare_ingest,
    stdin_is_tty,
)
from beyond_local_file.daemon.ipc import RequestSession
from beyond_local_file.daemon.process import (
    follow_logs,
    is_running,
    overlapping_running_set,
    print_status,
    read_pid,
    spawn_and_wait,
    spawn_worker,
    stop_process,
)
from beyond_local_file.daemon.runtime import run_worker
from beyond_local_file.daemon.screen import (
    ScreenSkip,
    isolation_ack_question,
    removal_confirm_question,
    run_shell_screen,
)
from beyond_local_file.daemon.store import get_state, iter_out_of_sync, load_baseline, load_snapshot
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
    if shell_wants_screen():
        return _start_on_screen(result.config_file)
    return _start_off_screen(result.config_file)


def _start_off_screen(config_path: Path) -> int:
    """Confirm ingest and isolation on stdin, then spawn without a shell screen."""
    ingest_code = ingest_before_start(config_path)
    if ingest_code != 0:
        return ingest_code
    _warn_and_ack_isolation(config_path)
    return spawn_and_wait(config_path)


def _start_on_screen(config_path: Path) -> int:
    """Ask start questions on the shell screen, then spawn and wait through ready."""
    code, file_projects, snapshot_projects, diff = prepare_ingest(config_path, confirm=False)
    if code != 0:
        return code
    iso_lines = _isolation_lines(config_path, warning=True)
    questions = []
    if diff is not None and diff.removals:
        questions.append(removal_confirm_question(format_removal_plan(diff.removals)))
    if iso_lines:
        questions.append(isolation_ack_question(iso_lines))
    if not questions:
        if commit_ingest(config_path, file_projects, snapshot_projects, diff) != 0:
            return 1
        return spawn_and_wait(config_path)

    def connect(answers: tuple[str, ...]) -> RequestSession:
        if diff is not None and diff.removals and answers[0] == "n":
            raise ScreenSkip("Mapping changes were not applied\n")
        if commit_ingest(config_path, file_projects, snapshot_projects, diff) != 0:
            raise ScreenSkip("Mapping changes were not applied\n")
        if spawn_worker(config_path) != 0:
            raise ScreenSkip("Error: daemon failed to start\n")
        return open_wait_session(config_path)

    return run_shell_screen({"op": "wait"}, questions=tuple(questions), connect=connect)


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
    on_screen = shell_wants_screen()
    code, file_projects, snapshot_projects, diff = prepare_ingest(
        result.config_file,
        confirm=not on_screen,
    )
    if code != 0:
        return code
    if snapshot_projects is None:
        click.echo("Error: mapping snapshot is missing")
        return 1
    iso_lines = _isolation_lines(result.config_file, warning=True)
    if not on_screen:
        _ack_isolation(iso_lines)
    no_diff = diff is None or file_projects is None or snapshot_projects is None
    questions = []
    if on_screen and diff is not None and diff.removals:
        questions.append(removal_confirm_question(format_removal_plan(diff.removals)))
    if on_screen and iso_lines:
        questions.append(isolation_ack_question(iso_lines))
    if no_diff and not questions:
        click.echo("Mappings already match the snapshot")
        return 0
    names = () if no_diff else sorted(affected_unit_names(snapshot_projects, file_projects, diff))
    target = names[0] if len(names) == 1 else "all projects"
    request = {
        "op": "reload",
        "confirmed": False if questions else bool(diff is not None and diff.removals),
        "screen_target": target,
    }

    def apply_answers(answers: tuple[str, ...], pending: dict) -> ScreenSkip | None:
        index = 0
        if diff is not None and diff.removals:
            if answers[index] == "n":
                return ScreenSkip("Mapping changes were not applied\n")
            pending["confirmed"] = True
            index += 1
        if no_diff:
            return ScreenSkip("Mappings already match the snapshot\n", exit_code=0)
        return None

    return call_daemon(
        result.config_file,
        request,
        questions=tuple(questions),
        apply_answers=apply_answers if questions else None,
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
    iso = tuple(_isolation_lines(result.config_file, warning=False))
    if shell_wants_screen() and is_running(result.config_file):
        return call_daemon(
            result.config_file,
            {"op": "status", "pid": read_pid(result.config_file)},
            trailer=iso,
        )
    code = print_status(result.config_file)
    for line in iso:
        click.echo(line)
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
    _ack_isolation(_isolation_lines(config_path, warning=True))


def _ack_isolation(lines: list[str]) -> None:
    """Print *lines* and, on a TTY, require ack without aborting."""
    if not lines:
        return
    for line in lines:
        click.echo(line)
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
    lines = _isolation_lines(config_path, warning=warning)
    for line in lines:
        click.echo(line)
    return bool(lines)


def _isolation_lines(config_path: Path, *, warning: bool) -> list[str]:
    """Return out-of-sync and held-copy lines for the shell or the screen."""
    trees = load_baseline(config_path) or {}
    oos = iter_out_of_sync(trees)
    held = [
        copy
        for project in _projects_for_isolation(config_path).values()
        for copy in list_held_copies(project.managed_project_path)
    ]
    lines: list[str] = []
    prefix = "WARNING: " if warning else ""
    if oos:
        if not warning:
            lines.append("Out-of-sync:")
        for replica, rel in oos:
            clause = str(get_state(trees, replica, rel).get("clause") or "")
            if warning:
                lines.append(f"{prefix}out-of-sync {replica.as_posix()} {rel}")
                if clause:
                    lines.append(f"{prefix}{clause}")
            else:
                lines.append(f"  {replica.as_posix()}  {rel}")
                if clause:
                    lines.append(f"  {clause}")
    if held:
        if not warning:
            lines.append("Held copies:")
        for copy in held:
            lines.append(f"{prefix}{copy.clause}" if warning else f"  {copy.clause}")
            lines.append(f"Held at {copy.slot.as_posix()}")
    return lines


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
