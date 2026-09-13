"""Physical copy management with bidirectional sync support.

Handles copying files and directory trees from managed projects to target
directories, with hash-based change detection and conflict resolution.
"""

import os
import shutil
from collections.abc import Callable
from pathlib import Path

from .daemon.store import BaselineTrees
from .git_manager import GitExcludeManager
from .link_strategy_protocol import (
    CopyCheckDetails,
    CopyCreateDetails,
    GitExcludeAddResult,
    GitExcludeCheckResult,
    LinkCheckResult,
    LinkCreateResult,
    OperationProgress,
)
from .model.processing import LinkStrategy, ManagedProjectItem
from .options import CopyConflictResolution
from .sync_state import SyncStatus, detect_status


def copy_projection(source: Path, destination: Path) -> None:
    """Replace *destination* with a copy of *source*, preserving symlink nodes.

    Nested symlinks inside a directory stay links (venv interpreters, relative
    ``python`` → ``python3.14``). A symlink at *source* is copied as a symlink,
    not followed. The projection path itself remains a real file or directory.

    Args:
        source: File, directory, or symlink to copy.
        destination: Path that should become the copy.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or destination.is_file():
        destination.unlink()
    elif destination.is_dir():
        shutil.rmtree(destination)
    if source.is_symlink():
        os.symlink(os.readlink(source), destination)
    elif source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination, follow_symlinks=False)


class CopyManager:
    """Manages physical copies from a project to a target directory.

    Only operates on items whose strategy is ``LinkStrategy.COPY``.
    Files and directory trees are both projected as real copies.

    Implements the LinkStrategyManager protocol.

    Attributes:
        copy_items: Managed project items that use the copy strategy.
        target_path: Target directory where copies are placed.
        config_dir: Unused; retained so existing call sites keep the same signature.
        git_manager: Manager for Git exclude file operations.

    Note:
        Git exclude operations require ``target_path`` to be the root of a Git
        repository (i.e., the directory that directly contains ``.git/``).
        If ``target_path`` is a subdirectory of a repo, ``is_git_repo()`` will
        return ``False`` and all git exclude steps will be silently skipped.
    """

    def __init__(self, copy_items: list[ManagedProjectItem], target_path: Path, config_dir: Path):
        """Initialize the CopyManager.

        Args:
            copy_items: Items with ``strategy == LinkStrategy.COPY``.
            target_path: Target directory for file copies.  Must be the root of
                a Git repository for git exclude operations to take effect.
            config_dir: Unused; retained for call-site compatibility.
        """
        self.copy_items = [i for i in copy_items if i.strategy == LinkStrategy.COPY]
        self.target_path = target_path
        self.config_dir = config_dir
        self.git_manager = GitExcludeManager(target_path)

    # Protocol methods (LinkStrategyManager interface)

    def get_managed_items(self) -> list[ManagedProjectItem]:
        """Return the list of items this manager handles.

        Returns:
            List of ManagedProjectItem instances managed by this manager.
        """
        return self.copy_items

    def create_links(  # noqa: PLR0912 -- inlined sync logic from removed sync() method
        self, conflict_callback: Callable[[Path, Path], CopyConflictResolution] | None = None
    ) -> LinkCreateResult:
        """Create links for all managed items (protocol method).

        Synchronizes copy projections using bidirectional change detection.
        For each copy item:
        - If the projection path is a symlink: replace it with a real copy.
        - If target does not exist: copy managed → target (file or directory tree).
        - If both exist and in sync: skip.
        - If only managed changed: copy managed → target.
        - If only target changed: copy target → managed (reverse sync).
        - If both changed: invoke conflict_callback for user decision.

        Args:
            conflict_callback: Called on bidirectional conflict. Receives
                (managed_path, target_path) and returns a CopyConflictResolution.
                Defaults to SKIP when not provided.

        Returns:
            LinkCreateResult containing details of the operation with progress tracking.
        """
        result = LinkCreateResult(progress=OperationProgress(total_items=len(self.copy_items)))
        reverse_copied: set[str] = set()

        for item in self.copy_items:
            target_file = self.target_path / item.name
            managed_file = item.path

            if target_file.is_symlink() or not target_file.exists():
                # Missing projection, or a leftover symlink at the projection
                # path, is replaced with a real copy.
                if self._copy_item(managed_file, target_file):
                    result.created.add(item.name)
                else:
                    result.failed.add(item.name)
                result.progress.completed_items += 1
                continue

            status = detect_status(managed_file, target_file)

            if status == SyncStatus.BOTH_CHANGED:
                action = (
                    conflict_callback(managed_file, target_file) if conflict_callback else CopyConflictResolution.SKIP
                )

                if action == CopyConflictResolution.MANAGED:
                    if self._copy_item(managed_file, target_file):
                        result.created.add(item.name)
                    else:
                        result.failed.add(item.name)
                elif action == CopyConflictResolution.TARGET:
                    if self._copy_item(target_file, managed_file):
                        reverse_copied.add(item.name)
                    else:
                        result.failed.add(item.name)
                else:
                    result.skipped.add(item.name)
            elif status == SyncStatus.IN_SYNC:
                result.already_correct.add(item.name)
            elif status in {SyncStatus.MANAGED_CHANGED, SyncStatus.MISMATCH}:
                if self._copy_item(managed_file, target_file):
                    result.created.add(item.name)
                else:
                    result.failed.add(item.name)
            elif status == SyncStatus.TARGET_CHANGED:
                if self._copy_item(target_file, managed_file):
                    reverse_copied.add(item.name)
                else:
                    result.failed.add(item.name)

            result.progress.completed_items += 1

        result.details = CopyCreateDetails(reverse_copied=reverse_copied)

        return result

    def check_links(
        self,
        *,
        baseline: BaselineTrees | None = None,
        managed_root: Path | None = None,
        on_item: Callable[[str], None] | None = None,
    ) -> LinkCheckResult:
        """Check live hashes of managed vs target for all copy items.

        Args:
            baseline: Optional baseline used only to label which side moved.
            managed_root: Managed-project root for baseline lookups.
            on_item: Optional callback invoked with the current item name.

        Returns:
            LinkCheckResult containing the status of copies with detailed sync information.
        """
        in_sync_list: list[str] = []
        mismatched_list: list[str] = []
        managed_changed_list: list[str] = []
        target_changed_list: list[str] = []
        both_changed_list: list[str] = []
        missing_list: list[str] = []
        incorrect_list: list[str] = []

        for item in self.copy_items:
            if on_item is not None:
                on_item(item.name)
            target_file = self.target_path / item.name

            if target_file.is_symlink():
                incorrect_list.append(item.name)
                continue

            if not target_file.exists():
                missing_list.append(item.name)
                continue

            status = detect_status(
                item.path,
                target_file,
                (baseline, managed_root, self.target_path, item.name)
                if baseline is not None and managed_root is not None
                else None,
            )
            status_map = {
                SyncStatus.IN_SYNC: in_sync_list,
                SyncStatus.MISMATCH: mismatched_list,
                SyncStatus.MANAGED_CHANGED: managed_changed_list,
                SyncStatus.TARGET_CHANGED: target_changed_list,
                SyncStatus.BOTH_CHANGED: both_changed_list,
            }
            status_map[status].append(item.name)

        details = CopyCheckDetails(
            in_sync=in_sync_list,
            mismatched=mismatched_list,
            managed_changed=managed_changed_list,
            target_changed=target_changed_list,
            both_changed=both_changed_list,
        )

        return LinkCheckResult(
            exists=in_sync_list,
            missing=missing_list,
            incorrect=incorrect_list,
            details=details,
        )

    def is_git_repo(self) -> bool:
        """Return whether the target directory is inside a git repository.

        Returns:
            True if the target is a git repository root, False otherwise.
        """
        return self.git_manager.is_git_repo()

    def add_git_excludes(self) -> GitExcludeAddResult | None:
        """Add git exclude entries for all managed items.

        Returns ``None`` when the target directory is not inside a git
        repository; no entries are written in that case.

        Returns:
            GitExcludeAddResult with added count and existing entries, or
            ``None`` if the target is not a git repository.
        """
        if not self.git_manager.is_git_repo():
            return None

        item_names = {i.name for i in self.copy_items}
        result = GitExcludeAddResult(progress=OperationProgress(total_items=len(item_names)))

        if item_names:
            added, existing = self.git_manager.write_entries(item_names)
            result.added = added
            result.existing = existing
            result.progress.completed_items = result.progress.total_items

        return result

    def check_git_excludes(self, all_valid_entries: set[str]) -> GitExcludeCheckResult | None:
        """Check git exclude status for managed items.

        Returns ``None`` when the target directory is not inside a git
        repository.

        Args:
            all_valid_entries: Set of ALL valid entry names from all managers.
                             Used to identify extra/stale entries.

        Returns:
            GitExcludeCheckResult with present, missing, extra entries, or
            ``None`` if the target is not a git repository.
        """
        if not self.git_manager.is_git_repo():
            return None

        result = GitExcludeCheckResult()

        exclude_entries = self.git_manager.read_entries()
        item_names = {i.name for i in self.copy_items}

        result.present = item_names & exclude_entries
        result.missing = item_names - exclude_entries
        # Use all_valid_entries to identify extra entries
        result.extra = exclude_entries - all_valid_entries

        return result

    # -- internal helpers ------------------------------------------------------

    @staticmethod
    def _copy_item(source: Path, destination: Path) -> bool:
        """Copy a file or directory tree, creating parent directories as needed.

        Replaces a symlink or existing path at ``destination`` so the
        projection path is a real copy. Nested symlink nodes inside a
        directory are preserved.

        Args:
            source: Source file or directory path.
            destination: Destination file or directory path.

        Returns:
            True on success, False on failure.
        """
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            copy_projection(source, destination)
            return True
        except OSError:
            return False
