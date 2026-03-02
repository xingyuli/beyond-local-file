"""Project processing utilities for CLI commands."""

from collections.abc import Callable
from pathlib import Path

import click

from .config import Config
from .formatters import CheckResultFormatter, SyncResultFormatter
from .models import Project, ProjectConfiguration
from .symlink_manager import Action, SymlinkManager


def get_absolute_path(path: str) -> str:
    """Resolve a path to its absolute form.

    Args:
        path: A file or directory path.

    Returns:
        Absolute path as a string.
    """
    return str(Path(path).resolve())


def load_config(config: str, project_name: str | None = None) -> dict[str, ProjectConfiguration] | None:
    """Load configuration and return project data.

    Args:
        config: Path to the YAML configuration file.
        project_name: Optional project name to filter. If provided, only
                    returns configuration for that project.

    Returns:
        Dictionary mapping project names to ProjectConfiguration objects.
        Returns None if loading failed.
    """
    config_path = get_absolute_path(config)

    if not Path(config_path).exists():
        click.echo(f"Config file not found: {config_path}")
        return None

    try:
        cfg = Config(config_path)
        cfg.load()
        return cfg.get_projects(project_name)
    except Exception as e:
        click.echo(str(e))
        return None


class ProjectProcessor:
    """Processes projects for sync and check operations.

    This class encapsulates the common logic for validating and processing
    projects, reducing duplication between CLI commands.
    """

    def __init__(self, projects_data: dict[str, ProjectConfiguration]):
        """Initialize the processor with project data.

        Args:
            projects_data: Dictionary mapping project names to ProjectConfiguration objects.
        """
        self.projects_data = projects_data

    def process_all(self, operation: Callable[[Project, Path], bool], skip_invalid: bool = True) -> bool:
        """Process all projects with the given operation.

        Args:
            operation: Function that takes (project, target_path)
                      and returns True to continue, False to abort.
            skip_invalid: Whether to skip invalid projects or stop processing.

        Returns:
            True if all operations completed, False if aborted.
        """
        for proj_name, proj_config in self.projects_data.items():
            project_dir = proj_config.project_path
            target_paths = proj_config.targets

            if not project_dir.exists():
                click.echo(f"Project directory does not exist: {project_dir}")
                if not skip_invalid:
                    return False
                continue

            project = Project.from_directory(proj_name, project_dir)

            if not project.items:
                click.echo(f"No items found in {project.name}")
                if not skip_invalid:
                    return False
                continue

            for target_path in target_paths:
                if not target_path.exists():
                    click.echo(f"Target directory does not exist: {target_path}")
                    continue

                click.echo(f"\nProcessing {proj_name} -> {target_path}")

                if not operation(project, target_path):
                    return False

        return True


class SyncOperation:
    """Encapsulates the sync operation logic."""

    def __init__(self, ask_callback: Callable[[str], Action] | None = None):
        """Initialize the sync operation.

        Args:
            ask_callback: Optional callback for handling existing paths.
        """
        self.ask_callback = ask_callback

    def execute(self, project: Project, target_path: Path) -> bool:
        """Execute the sync operation.

        Args:
            project: The project to sync.
            target_path: The target directory for symlinks.

        Returns:
            True to continue, False if aborted.
        """
        manager = SymlinkManager(project, target_path)
        result = manager.sync(self.ask_callback)

        formatter = SyncResultFormatter(project, result)
        formatter.format(project.name, target_path)

        if result.aborted:
            click.echo("Aborted by user")
            return False

        return True


class CheckOperation:
    """Encapsulates the check operation logic."""

    def __init__(self, show_extra: bool = False):
        """Initialize the check operation.

        Args:
            show_extra: Whether to show extra exclude entries.
        """
        self.show_extra = show_extra

    def execute(self, project: Project, target_path: Path) -> bool:
        """Execute the check operation.

        Args:
            project: The project to check.
            target_path: The target directory to check.

        Returns:
            Always True to continue processing.
        """
        manager = SymlinkManager(project, target_path)
        result = manager.check()

        formatter = CheckResultFormatter(result, self.show_extra)
        formatter.format(project.name, target_path)

        return True
