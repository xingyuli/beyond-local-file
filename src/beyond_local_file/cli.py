"""CLI tool for managing symlinks between project directories and target locations.

This tool provides commands to synchronize symlinks and check their status,
with automatic Git exclude file management.
"""

import click

from .project_processor import CheckOperation, ProjectProcessor, SyncOperation, load_config
from .symlink_manager import Action


def ask_user_for_action(target_path: str) -> Action:
    """Prompt user for action when a path already exists.

    Args:
        target_path: The path that already exists.

    Returns:
        The user's chosen action: SKIP, OVERWRITE, or ABORT.
    """
    options = ", ".join(f"{a.value}-{a.name.lower()}" for a in Action)
    choices = [str(a.value) for a in Action]
    default = str(Action.SKIP.value)

    click.echo(f"Path already exists: {target_path}")
    choice = click.prompt(
        f"What do you want to do? ({options})",
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

    Args:
        project_name: Optional project name to sync. If not provided, syncs all projects.
        config: Path to the YAML configuration file (default: config.yml).
    """
    projects_data = load_config(config, project_name)
    if projects_data is None:
        return

    processor = ProjectProcessor(projects_data)
    operation = SyncOperation(ask_user_for_action)
    processor.process_all(operation.execute)


@symlink.command()
@click.argument("project_name", required=False)
@click.option("-c", "--config", default="config.yml", help="Path to config file")
@click.option("--extra-exclude", is_flag=True, help="Show extra entries in git exclude file")
def check(project_name, config, extra_exclude):
    """Check symlink status and Git exclude configuration.

    Displays the status of symlinks and Git exclude entries for each project
    and target location. Shows which symlinks exist, are missing, and which
    exclude entries are present, missing, or extra.

    Args:
        project_name: Optional project name to check. If not provided, checks all projects.
        config: Path to the YAML configuration file (default: config.yml).
        extra_exclude: Flag to show extra entries in git exclude file that are not in the project.
    """
    projects_data = load_config(config, project_name)
    if projects_data is None:
        return

    processor = ProjectProcessor(projects_data)
    operation = CheckOperation(extra_exclude)
    processor.process_all(operation.execute)


if __name__ == "__main__":
    cli()
