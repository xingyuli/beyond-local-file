"""CLI tool for managing links between project directories and target locations.

This tool provides commands to synchronize physical copies of managed items
and check their status, with automatic Git exclude file management.
"""

import os
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

import click

from . import __version__
from .completion import complete_project_names
from .contribution import contribution_owner, projects_targeting
from .daemon.client import call_daemon
from .operations.daemon import (
    follow_blf_logs,
    follow_daemon_logs,
    reload_daemon,
    start_daemon,
    status_daemon,
    stop_daemon,
)
from .operations.upgrade import run_upgrade
from .options import OutputFormat
from .project_processor import load_config_projects


def _configure_windows_console_encoding() -> None:
    """Use UTF-8 for stdout/stderr so Rich and Unicode status glyphs render on Windows."""
    if os.name != "nt":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        with suppress(OSError, ValueError):
            reconfigure(encoding="utf-8")


@click.group()
@click.version_option(version=__version__, prog_name="beyond-local-file")
@click.option(
    "-c",
    "--config",
    default=None,
    help="Path to config file",
)
@click.pass_context
def cli(ctx, config):
    """Manage links between project directories and target locations."""
    _configure_windows_console_encoding()
    ctx.ensure_object(dict)
    ctx.obj["config"] = config


@cli.group()
def link():
    """Link management commands (physical copies of managed items)."""
    pass


@link.command()
@click.argument("project_name", required=False, shell_complete=complete_project_names)
@click.option("--extra-exclude", is_flag=True, help="Show extra entries in git exclude file")
@click.option(
    "--format",
    "output_format",
    type=click.Choice([f.value for f in OutputFormat]),
    default=OutputFormat.TABLE.value,
    show_default=True,
    help="Output format: table (compact) or verbose (detailed per-project).",
)
@click.pass_context
def check(ctx, project_name, extra_exclude, output_format):
    """Check link status and Git exclude configuration.

    Displays the daemon's view of copy projections and Git exclude entries
    for each project and target location.
    """
    _call_daemon(
        ctx,
        {
            "op": "check",
            "project_name": project_name,
            "extra_exclude": extra_exclude,
            "output_format": output_format,
        },
    )


@cli.command()
@click.option("--dry-run", is_flag=True, help="Show the upgrade command without executing it.")
@click.pass_context
def upgrade(ctx, dry_run):
    """Upgrade beyond-local-file to the latest version.

    Detects whether the tool was installed via ``uv tool`` or ``pipx`` and
    runs the appropriate upgrade command automatically. Use ``--dry-run`` to
    preview the command without executing it.
    """
    exit_code = run_upgrade(dry_run=dry_run, config=ctx.obj["config"])
    ctx.exit(exit_code)


@cli.command("remove")
@click.argument("path")
@click.option("--dry-run", is_flag=True, help="Preview permanent removal without modifying the filesystem.")
@click.pass_context
def remove(ctx, path, dry_run):
    """Permanently remove one managed item and every validated projection."""
    cwd = _cwd_containing(ctx, path)
    _call_daemon(
        ctx,
        {
            "op": "remove",
            "cwd": str(cwd),
            "path": path,
            "dry_run": dry_run,
        },
    )


@cli.command("logs")
@click.argument(
    "record",
    required=False,
    type=click.Choice(["requests", "idle", "daemon"]),
)
@click.pass_context
def logs(ctx, record):
    """Follow idle, request, and daemon logs. Ctrl-C stops following, not the daemon."""
    ctx.exit(follow_blf_logs(ctx.obj["config"], record))


@cli.group()
def daemon():
    """Run one background process that catch-up's copy projections."""
    pass


@daemon.command("start")
@click.option("--worker", is_flag=True, hidden=True)
@click.pass_context
def daemon_start(ctx, worker):
    """Start the daemon in the background."""
    ctx.exit(start_daemon(ctx.obj["config"], worker=worker))


@daemon.command("stop")
@click.pass_context
def daemon_stop(ctx):
    """Stop the running daemon."""
    ctx.exit(stop_daemon(ctx.obj["config"]))


@daemon.command("status")
@click.pass_context
def daemon_status(ctx):
    """Show whether the daemon is running, plus out-of-sync paths and held copies."""
    ctx.exit(status_daemon(ctx.obj["config"]))


@daemon.command("logs")
@click.pass_context
def daemon_logs(ctx):
    """Retired. Use ``blf logs``."""
    ctx.exit(follow_daemon_logs(ctx.obj["config"]))


@daemon.command("reload")
@click.pass_context
def daemon_reload(ctx):
    """Apply external mapping edits from the config file."""
    ctx.exit(reload_daemon(ctx.obj["config"]))


@cli.group()
def revlink():
    """Manage the lifecycle of files adopted into the managed project."""
    pass


@revlink.command("create")
@click.argument("path")
@click.option("--dry-run", is_flag=True, help="Preview actions without modifying the filesystem.")
@click.option("--force", is_flag=True, help="Overwrite existing destination in managed project.")
@click.pass_context
def revlink_create(ctx, path, dry_run, force):
    """Adopt an existing file or directory as a copy projection.

    Copies PATH to the managed project, verifies the copy via MD5 checksum,
    leaves the original as a regular file or directory, and records the item in
    .git/info/exclude if the target directory is a Git repository.
    """
    cwd = _cwd_containing(ctx, path, resolve_source=True)
    project_name = _choose_create_project(ctx, cwd, path)
    _call_daemon(
        ctx,
        {
            "op": "create",
            "cwd": str(cwd),
            "path": path,
            "dry_run": dry_run,
            "force": force,
            "project_name": project_name,
        },
    )


@revlink.command("restore")
@click.argument("path")
@click.option("--dry-run", is_flag=True, help="Preview actions without modifying the filesystem.")
@click.pass_context
def revlink_restore(ctx, path, dry_run):
    """Stop managing PATH and leave the target file in place.

    Deletes the managed copy, leaves PATH as a regular file or directory,
    leaves other targets' copies as unmanaged files, removes the item from
    .git/info/exclude, and removes the entry from the config subpath list if
    selective sync is active.
    """
    cwd = _cwd_containing(ctx, path, resolve_source=False)
    _call_daemon(
        ctx,
        {
            "op": "restore",
            "cwd": str(cwd),
            "path": path,
            "dry_run": dry_run,
        },
    )


def _choose_create_project(ctx: click.Context, cwd: Path, path: str) -> str | None:
    """Return the hub for ``revlink create``, interviewing when PATH is new.

    Args:
        ctx: Active Click context carrying ``--config``.
        cwd: Resolved current working directory (the target).
        path: User-supplied path argument.

    Returns:
        The chosen managed project name, or ``None`` when no project targets
        ``cwd`` (the daemon still reports that).
    """
    loaded = load_config_projects(ctx.obj["config"])
    if loaded is None:
        ctx.exit(1)
        return None
    matches = projects_targeting(loaded.projects, cwd)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0].managed_project_name
    source = Path(path).resolve()
    rel = source.relative_to(cwd).as_posix()
    owner = contribution_owner(loaded.projects, cwd, rel)
    if owner is not None:
        return owner.managed_project_name
    names = [project.managed_project_name for project in matches]
    chosen = _interview_create_project(names)
    if chosen is None:
        click.echo("Error: more than one managed project contributes to this directory: " + ", ".join(names))
        ctx.exit(1)
        return None
    return chosen


def _interview_create_project(names: list[str]) -> str | None:
    """Prompt for a 1-based hub choice. Return ``None`` when stdin cannot answer.

    Args:
        names: Managed project names in stable order.

    Returns:
        The chosen name, or ``None`` when there is no TTY/input or the prompt
        is aborted.
    """
    if not _stdin_can_prompt():
        return None
    click.echo("More than one managed project contributes to this directory:")
    for index, name in enumerate(names, start=1):
        click.echo(f"  {index}. {name}")
    choices = click.Choice([str(index) for index in range(1, len(names) + 1)])
    try:
        selected = click.prompt("Choose a managed project", type=choices, show_choices=False)
    except (EOFError, OSError, click.Abort):
        return None
    return names[int(selected) - 1]


def _stdin_can_prompt() -> bool:
    """Return whether stdin is a TTY or a test/pipe stream with unread input."""
    try:
        if sys.stdin.isatty():
            return True
    except ValueError:
        return False
    try:
        position = sys.stdin.tell()
        chunk = sys.stdin.read(1)
        sys.stdin.seek(position)
    except OSError:
        return False
    return bool(chunk)


def _cwd_containing(ctx: click.Context, path: str, *, resolve_source: bool = False) -> Path:
    """Return CWD after proving *path* is inside it.

    Args:
        ctx: Active Click context used to exit on a path error.
        path: User-supplied path argument.
        resolve_source: When True, follow symlinks the way ``revlink create`` does.

    Returns:
        Resolved current working directory.
    """
    cwd = Path.cwd().resolve()
    if resolve_source:
        source = Path(path).resolve()
    else:
        candidate = Path(path)
        candidate = candidate if candidate.is_absolute() else cwd / candidate
        source = Path(os.path.normpath(candidate))
    try:
        source.relative_to(cwd)
    except ValueError:
        click.echo(f"Error: PATH must be inside the current directory: {path}")
        ctx.exit(1)
    return cwd


def _call_daemon(ctx: click.Context, request: dict[str, Any]) -> None:
    """Load the config file and send *request* to the running daemon.

    Args:
        ctx: Active Click context carrying ``--config``.
        request: JSON-serialisable daemon request.
    """
    result = load_config_projects(ctx.obj["config"])
    if result is None:
        ctx.exit(1)
        return
    ctx.exit(call_daemon(result.config_file, request))


if __name__ == "__main__":
    cli()
