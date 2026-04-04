"""Project processing utilities for CLI commands."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import click

from .config import Config
from .copy_manager import CopyCheckResult, CopyManager
from .formatters import (
    CheckResultFormatter,
    CheckRow,
    CheckTableFormatter,
    CopyCheckResultFormatter,
    CopyResultFormatter,
    SyncResultFormatter,
)
from .model.config import ConfigProject
from .model.processing import ManagedProjectItem, ProcessingUnit
from .model.translator import translate_config_to_processing
from .models import Project
from .options import LinkStrategy, OutputFormat
from .symlink_manager import Action, CheckResult, SymlinkManager


def get_absolute_path(path: str) -> str:
    """Resolve a path to its absolute form.

    Args:
        path: A file or directory path.

    Returns:
        Absolute path as a string.
    """
    return str(Path(path).resolve())


def load_config_projects(config: str, project_name: str | None = None) -> tuple[dict[str, ConfigProject], Path] | None:
    """Load configuration using new model structure.

    Args:
        config: Path to the YAML configuration file.
        project_name: Optional project name to filter. If provided, only
                    returns configuration for that project.

    Returns:
        Tuple of (ConfigProject dict, config directory path).
        Returns None if loading failed.
    """
    config_path = get_absolute_path(config)

    if not Path(config_path).exists():
        click.echo(f"Config file not found: {config_path}")
        return None

    try:
        cfg = Config(config_path)
        cfg.load()
        projects = cfg.get_config_projects(project_name)
        config_dir = Path(config_path).parent
        return projects, config_dir
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

        DEPRECATED: Use execute_unit() for new code. This method will be
        removed after migration to the new model structure is complete.

        Args:
            project: The project to process.
            target_path: The target directory to operate on.

        Returns:
            True to continue processing, False to abort.
        """

    def execute_unit(self, unit: ProcessingUnit) -> bool:
        """Execute the operation for a single processing unit.

        Default implementation converts ProcessingUnit to Project and calls
        execute() for backward compatibility. Subclasses should override this
        method to work directly with ProcessingUnit.

        Args:
            unit: The processing unit to execute.

        Returns:
            True to continue processing, False to abort.
        """
        # Convert ProcessingUnit to Project for backward compatibility
        if unit.items is None:
            # Sync everything: scan directory
            project = Project.from_directory(unit.display_name, unit.managed_project_path)
        else:
            # Sync specified items: use items directly (ManagedProjectItem is now unified)
            project = Project(name=unit.display_name, directory=unit.managed_project_path, items=unit.items)

        return self.execute(project, unit.target_project_path)


class ProjectProcessor:
    """Processes projects for sync and check operations.

    This class provides static methods for processing projects using the new
    model structure with translation layer.
    """

    @staticmethod
    def process_all_units(
        config_projects: dict[str, ConfigProject],
        operation: CmdOperation,
        skip_invalid: bool = True,
    ) -> bool:
        """Process all projects using new model structure with translation layer.

        Args:
            config_projects: Dictionary of ConfigProject instances.
            operation: The operation to execute for each processing unit.
            skip_invalid: Whether to skip invalid projects or stop processing.

        Returns:
            True if all operations completed, False if aborted.
        """
        # Translate config to processing units
        processing_units = translate_config_to_processing(config_projects)

        # Execute each processing unit
        for unit in processing_units:
            # Validate managed project path
            if not unit.managed_project_path.exists():
                click.echo(f"Project directory does not exist: {unit.managed_project_path}")
                if not skip_invalid:
                    return False
                continue

            # Load items if not already loaded (items=None means sync everything)
            current_unit = unit
            if unit.items is None:
                # Scan directory to get all items
                items = []
                if unit.managed_project_path.exists() and unit.managed_project_path.is_dir():
                    for item_path in unit.managed_project_path.iterdir():
                        items.append(
                            ManagedProjectItem(
                                name=item_path.name,
                                path=item_path,
                                strategy=LinkStrategy.SYMLINK,
                            )
                        )
                # Update unit with loaded items (create new instance since dataclass is immutable by default)
                current_unit = replace(unit, items=items)

            # Validate items exist
            if not current_unit.items:
                click.echo(f"No items found in {current_unit.display_name}")
                if not skip_invalid:
                    return False
                continue

            # Validate target path
            if not current_unit.target_project_path.exists():
                click.echo(f"Target directory does not exist: {current_unit.target_project_path}")
                continue

            # Print progress
            if operation.verbose_progress:
                click.echo(f"\nProcessing {current_unit.display_name} -> {current_unit.target_project_path}")

            # Execute operation
            if not operation.execute_unit(current_unit):
                return False

        return True


class SyncOperation(CmdOperation):
    """Encapsulates the sync operation logic for both symlinks and copies."""

    def __init__(
        self,
        config_dir: Path,
        ask_callback: Callable[[str, str], Action] | None = None,
        conflict_callback: Callable[[Path, Path], str] | None = None,
    ):
        """Initialize the sync operation.

        Args:
            config_dir: Directory where the config file lives.
            ask_callback: Optional callback for handling existing symlink paths.
            conflict_callback: Optional callback for resolving copy conflicts.
        """
        self.config_dir = config_dir
        self.ask_callback = ask_callback
        self.conflict_callback = conflict_callback

    def execute(self, project: Project, target_path: Path) -> bool:
        """Execute the sync operation for symlinks and copies.

        Uses divide-and-conquer strategy: partition items by strategy,
        then delegate to appropriate managers.

        Args:
            project: The project to sync.
            target_path: The target directory.

        Returns:
            True to continue, False if aborted.
        """
        # PARTITION: Divide items by strategy
        symlink_items = [i for i in project.items if i.strategy == LinkStrategy.SYMLINK]
        copy_items = [i for i in project.items if i.strategy == LinkStrategy.COPY]

        # CONQUER: Delegate to appropriate managers

        # Handle symlink items
        if symlink_items:
            manager = SymlinkManager(symlink_items, target_path)
            result = manager.sync(self.ask_callback)

            formatter = SyncResultFormatter(project, result)
            formatter.format(project.name, target_path)

            if result.aborted:
                click.echo("Aborted by user")
                return False

        # Handle copy items
        if copy_items:
            copy_mgr = CopyManager(copy_items, target_path, self.config_dir)
            copy_result = copy_mgr.sync(self.conflict_callback)
            CopyResultFormatter(copy_result).format(project.name, target_path)

        return True


class CheckOperation(CmdOperation):
    """Encapsulates the check operation logic for symlinks and copies.

    Supports two output formats:
    - ``"table"`` (default): collects all results and renders a compact Rich table
      after all projects are processed via :meth:`render`.
    - ``"verbose"``: prints detailed per-project output immediately during processing.
    """

    def __init__(self, config_dir: Path, show_extra: bool = False, output_format: OutputFormat = OutputFormat.TABLE):
        """Initialize the check operation.

        Args:
            config_dir: Directory where the config file lives.
            show_extra: Whether to show extra exclude entries.
            output_format: Output format — ``OutputFormat.TABLE`` (default) or ``OutputFormat.VERBOSE``.
        """
        self.config_dir = config_dir
        self.show_extra = show_extra
        self.output_format = output_format
        self._rows: list[CheckRow] = []

    @property
    def verbose_progress(self) -> bool:
        """Whether to print per-target progress lines during processing."""
        return self.output_format == OutputFormat.VERBOSE

    def execute(self, project: Project, target_path: Path) -> bool:
        """Execute the check operation for a single project/target pair.

        Uses divide-and-conquer strategy: partition items by strategy,
        then delegate to appropriate managers.

        Args:
            project: The project to check.
            target_path: The target directory to check.

        Returns:
            Always True to continue processing.
        """
        # PARTITION: Divide items by strategy
        symlink_items = [i for i in project.items if i.strategy == LinkStrategy.SYMLINK]
        copy_items = [i for i in project.items if i.strategy == LinkStrategy.COPY]

        # CONQUER: Create managers with partitioned items
        symlink_mgr = SymlinkManager(symlink_items, target_path) if symlink_items else None
        copy_mgr = CopyManager(copy_items, target_path, self.config_dir) if copy_items else None

        # Collect all valid entry names from ALL managers for git exclude checking
        all_valid_entries: set[str] = set()
        if symlink_mgr:
            all_valid_entries.update(i.name for i in symlink_mgr.get_managed_items())
        if copy_mgr:
            all_valid_entries.update(i.name for i in copy_mgr.get_managed_items())

        # Check symlink items using protocol
        symlink_result = None
        if symlink_mgr:
            symlink_result = symlink_mgr.check()

            # Check git excludes using protocol with all_valid_entries
            if symlink_mgr.git_manager.is_git_repo():
                git_result = symlink_mgr.check_git_excludes(all_valid_entries)
                # Map protocol result back to CheckResult for backward compatibility
                symlink_result.exclude_present = git_result.present
                symlink_result.exclude_missing = git_result.missing
                symlink_result.exclude_extra = git_result.extra

        # Check copy items
        copy_result: CopyCheckResult | None = None
        if copy_mgr:
            copy_result = copy_mgr.check()

        if self.output_format == OutputFormat.VERBOSE:
            if symlink_result:
                formatter = CheckResultFormatter(symlink_result, self.show_extra)
                formatter.format(project.name, target_path)
            if copy_result:
                CopyCheckResultFormatter(copy_result).format(project.name, target_path)
        else:
            # For table format, we need a symlink_result even if empty
            if not symlink_result:
                symlink_result = CheckResult()
            self._rows.append(CheckRow(project.name, target_path, symlink_result, copy_result))

        return True

    def render(self) -> None:
        """Render collected results as a table.

        No-op when ``output_format`` is ``"verbose"`` since output is already printed.
        """
        if self.output_format != OutputFormat.VERBOSE and self._rows:
            CheckTableFormatter(self._rows, self.show_extra).render()
