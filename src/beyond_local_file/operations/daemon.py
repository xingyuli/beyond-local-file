"""daemon subcommands — start, stop, status, logs, and reload."""

from __future__ import annotations

from pathlib import Path

import click

from beyond_local_file.configuration_set import (
    ConfigError,
    ConfigurationSet,
    configuration_set_for_shell,
    configuration_set_for_start,
)
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
)
from beyond_local_file.daemon.ipc import RequestSession
from beyond_local_file.daemon.oos_held import list_oos_and_held
from beyond_local_file.daemon.process import (
    follow_logs,
    is_running,
    print_status,
    read_pid,
    spawn_and_wait,
    spawn_worker,
    stop_process,
)
from beyond_local_file.daemon.resolve_ui import resolve_ui_url
from beyond_local_file.daemon.runtime import run_worker
from beyond_local_file.daemon.screen import (
    ScreenSkip,
    removal_confirm_question,
    run_shell_screen,
)
from beyond_local_file.daemon.store import load_baseline, load_snapshot
from beyond_local_file.model.config import ConfigProject


def start_daemon(config: str | None, *, worker: bool) -> int:
    """Start the daemon or run the worker loop.

    Args:
        config: Optional ``--config`` path.
        worker: When True, run the in-process worker instead of spawning.

    Returns:
        Process exit code.
    """
    asked = configuration_set_for_start(config)
    if asked is None:
        return 1
    if worker:
        return run_worker(asked.identity)
    refused = _refuse_start(asked)
    if refused is not None:
        return refused
    if shell_wants_screen():
        return _start_on_screen(asked.identity)
    return _start_off_screen(asked.identity)


def _refuse_start(asked: ConfigurationSet) -> int | None:
    """Return an exit code when this identity is running, overlapping, or unloadable."""
    if is_running(asked.identity):
        click.echo(f"Error: daemon is already running (pid {read_pid(asked.identity)})")
        return 1
    overlap = asked.running_overlap()
    if overlap is not None:
        owner = "global set" if ConfigurationSet(overlap.identity).is_global else f"set {overlap.identity}"
        click.echo(
            f"Error: mapping file {overlap.mapping_file} is already loaded by the running {owner} (pid {overlap.pid})"
        )
        return 1
    try:
        asked.projects()
    except ConfigError as error:
        _echo_config_error(asked, error)
        return 1
    return None


def _start_off_screen(config_path: Path) -> int:
    """Confirm ingest on stdin, print out-of-sync and held-copy WARNINGs, then spawn without a shell screen."""
    ingest_code = ingest_before_start(config_path)
    if ingest_code != 0:
        return ingest_code
    _echo_oos_and_held(config_path, warning=True)
    return spawn_and_wait(config_path)


def _start_on_screen(config_path: Path) -> int:
    """Ask start questions on the shell screen, then spawn and wait through ready."""
    code, file_projects, snapshot_projects, diff = prepare_ingest(config_path, confirm=False)
    if code != 0:
        return code
    questions = []
    if diff is not None and diff.removals:
        questions.append(removal_confirm_question(format_removal_plan(diff.removals)))
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
    asked = configuration_set_for_shell(config)
    if asked is None:
        return 1
    if not is_running(asked.identity):
        click.echo(DAEMON_DOWN_HINT)
        return 1
    on_screen = shell_wants_screen()
    try:
        code, file_projects, snapshot_projects, diff = prepare_ingest(
            asked.identity,
            confirm=not on_screen,
        )
    except ConfigError as error:
        _echo_config_error(asked, error)
        code, file_projects, snapshot_projects, diff = 1, None, None, None
    if code != 0:
        return code
    if snapshot_projects is None:
        click.echo("Error: mapping snapshot is missing")
        return 1
    _echo_oos_and_held(asked.identity, warning=True)
    no_diff = diff is None or file_projects is None or snapshot_projects is None
    questions = []
    if on_screen and diff is not None and diff.removals:
        questions.append(removal_confirm_question(format_removal_plan(diff.removals)))
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
        asked.identity,
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
    asked = configuration_set_for_shell(config)
    if asked is None:
        return 1
    return stop_process(asked.identity)


def status_daemon(config: str | None) -> int:
    """Print whether the daemon is running, plus out-of-sync paths and held copies.

    Args:
        config: Optional ``--config`` path.

    Returns:
        Process exit code.
    """
    asked = configuration_set_for_shell(config)
    if asked is None:
        return 1
    try:
        lines = _oos_and_held_lines(asked.identity, warning=False)
    except ConfigError as error:
        _echo_config_error(asked, error)
        return 1
    url = resolve_ui_url(asked.identity) if lines else None
    if url:
        lines.append(url)
    listing_lines = tuple(lines)
    if shell_wants_screen() and is_running(asked.identity):
        return call_daemon(
            asked.identity,
            {"op": "status", "pid": read_pid(asked.identity)},
            trailer=listing_lines,
        )
    code = print_status(asked.identity)
    for line in listing_lines:
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
    asked = configuration_set_for_shell(config)
    if asked is None:
        return 1
    return follow_logs(asked.identity, record)


def _echo_oos_and_held(config_path: Path, *, warning: bool) -> bool:
    """Print out-of-sync paths and held-copy clauses.

    Args:
        config_path: Path to the loaded config file.
        warning: When True, prefix lines with ``WARNING:``.

    Returns:
        True when any out-of-sync path or held copy was printed.
    """
    lines = _oos_and_held_lines(config_path, warning=warning)
    for line in lines:
        click.echo(line)
    return bool(lines)


def _oos_and_held_lines(config_path: Path, *, warning: bool) -> list[str]:
    """Return out-of-sync and held-copy lines for the shell or the screen."""
    listing = list_oos_and_held(load_baseline(config_path) or {}, _committed_projects(config_path))
    lines: list[str] = []
    prefix = "WARNING: " if warning else ""
    if listing.oos:
        if not warning:
            lines.append("Out-of-sync:")
        for row in listing.oos:
            if warning:
                lines.append(f"{prefix}out-of-sync {row.replica.as_posix()} {row.rel}")
                if row.clause:
                    lines.append(f"{prefix}{row.clause}")
            else:
                lines.append(f"  {row.replica.as_posix()}  {row.rel}")
                if row.clause:
                    lines.append(f"  {row.clause}")
    if listing.held:
        if not warning:
            lines.append("Held copies:")
        for copy in listing.held:
            lines.append(f"{prefix}{copy.clause}" if warning else f"  {copy.clause}")
            lines.append(f"Held at {copy.slot.as_posix()}")
    return lines


def _committed_projects(config_path: Path) -> dict[str, ConfigProject]:
    """Return committed mappings, falling back to the config file.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        Config projects whose runtime-home attics are listed for held copies.
    """
    snapshot = load_snapshot(config_path)
    if snapshot is not None:
        return snapshot
    return ConfigurationSet(config_path).projects()


def _echo_config_error(asked: ConfigurationSet, error: ConfigError) -> None:
    """Print a mapping-load error, matching the former load_config_projects strings."""
    if asked.is_global:
        click.echo(f"Error: {error}")
        return
    click.echo(str(error))
