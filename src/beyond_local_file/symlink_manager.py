"""Symlink management for synchronizing project items to target directories."""

import shutil
from collections.abc import Callable
from enum import Enum
from pathlib import Path

from .git_manager import GitExcludeManager
from .link_strategy_protocol import (
    GitExcludeAddResult,
    GitExcludeCheckResult,
    LinkCheckResult,
    LinkCreateResult,
    OperationProgress,
)
from .model.processing import ManagedProjectItem


class Action(Enum):
    """Actions to take when encountering an existing path."""

    SKIP = 1
    OVERWRITE = 2
    ABORT = 3


class SymlinkManager:
    """Manages symlink creation and checking for a project.

    This class handles synchronizing symlinks from a project's source directory
    to a target directory, with support for Git exclude file management.

    Implements the LinkStrategyManager protocol.

    Attributes:
        symlink_items: List of items to manage (pre-filtered by strategy).
        target_path: The target directory where symlinks should be created.
        git_manager: Manager for Git exclude file operations.
    """

    def __init__(self, symlink_items: list[ManagedProjectItem], target_path: Path):
        """Initialize the SymlinkManager.

        Args:
            symlink_items: List of ManagedProjectItem instances with SYMLINK strategy.
                          Should be pre-filtered by the caller.
            target_path: The target directory for symlinks.
        """
        self.symlink_items = symlink_items
        self.target_path = Path(target_path)
        self.git_manager = GitExcludeManager(self.target_path)

    # Protocol methods (LinkStrategyManager interface)

    def get_managed_items(self) -> list[ManagedProjectItem]:
        """Return the list of items this manager handles.

        Returns:
            List of ManagedProjectItem instances managed by this manager.
        """
        return self.symlink_items

    def create_links(self, ask_callback: Callable[[str, str], Action] | None = None) -> LinkCreateResult:
        """Create links for all managed items (protocol method).

        Args:
            ask_callback: Optional callback function that takes a path string
                        and expected source path, and returns an Action.

        Returns:
            LinkCreateResult containing details of the operation with progress tracking.
        """
        result = LinkCreateResult(progress=OperationProgress(total_items=len(self.symlink_items)))

        for item in self.symlink_items:
            link_path = self.target_path / item.name

            if self._is_link_correct(link_path, item.path):
                result.already_correct.add(item.name)
                result.progress.completed_items += 1
                continue

            if link_path.exists() or link_path.is_symlink():
                action = self._handle_existing_path(link_path, item.path, ask_callback)
                if action == Action.SKIP:
                    result.skipped.add(item.name)
                    result.progress.completed_items += 1
                    continue
                elif action == Action.ABORT:
                    result.progress.aborted = True
                    return result
                elif action == Action.OVERWRITE:
                    self._remove_path(link_path)

            # Ensure parent directories exist for subpath items
            link_path.parent.mkdir(parents=True, exist_ok=True)

            if self._create_symlink(item.path, link_path):
                result.created.add(item.name)
            else:
                result.failed.add(item.name)

            result.progress.completed_items += 1

        return result

    def check_links(self) -> LinkCheckResult:
        """Check the status of links for all managed items (protocol method).

        Verifies that symlinks exist and point to the correct source path.

        Returns:
            LinkCheckResult containing the status of symlinks:
            - exists: Symlinks that exist and point to correct source
            - incorrect: Symlinks that exist but point to wrong source
            - missing: Symlinks that don't exist
        """
        result = LinkCheckResult()

        for item in self.symlink_items:
            link_path = self.target_path / item.name

            if not link_path.exists() and not link_path.is_symlink():
                result.missing.append(item.name)
            elif self._is_link_correct(link_path, item.path):
                result.exists.append(item.name)
            else:
                # Link exists but points to wrong source
                result.incorrect.append(item.name)

        # Symlinks don't have strategy-specific details
        result.details = None

        return result

    def add_git_excludes(self) -> GitExcludeAddResult:
        """Add git exclude entries for all managed items (protocol method).

        PRECONDITION: This method is guaranteed to be called only when the target
        directory is inside a git repository. Callers must check git repo status
        before invoking this method.

        Returns:
            GitExcludeAddResult with added count, existing entries, and progress tracking.
        """
        item_names = {i.name for i in self.symlink_items}
        result = GitExcludeAddResult(progress=OperationProgress(total_items=len(item_names)))

        if item_names:
            added, existing = self.git_manager.write_entries(item_names)
            result.added = added
            result.existing = existing
            result.progress.completed_items = result.progress.total_items

        return result

    def check_git_excludes(self, all_valid_entries: set[str]) -> GitExcludeCheckResult:
        """Check git exclude status for managed items (protocol method).

        PRECONDITION: This method is guaranteed to be called only when the target
        directory is inside a git repository. Callers must check git repo status
        before invoking this method.

        Args:
            all_valid_entries: Set of ALL valid entry names from all managers.
                             Used to identify extra/stale entries.

        Returns:
            GitExcludeCheckResult with present, missing, extra entries.
        """
        result = GitExcludeCheckResult()

        exclude_entries = self.git_manager.read_entries()
        item_names = {i.name for i in self.symlink_items}

        result.present = item_names & exclude_entries
        result.missing = item_names - exclude_entries
        # Use all_valid_entries to identify extra entries
        result.extra = exclude_entries - all_valid_entries

        return result

    def _is_link_correct(self, link_path: Path, source_path: Path) -> bool:
        """Check if a symlink correctly points to the source path.

        Args:
            link_path: Path to the symlink.
            source_path: Expected source path.

        Returns:
            True if the symlink exists and points to the correct source.
        """
        if not link_path.is_symlink():
            return False
        return link_path.resolve() == source_path.resolve()

    def _handle_existing_path(
        self, link_path: Path, source_path: Path, ask_callback: Callable[[str, str], Action] | None = None
    ) -> Action:
        """Handle an existing path at the symlink location.

        Args:
            link_path: Path that already exists.
            source_path: Expected source path for the symlink.
            ask_callback: Callback to prompt user for action.

        Returns:
            The action to take: SKIP, OVERWRITE, or ABORT.
        """
        if ask_callback:
            return ask_callback(str(link_path), str(source_path))
        return Action.SKIP

    def _remove_path(self, path: Path) -> None:
        """Safely remove a file, symlink, or directory.

        Args:
            path: Path to remove.
        """
        if path.is_symlink():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    def _create_symlink(self, source: Path, link: Path) -> bool:
        """Create a symlink pointing to the source.

        Args:
            source: Source path to point to.
            link: Path where the symlink will be created.

        Returns:
            True if the symlink was created successfully, False otherwise.

        Note:
            On Windows, this requires either:
            - Developer Mode enabled (Windows 10 1703+), or
            - Administrator privileges (older Windows versions)
        """
        try:
            # On Windows, symlink_to needs to know if target is a directory
            # The target_is_directory parameter is ignored on Unix
            link.symlink_to(source, target_is_directory=source.is_dir())
            return True
        except (OSError, PermissionError):
            return False
