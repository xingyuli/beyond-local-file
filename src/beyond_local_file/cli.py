"""CLI tool for managing symlinks between project directories and target locations.

This tool provides commands to synchronize symlinks and check their status,
with automatic Git exclude file management.
"""

from pathlib import Path

import click

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

    click.echo(f"\nThe link of {target_path} already exists.")

    # Show what it should be
    if expected_source:
        click.echo("\nShould be:")
        click.echo(f"  {expected_source}")

    # Show what the current path is
    target = Path(target_path)
    if target.is_symlink():
        current_target = target.readlink()
        click.echo("\nBut was:")
        click.echo(f"  {current_target}")
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


@click.group()
def cli():
    """Manage symlinks between project directories and target locations."""
    pass


@cli.group()
def symlink():
    """Symlink management commands."""
    pass


@symlink.command()
@click.argument("project_name", required=False)
@click.option("-c", "--config", default="config.yml", help="Path to config file")
def sync(project_name, config):
    """Synchronize symlinks from project directory to target locations.

    Creates symlinks for all items in the project directory to each target
    location specified in the config. If a target is a Git repository, the
    symlink names are automatically added to .git/info/exclude.
    """
    projects_data = load_config(config, project_name)
    if projects_data is None:
        return

    processor = ProjectProcessor(projects_data)
    operation = SyncOperation(ask_user_for_action)
    processor.process_all(operation)


@symlink.command()
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
    """Check symlink status and Git exclude configuration.

    Displays the status of symlinks and Git exclude entries for each project
    and target location. Shows which symlinks exist, are missing, and which
    exclude entries are present, missing, or extra.
    """
    projects_data = load_config(config, project_name)
    if projects_data is None:
        return

    processor = ProjectProcessor(projects_data)
    operation = CheckOperation(extra_exclude, OutputFormat(output_format))
    processor.process_all(operation)
    operation.render()


if __name__ == "__main__":
    cli()
