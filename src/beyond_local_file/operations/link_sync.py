"""link sync subcommand — operation logic and output formatting."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import click

from ..copy_manager import CopyManager
from ..link_strategy_protocol import (
    CopyCreateDetails,
    GitExcludeAddResult,
    LinkCreateResult,
)
from ..model.processing import ProcessingUnit
from ..options import LinkStrategy
from ..symlink_manager import Action, SymlinkManager
from .base import CmdOperation

# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------


class LinkSyncFormatter:
    """Formats and prints the results of a link sync operation.

    Handles output for both symlink and copy strategies by inspecting the
    ``details`` field of the result types.
    """

    def __init__(
        self,
        project_directory: Path,
        link_result: LinkCreateResult,
        git_result: GitExcludeAddResult | None = None,
    ) -> None:
        """Initialize the formatter.

        Args:
            project_directory: Directory path of the managed project (used to
                build source paths for symlink messages).
            link_result: Result of the link creation operation.
            git_result: Optional result of the git exclude add operation.
        """
        self.project_directory = project_directory
        self.link_result = link_result
        self.git_result = git_result

    def print(self, target_path: Path) -> None:
        """Print all output lines for this sync result.

        Args:
            target_path: Target path where links were created.
        """
        self._format_already_correct(target_path)
        self._format_created(target_path)
        self._format_reverse_copied(target_path)
        self._format_skipped(target_path)
        self._format_failed()
        self._format_git_entries()
        self._format_progress()

    def _format_already_correct(self, target_path: Path) -> None:
        for item in sorted(self.link_result.already_correct):
            source_path = self.project_directory / item
            link_path = target_path / item
            if isinstance(self.link_result.details, CopyCreateDetails):
                click.echo(f"Copy already in sync: {item}")
            else:
                click.echo(f"Symlink already correct: {link_path} -> {source_path}")

    def _format_created(self, target_path: Path) -> None:
        for item in sorted(self.link_result.created):
            source_path = self.project_directory / item
            link_path = target_path / item
            if isinstance(self.link_result.details, CopyCreateDetails):
                click.echo(f"Copied: {item} -> {link_path}")
            else:
                click.echo(f"Created symlink: {link_path} -> {source_path}")

    def _format_skipped(self, target_path: Path) -> None:
        for item in sorted(self.link_result.skipped):
            link_path = target_path / item
            if isinstance(self.link_result.details, CopyCreateDetails):
                click.echo(f"Copy skipped: {item}")
            else:
                click.echo(f"Skipped: {link_path}")

    def _format_failed(self) -> None:
        for item in sorted(self.link_result.failed):
            if isinstance(self.link_result.details, CopyCreateDetails):
                click.echo(f"Copy failed: {item}")
            else:
                click.echo(f"Failed to create symlink: {item}")

    def _format_git_entries(self) -> None:
        if self.git_result is None:
            return
        for item in sorted(self.git_result.existing):
            click.echo(f"Git exclude already have: {item}")
        if self.git_result.added > 0:
            click.echo(f"Added {self.git_result.added} entries to .git/info/exclude")

    def _format_progress(self) -> None:
        if self.link_result.progress.aborted:
            click.echo(
                f"Operation aborted: {self.link_result.progress.completed_items}/"
                f"{self.link_result.progress.total_items} items processed"
            )

    def _format_reverse_copied(self, target_path: Path) -> None:
        if not isinstance(self.link_result.details, CopyCreateDetails):
            return
        for item in sorted(self.link_result.details.reverse_copied):
            click.echo(f"Reverse synced: {item} (target -> managed)")


# ---------------------------------------------------------------------------
# Operation
# ---------------------------------------------------------------------------


class SyncOperation(CmdOperation):
    """Encapsulates the sync operation logic for both symlinks and copies."""

    def __init__(
        self,
        config_dir: Path,
        ask_callback: Callable[[str, str], Action] | None = None,
        conflict_callback: Callable[[Path, Path], str] | None = None,
    ) -> None:
        """Initialize the sync operation.

        Args:
            config_dir: Directory where the config file lives.
            ask_callback: Optional callback for handling existing symlink paths.
            conflict_callback: Optional callback for resolving copy conflicts.
        """
        self.config_dir = config_dir
        self.ask_callback = ask_callback
        self.conflict_callback = conflict_callback

    def execute_unit(self, unit: ProcessingUnit) -> bool:
        """Execute the sync operation for a single processing unit.

        Partitions items by strategy, delegates to the appropriate manager,
        then prints results via :class:`LinkSyncFormatter`.

        Args:
            unit: The processing unit to sync.

        Returns:
            True to continue, False if the operation was aborted.
        """
        symlink_items = [i for i in unit.items if i.strategy == LinkStrategy.SYMLINK]
        copy_items = [i for i in unit.items if i.strategy == LinkStrategy.COPY]

        if symlink_items:
            manager = SymlinkManager(symlink_items, unit.target_project_path)
            link_result = manager.create_links(self.ask_callback)

            git_result = None
            if manager.git_manager.is_git_repo():
                git_result = manager.add_git_excludes()

            LinkSyncFormatter(unit.managed_project_path, link_result, git_result).print(unit.target_project_path)

            if link_result.progress.aborted:
                return False

        if copy_items:
            copy_mgr = CopyManager(copy_items, unit.target_project_path, self.config_dir)
            link_result = copy_mgr.create_links(self.conflict_callback)

            git_result = None
            if copy_mgr.git_manager.is_git_repo():
                git_result = copy_mgr.add_git_excludes()

            LinkSyncFormatter(unit.managed_project_path, link_result, git_result).print(unit.target_project_path)

            if link_result.progress.aborted:
                return False

        return True
