"""CLI tool for managing links between project directories and target locations.

This tool provides commands to synchronize symlinks (and physical file copies)
and check their status, with automatic Git exclude file management.
"""

from pathlib import Path

import click

from . import __version__
from .completion import complete_project_names
from .operations import (
    CheckOperation,
    CreateOperation,
    SyncOperation,
    run_upgrade,
)
from .operations.revlink import CreateFormatter, RestoreFormatter, RestoreOperation, RevlinkContext
from .options import ConflictResolution, CopyConflictResolution, OutputFormat
from .project_processor import (
    ProjectProcessor,
    load_config_projects,
    resolve_project_from_cwd,
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
    """Convert an existing file or directory into a managed symlink.

    Copies PATH to the managed project, verifies the copy via MD5 checksum,
    replaces the original with a symlink, and records the item in
    .git/info/exclude if the target directory is a Git repository.
    """
    source = Path(path).resolve()
    config = ctx.obj["config"]

    result = load_config_projects(config)
    if result is None:
        ctx.exit(1)
        return

    cwd = Path.cwd()
    project = resolve_project_from_cwd(result.projects, cwd)

    if project is None:
        hint = (
            "Hint: add a target entry for this directory in your config, "
            "or use --config to specify the correct config file."
        )
        click.echo(f"No managed project found for current directory: {cwd}\n{hint}")
        ctx.exit(1)
        return

    if isinstance(project, list):
        names = ", ".join(p.managed_project_name for p in project)
        click.echo(f"Ambiguous: multiple projects target {cwd}: {names}")
        ctx.exit(1)
        return

    # Find the specific mapping whose targets include CWD — needed for config update
    matched_mapping = next((m for m in project.mappings if cwd in m.targets), None)

    ctx_obj = (
        RevlinkContext(
            config_path=result.config_file,
            project_name=project.managed_project_name,
            matched_mapping=matched_mapping,
            cwd=cwd,
        )
        if matched_mapping is not None
        else None
    )

    exit_code = CreateOperation(
        source=source,
        dest_root=project.managed_project_path,
        dry_run=dry_run,
        force=force,
        formatter=CreateFormatter(dry_run=dry_run),
        context=ctx_obj,
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
    config = ctx.obj["config"]

    result = load_config_projects(config)
    if result is None:
        ctx.exit(1)
        return

    cwd = Path.cwd()
    # Use absolute() instead of resolve() so that symlinks are not followed —
    # the source must be the symlink path itself, not the managed copy it points to.
    source = (cwd / path).absolute()
    project = resolve_project_from_cwd(result.projects, cwd)

    if project is None:
        hint = (
            "Hint: add a target entry for this directory in your config, "
            "or use --config to specify the correct config file."
        )
        click.echo(f"No managed project found for current directory: {cwd}\n{hint}")
        ctx.exit(1)
        return

    if isinstance(project, list):
        names = ", ".join(p.managed_project_name for p in project)
        click.echo(f"Ambiguous: multiple projects target {cwd}: {names}")
        ctx.exit(1)
        return

    # Find the specific mapping whose targets include CWD — needed for config removal
    matched_mapping = next((m for m in project.mappings if cwd in m.targets), None)

    ctx_obj = (
        RevlinkContext(
            config_path=result.config_file,
            project_name=project.managed_project_name,
            matched_mapping=matched_mapping,
            cwd=cwd,
        )
        if matched_mapping is not None
        else None
    )

    exit_code = RestoreOperation(
        source=source,
        dest_root=project.managed_project_path,
        dry_run=dry_run,
        formatter=RestoreFormatter(dry_run=dry_run),
        context=ctx_obj,
    ).run()
    ctx.exit(exit_code)


if __name__ == "__main__":
    cli()
