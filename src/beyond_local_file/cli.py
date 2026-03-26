"""CLI tool for managing links between project directories and target locations.

This tool provides commands to synchronize symlinks (and physical file copies)
and check their status, with automatic Git exclude file management.
"""

from pathlib import Path

import click

from .copy_manager import CopyConflictAction
from .options import OutputFormat
from .project_processor import CheckOperation, ProjectProcessor, SyncOperation, load_config
from .symlink_manager import Action


def ask_user_for_action(target_path: str, expected_source: str | None = None) -> Action:
    """Prompt user for action when a path already exists.

    Args:
        target_path: The path that already exists.
        expected_source: The expected source path that the symlink should point to.

    Returns:
        The user's chosen action: SKIP, OVERWRITE, or ABORT.
    """
    options = ", ".join(f"{a.value}-{a.name.lower()}" for a in Action)
    choices = [str(a.value) for a in Action]
    default = str(Action.SKIP.value)

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
    return Action(int(choice))


def ask_user_for_conflict(managed_file: Path, target_file: Path) -> str:
    """Prompt user to resolve a bidirectional copy conflict.

    Args:
        managed_file: Path to the managed (source) file.
        target_file: Path to the target (copied) file.

    Returns:
        One of CopyConflictAction values: managed, target, or skip.
    """
    click.echo("\nConflict detected: both managed and target files have changed")
    click.echo(f"  managed: {managed_file}")
    click.echo(f"  target:  {target_file}")

    choice = click.prompt(
        "\nChoose resolution: [m]anaged / [t]arget / [s]kip",
        type=click.Choice(["m", "t", "s"]),
        show_choices=False,
        default="s",
    )
    resolution_map = {
        "m": CopyConflictAction.MANAGED,
        "t": CopyConflictAction.TARGET,
        "s": CopyConflictAction.SKIP,
    }
    return resolution_map[choice]


@click.group()
def cli():
    """Manage links between project directories and target locations."""
    pass


@cli.group()
def link():
    """Link management commands (symlinks and file copies)."""
    pass


# Backward compatibility: keep 'symlink' as an alias for 'link'
@cli.group("symlink", hidden=True)
def symlink():
    """Symlink management commands (alias for 'link')."""
    pass


@link.command()
@click.argument("project_name", required=False)
@click.option("-c", "--config", default="config.yml", help="Path to config file")
def sync(project_name, config):
    """Synchronize links from project directory to target locations.

    Creates symlinks (or physical copies for items marked with copy: true)
    for all items in the project directory to each target location specified
    in the config.
    """
    result = load_config(config, project_name)
    if result is None:
        return

    projects_data, config_dir = result
    processor = ProjectProcessor(projects_data, config_dir)
    operation = SyncOperation(config_dir, ask_user_for_action, ask_user_for_conflict)
    processor.process_all(operation)


@link.command()
@click.argument("project_name", required=False)
@click.option("-c", "--config", default="config.yml", help="Path to config file")
@click.option("--extra-exclude", is_flag=True, help="Show extra entries in git exclude file")
@click.option(
    "--format",
    "output_format",
    type=click.Choice([f.value for f in OutputFormat]),
    default=OutputFormat.TABLE.value,
    show_default=True,
    help="Output format: table (compact) or verbose (detailed per-project).",
)
def check(project_name, config, extra_exclude, output_format):
    """Check link status and Git exclude configuration.

    Displays the status of symlinks, file copies, and Git exclude entries
    for each project and target location.
    """
    result = load_config(config, project_name)
    if result is None:
        return

    projects_data, config_dir = result
    processor = ProjectProcessor(projects_data, config_dir)
    operation = CheckOperation(config_dir, extra_exclude, OutputFormat(output_format))
    processor.process_all(operation)
    operation.render()


# Register the same commands under the 'symlink' alias
symlink.add_command(sync, "sync")
symlink.add_command(check, "check")


if __name__ == "__main__":
    cli()
