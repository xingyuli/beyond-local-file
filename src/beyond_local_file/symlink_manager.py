"""Symlink management for synchronizing project items to target directories."""

import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .git_manager import GitExcludeManager
from .models import Project


class Action(Enum):
    """Actions to take when encountering an existing path."""

    SKIP = 1
    OVERWRITE = 2
    ABORT = 3


@dataclass
class SyncResult:
    """Result of a sync operation.

    Attributes:
        created: Set of item names for which symlinks were newly created.
        already_correct: Set of item names where symlinks already existed and were correct.
        skipped: Set of item names that were skipped due to user choice.
        failed: Set of item names for which symlink creation failed.
        git_added: Number of entries added to .git/info/exclude.
        git_existing: Set of entries that were already in .git/info/exclude.
        aborted: True if the operation was aborted by user.
    """

    created: set[str] = field(default_factory=set)
    already_correct: set[str] = field(default_factory=set)
    skipped: set[str] = field(default_factory=set)
    failed: set[str] = field(default_factory=set)
    git_added: int = 0
    git_existing: set[str] = field(default_factory=set)
    aborted: bool = False


@dataclass
class CheckResult:
    """Result of a check operation.

    Attributes:
        symlink_exists: List of item names that have existing symlinks.
        symlink_missing: List of item names that are missing symlinks.
        exclude_present: Set of items that are correctly in .git/info/exclude.
        exclude_missing: Set of items that should be but are not in .git/info/exclude.
        exclude_extra: Set of entries in .git/info/exclude that don't correspond to project items.
    """

    symlink_exists: list[str] = field(default_factory=list)
    symlink_missing: list[str] = field(default_factory=list)
    exclude_present: set[str] = field(default_factory=set)
    exclude_missing: set[str] = field(default_factory=set)
    exclude_extra: set[str] = field(default_factory=set)


class SymlinkManager:
    """Manages symlink creation and checking for a project.

    This class handles synchronizing symlinks from a project's source directory
    to a target directory, with support for Git exclude file management.

    Attributes:
        project: The project to manage symlinks for.
        target_path: The target directory where symlinks should be created.
        git_manager: Manager for Git exclude file operations.
    """

    def __init__(self, project: Project, target_path: Path):
        """Initialize the SymlinkManager.

        Args:
            project: The project containing items to create symlinks for.
            target_path: The target directory for symlinks.
        """
        self.project = project
        self.target_path = Path(target_path)
        self.git_manager = GitExcludeManager(self.target_path)

    def sync(self, ask_callback: Callable[[str], Action] | None = None) -> SyncResult:
        """Synchronize symlinks from project to target directory.

        Creates symlinks for all project items in the target directory.
        If a symlink already exists and points to the correct source, it is
        left unchanged. If an incorrect symlink or regular file/directory
        exists, the callback is invoked to determine the action to take.

        Args:
            ask_callback: Optional callback function that takes a path string
                        and returns an Action. If not provided, existing
                        paths are skipped by default.

        Returns:
            SyncResult containing details of the operation.
        """
        result = SyncResult()

        for item in self.project.items:
            link_path = self.target_path / item.name

            if self._is_link_correct(link_path, item.source_path):
                result.already_correct.add(item.name)
                continue

            if link_path.exists() or link_path.is_symlink():
                action = self._handle_existing_path(link_path, ask_callback)
                if action == Action.SKIP:
                    result.skipped.add(item.name)
                    continue
                elif action == Action.ABORT:
                    result.aborted = True
                    return result
                elif action == Action.OVERWRITE:
                    self._remove_path(link_path)

            if not self._create_symlink(item.source_path, link_path):
                result.failed.add(item.name)
                continue
            result.created.add(item.name)

        if self.git_manager.is_git_repo():
            all_items = result.created | result.already_correct
            if all_items:
                added, existing = self.git_manager.write_entries(all_items)
                result.git_added = added
                result.git_existing = existing

        return result

    def check(self) -> CheckResult:
        """Check the status of symlinks and Git exclude configuration.

        Inspects the target directory to determine which symlinks exist,
        which are missing, and the state of the Git exclude file.

        Returns:
            CheckResult containing the status of symlinks and exclude entries.
        """
        result = CheckResult()

        for item in self.project.items:
            link_path = self.target_path / item.name

            if link_path.exists() or link_path.is_symlink():
                result.symlink_exists.append(item.name)
            else:
                result.symlink_missing.append(item.name)

        if self.git_manager.is_git_repo():
            exclude_entries = self.git_manager.read_entries()
            item_names = self.project.get_item_names()

            result.exclude_present = item_names & exclude_entries
            result.exclude_missing = item_names - exclude_entries
            result.exclude_extra = exclude_entries - item_names

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

    def _handle_existing_path(self, link_path: Path, ask_callback: Callable[[str], Action] | None = None) -> Action:
        """Handle an existing path at the symlink location.

        Args:
            link_path: Path that already exists.
            ask_callback: Callback to prompt user for action.

        Returns:
            The action to take: SKIP, OVERWRITE, or ABORT.
        """
        if ask_callback:
            return ask_callback(str(link_path))
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
        """
        try:
            link.symlink_to(source)
            return True
        except (OSError, PermissionError):
            return False
