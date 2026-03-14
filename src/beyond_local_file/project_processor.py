"""Project processing utilities for CLI commands."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

import click

from .config import Config
from .formatters import CheckResultFormatter, CheckRow, CheckTableFormatter, SyncResultFormatter
from .models import Project, ProjectConfiguration
from .options import OutputFormat
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


class CmdOperation(ABC):
    """Base class for CLI operations executed per project/target pair.

    Subclasses implement :meth:`execute` to perform the actual work, and may
    override :attr:`verbose_progress` to suppress the per-target progress line
    printed by :class:`ProjectProcessor` (useful when output is deferred, e.g.
    a table rendered after all projects are processed).
    """

    @property
    def verbose_progress(self) -> bool:
        """Whether to print per-target progress lines during processing.

        Returns:
            True by default; subclasses may override to return False when
            progress output should be suppressed (e.g. deferred table rendering).
        """
        return True

    @abstractmethod
    def execute(self, project: Project, target_path: Path) -> bool:
        """Execute the operation for a single project/target pair.

        Args:
            project: The project to process.
            target_path: The target directory to operate on.

        Returns:
            True to continue processing, False to abort.
        """


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

    def process_all(self, operation: CmdOperation, skip_invalid: bool = True) -> bool:
        """Process all projects with the given operation.

        Args:
            operation: The operation to execute for each (project, target) pair.
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

                if operation.verbose_progress:
                    click.echo(f"\nProcessing {proj_name} -> {target_path}")

                if not operation.execute(project, target_path):
                    return False

        return True


class SyncOperation(CmdOperation):
    """Encapsulates the sync operation logic."""

    def __init__(self, ask_callback: Callable[[str, str], Action] | None = None):
        """Initialize the sync operation.

        Args:
            ask_callback: Optional callback for handling existing paths.
                         Takes target path and expected source path as arguments.
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


class CheckOperation(CmdOperation):
    """Encapsulates the check operation logic.

    Supports two output formats:
    - ``"table"`` (default): collects all results and renders a compact Rich table
      after all projects are processed via :meth:`render`.
    - ``"verbose"``: prints detailed per-project output immediately during processing.
    """

    def __init__(self, show_extra: bool = False, output_format: OutputFormat = OutputFormat.TABLE):
        """Initialize the check operation.

        Args:
            show_extra: Whether to show extra exclude entries.
            output_format: Output format — ``OutputFormat.TABLE`` (default) or ``OutputFormat.VERBOSE``.
        """
        self.show_extra = show_extra
        self.output_format = output_format
        self._rows: list[CheckRow] = []

    @property
    def verbose_progress(self) -> bool:
        """Whether to print per-target progress lines during processing."""
        return self.output_format == OutputFormat.VERBOSE

    def execute(self, project: Project, target_path: Path) -> bool:
        """Execute the check operation for a single project/target pair.

        In table mode, results are collected for deferred rendering via :meth:`render`.
        In verbose mode, results are printed immediately.

        Args:
            project: The project to check.
            target_path: The target directory to check.

        Returns:
            Always True to continue processing.
        """
        manager = SymlinkManager(project, target_path)
        result = manager.check()

        if self.output_format == OutputFormat.VERBOSE:
            formatter = CheckResultFormatter(result, self.show_extra)
            formatter.format(project.name, target_path)
        else:
            self._rows.append(CheckRow(project.name, target_path, result))

        return True

    def render(self) -> None:
        """Render collected results as a table.

        No-op when ``output_format`` is ``"verbose"`` since output is already printed.
        """
        if self.output_format != OutputFormat.VERBOSE and self._rows:
            CheckTableFormatter(self._rows, self.show_extra).render()
