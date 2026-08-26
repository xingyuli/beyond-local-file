"""CLI tool for managing links between project directories and target locations.

This tool provides commands to synchronize symlinks (and physical file copies)
and check their status, with automatic Git exclude file management.
"""

import os
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import click


def _configure_windows_console_encoding() -> None:
    """Use UTF-8 for stdout/stderr so Rich and Unicode status glyphs render on Windows."""
    if os.name != "nt":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass

from . import __version__
from .completion import complete_project_names
from .operations import (
    CheckOperation,
    CreateOperation,
    SyncOperation,
    run_upgrade,
)
from .operations.remove import RemoveFormatter, RemoveOperation
from .operations.revlink import CreateFormatter, RestoreFormatter, RestoreOperation
from .options import ConflictResolution, CopyConflictResolution, OutputFormat
from .project_processor import (
    ProjectProcessor,
    RevlinkResolveError,
    load_config_projects,
    resolve_revlink_context,
)


def ask_user_for_action(target_path: str, expected_source: str | None = None) -> ConflictResolution:
    """Prompt user for action when a path already exists.

    Args:
        target_path: The path that already exists.
        expected_source: The expected source path that the symlink should point to.

    Returns:
        The user's chosen action: SKIP, OVERWRITE, or ABORT.
    """
    options = ", ".join(f"{a.value}-{a.name.lower()}" for a in ConflictResolution)
    choices = [str(a.value) for a in ConflictResolution]
    default = str(ConflictResolution.SKIP.value)

    click.echo(f"\nThe path of {target_path} already exists.")

    # Show what it should be
    if expected_source:
        click.echo("\nShould be:")
        click.echo(f"  (a link to) {expected_source}")

    # Show what the current path is
    target = Path(target_path)
    if target.is_symlink():
        current_target = target.readlink()
        click.echo("\nBut was:")
        click.echo(f"  (a link to) {current_target}")
    elif target.is_dir():
        click.echo("\nBut was:")
        click.echo("  (a directory)")
    elif target.is_file():
        click.echo("\nBut was:")
        click.echo("  (a regular file)")

    choice = click.prompt(
        f"\nWhat do you want to do? ({options})",
        type=click.Choice(choices),
        show_choices=True,
        default=default,
    )
    return ConflictResolution(int(choice))


def ask_user_for_conflict(managed_file: Path, target_file: Path) -> CopyConflictResolution:
    """Prompt user to resolve a bidirectional copy conflict.

    Args:
        managed_file: Path to the managed (source) file.
        target_file: Path to the target (copied) file.

    Returns:
        The user's chosen resolution: MANAGED, TARGET, or SKIP.
    """
    click.echo("\nConflict detected: both managed and target files have changed")
    click.echo(f"  managed: {managed_file}")
    click.echo(f"  target:  {target_file}")

    # Derive shortcut and label from enum values: "managed" → "[m]anaged"
    resolution_map = {m.value[0]: m for m in CopyConflictResolution}
    prompt_options = " / ".join(f"[{k}]{m.value[1:]}" for k, m in resolution_map.items())
    default = CopyConflictResolution.SKIP.value[0]

    choice = click.prompt(
        f"\nChoose resolution: {prompt_options}",
        type=click.Choice(list(resolution_map)),
        show_choices=False,
        default=default,
    )
    return resolution_map[choice]


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
    """Link management commands (symlinks and file copies)."""
    pass


@link.command()
@click.argument("project_name", required=False, shell_complete=complete_project_names)
@click.pass_context
def sync(ctx, project_name):
    """Synchronize links from project directory to target locations.

    Creates symlinks (or physical copies for items marked with copy: true)
    for all items in the project directory to each target location specified
    in the config.
    """
    config = ctx.obj["config"]
    result = load_config_projects(config, project_name)
    if result is None:
        ctx.exit(1)

    operation = SyncOperation(result.config_file.parent, ask_user_for_action, ask_user_for_conflict)
    ProjectProcessor.process_all_units(result.projects, operation)


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

    Displays the status of symlinks, file copies, and Git exclude entries
    for each project and target location.
    """
    config = ctx.obj["config"]
    result = load_config_projects(config, project_name)
    if result is None:
        ctx.exit(1)

    operation = CheckOperation(result.config_file.parent, extra_exclude, OutputFormat(output_format))
    ProjectProcessor.process_all_units(result.projects, operation)
    operation.render()


@cli.command()
@click.option("--dry-run", is_flag=True, help="Show the upgrade command without executing it.")
@click.pass_context
def upgrade(ctx, dry_run):
    """Upgrade beyond-local-file to the latest version.

    Detects whether the tool was installed via ``uv tool`` or ``pipx`` and
    runs the appropriate upgrade command automatically. Use ``--dry-run`` to
    preview the command without executing it.
    """
    exit_code = run_upgrade(dry_run=dry_run)
    ctx.exit(exit_code)


@cli.command("remove")
@click.argument("path")
@click.option("--dry-run", is_flag=True, help="Preview permanent removal without modifying the filesystem.")
@click.pass_context
def remove(ctx, path, dry_run):
    """Permanently remove one managed item and every validated projection."""
    formatter = RemoveFormatter(dry_run=dry_run)
    # resolve() normalises Windows short (8.3) vs long path forms so that
    # relative_to and target matching stay consistent with config paths.
    cwd = Path.cwd().resolve()
    candidate = Path(path)
    candidate = candidate if candidate.is_absolute() else cwd / candidate
    source = Path(os.path.normpath(candidate))

    try:
        rel_path = source.relative_to(cwd)
    except ValueError:
        formatter.error(f"PATH must be inside the current directory: {path}")
        ctx.exit(1)
        return

    resolver_output = StringIO()
    with redirect_stdout(resolver_output):
        ctx_result = resolve_revlink_context(ctx.obj["config"], cwd)
    for line in resolver_output.getvalue().splitlines():
        formatter.info(line)
    if isinstance(ctx_result, RevlinkResolveError):
        if ctx_result.message is not None:
            formatter.error(ctx_result.message)
        ctx.exit(ctx_result.exit_code)
        return

    exit_code = RemoveOperation(
        source=source,
        rel_path=rel_path,
        dry_run=dry_run,
        formatter=formatter,
        context=ctx_result,
    ).run()
    ctx.exit(exit_code)


@cli.group()
def revlink():
    """Manage the lifecycle of files adopted into the managed project."""
    pass


def _exit_on_revlink_error(ctx: click.Context, result: RevlinkResolveError) -> None:
    """Emit the error message (if any) and call ctx.exit with the error's exit code.

    Args:
        ctx: The active Click context; used to exit with the correct code.
        result: The resolution error returned by :func:`resolve_revlink_context`.
    """
    if result.message is not None:
        click.echo(result.message)
    ctx.exit(result.exit_code)


@revlink.command("create")
@click.argument("path")
@click.option("--dry-run", is_flag=True, help="Preview actions without modifying the filesystem.")
@click.option("--force", is_flag=True, help="Overwrite existing destination in managed project.")
@click.pass_context
def revlink_create(ctx, path, dry_run, force):
    """Convert an existing file or directory into a managed symlink.

    Copies PATH to the managed project, verifies the copy via MD5 checksum,
    replaces the original with a symlink, and records the item in
    .git/info/exclude if the target directory is a Git repository.
    """
    source = Path(path).resolve()
    # resolve() normalises Windows short (8.3) vs long path forms so that
    # relative_to and target matching stay consistent with config paths.
    cwd = Path.cwd().resolve()

    try:
        rel_path = source.relative_to(cwd)
    except ValueError:
        click.echo(f"Error: PATH must be inside the current directory: {path}")
        ctx.exit(1)
        return

    ctx_result = resolve_revlink_context(ctx.obj["config"], cwd)
    if isinstance(ctx_result, RevlinkResolveError):
        _exit_on_revlink_error(ctx, ctx_result)
        return

    exit_code = CreateOperation(
        source=source,
        dest_root=ctx_result.managed_project_path,
        rel_path=rel_path,
        dry_run=dry_run,
        force=force,
        formatter=CreateFormatter(dry_run=dry_run),
        context=ctx_result,
    ).run()
    ctx.exit(exit_code)


@revlink.command("restore")
@click.argument("path")
@click.option("--dry-run", is_flag=True, help="Preview actions without modifying the filesystem.")
@click.pass_context
def revlink_restore(ctx, path, dry_run):
    """Dissolve a managed symlink and recover the real file from the managed project.

    Copies the managed copy back to PATH, verifies integrity via MD5 checksum,
    deletes the managed copy, removes the item from .git/info/exclude, and
    removes the entry from the config subpath list if selective sync is active.
    """
    # resolve() normalises Windows short (8.3) vs long path forms so that
    # relative_to and target matching stay consistent with config paths.
    cwd = Path.cwd().resolve()
    # Use absolute() instead of resolve() on the source so that symlinks are
    # not followed — the source must be the symlink path itself, not the
    # managed copy it points to.  Build from the already-resolved cwd so the
    # absolute form shares the same prefix.
    source = (cwd / path).absolute()

    try:
        rel_path = source.relative_to(cwd)
    except ValueError:
        click.echo(f"Error: PATH must be inside the current directory: {path}")
        ctx.exit(1)
        return

    ctx_result = resolve_revlink_context(ctx.obj["config"], cwd)
    if isinstance(ctx_result, RevlinkResolveError):
        _exit_on_revlink_error(ctx, ctx_result)
        return

    exit_code = RestoreOperation(
        source=source,
        dest_root=ctx_result.managed_project_path,
        rel_path=rel_path,
        dry_run=dry_run,
        formatter=RestoreFormatter(dry_run=dry_run),
        context=ctx_result,
    ).run()
    ctx.exit(exit_code)


if __name__ == "__main__":
    cli()
