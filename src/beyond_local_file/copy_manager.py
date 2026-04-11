"""Physical file copy management with bidirectional sync support.

Handles copying single files from managed projects to target directories,
with hash-based change detection and conflict resolution.
"""

import shutil
from collections.abc import Callable
from pathlib import Path

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
from .model.processing import ManagedProjectItem
from .options import LinkStrategy, SyncStatus
from .sync_state import SyncState


class CopyConflictAction:
    """Actions available when a bidirectional conflict is detected."""

    MANAGED = "managed"
    TARGET = "target"
    SKIP = "skip"


class CopyManager:
    """Manages physical file copies from a project to a target directory.

    Only operates on items whose strategy is ``LinkStrategy.COPY``.

    Implements the LinkStrategyManager protocol.

    Attributes:
        copy_items: Managed project items that use the copy strategy.
        target_path: Target directory where copies are placed.
        config_dir: Directory where the config file lives (for sync state storage).
        sync_state: Persistent sync state tracker.
        git_manager: Manager for Git exclude file operations.
    """

    def __init__(self, copy_items: list[ManagedProjectItem], target_path: Path, config_dir: Path):
        """Initialize the CopyManager.

        Args:
            copy_items: Items with ``strategy == LinkStrategy.COPY``.
            target_path: Target directory for file copies.
            config_dir: Directory where the config file lives.
        """
        self.copy_items = [i for i in copy_items if i.strategy == LinkStrategy.COPY]
        self.target_path = target_path
        self.config_dir = config_dir
        self.sync_state = SyncState(config_dir)
        self.sync_state.load()
        self.git_manager = GitExcludeManager(target_path)

    # Protocol methods (LinkStrategyManager interface)

    def get_managed_items(self) -> list[ManagedProjectItem]:
        """Return the list of items this manager handles.

        Returns:
            List of ManagedProjectItem instances managed by this manager.
        """
        return self.copy_items

    def create_links(self, conflict_callback: Callable[[Path, Path], str] | None = None) -> LinkCreateResult:  # noqa: PLR0912 -- inlined sync logic from removed sync() method
        """Create links for all managed items (protocol method).

        Synchronizes copied files using bidirectional change detection.
        For each copy item:
        - If target does not exist: copy managed → target.
        - If both exist and in sync: skip.
        - If only managed changed: copy managed → target.
        - If only target changed: copy target → managed (reverse sync).
        - If both changed: invoke conflict_callback for user decision.

        Args:
            conflict_callback: Called on bidirectional conflict. Receives
                (managed_path, target_path) and returns one of
                CopyConflictAction.MANAGED, TARGET, or SKIP.
                Defaults to skip when not provided.

        Returns:
            LinkCreateResult containing details of the operation with progress tracking.
        """
        result = LinkCreateResult(progress=OperationProgress(total_items=len(self.copy_items)))
        reverse_copied: set[str] = set()

        for item in self.copy_items:
            target_file = self.target_path / item.name
            managed_file = item.path

            if not target_file.exists():
                # First-time copy
                if self._copy_file(managed_file, target_file):
                    self.sync_state.update_record(managed_file, target_file)
                    result.created.add(item.name)
                else:
                    result.failed.add(item.name)
                result.progress.completed_items += 1
                continue

            status = self.sync_state.detect_status(managed_file, target_file)

            if status == SyncStatus.BOTH_CHANGED:
                # Resolve conflict via user callback
                action = conflict_callback(managed_file, target_file) if conflict_callback else CopyConflictAction.SKIP

                if action == CopyConflictAction.MANAGED:
                    if self._copy_and_record(managed_file, target_file, managed_file, target_file):
                        result.created.add(item.name)
                    else:
                        result.failed.add(item.name)
                elif action == CopyConflictAction.TARGET:
                    if self._copy_and_record(target_file, managed_file, managed_file, target_file):
                        reverse_copied.add(item.name)
                    else:
                        result.failed.add(item.name)
                else:
                    result.skipped.add(item.name)
            elif status == SyncStatus.MANUALLY_SYNCED:
                # Files match but sync-state is outdated: update record without copying
                self.sync_state.update_record(managed_file, target_file)
                result.already_correct.add(item.name)
            elif status == SyncStatus.IN_SYNC:
                # Create missing record when target file was just added to managed project
                if self.sync_state.get_record(str(target_file)) is None:
                    self.sync_state.update_record(managed_file, target_file)
                result.already_correct.add(item.name)
            elif status == SyncStatus.MANAGED_CHANGED:
                if self._copy_and_record(managed_file, target_file, managed_file, target_file):
                    result.created.add(item.name)
                else:
                    result.failed.add(item.name)
            elif status == SyncStatus.TARGET_CHANGED:
                if self._copy_and_record(target_file, managed_file, managed_file, target_file):
                    reverse_copied.add(item.name)
                else:
                    result.failed.add(item.name)

            result.progress.completed_items += 1

        self.sync_state.save()

        # Create strategy-specific details
        result.details = CopyCreateDetails(reverse_copied=reverse_copied)

        return result

    def check_links(self) -> LinkCheckResult:
        """Check the status of links for all managed items (protocol method).

        Checks sync status of all copy items without modifying files.

        Returns:
            LinkCheckResult containing the status of copies with detailed sync information.
        """
        in_sync_list: list[str] = []
        manually_synced_list: list[str] = []
        managed_changed_list: list[str] = []
        target_changed_list: list[str] = []
        both_changed_list: list[str] = []
        missing_list: list[str] = []

        for item in self.copy_items:
            target_file = self.target_path / item.name

            if not target_file.exists():
                missing_list.append(item.name)
                continue

            status = self.sync_state.detect_status(item.path, target_file)
            status_map = {
                SyncStatus.IN_SYNC: in_sync_list,
                SyncStatus.MANUALLY_SYNCED: manually_synced_list,
                SyncStatus.MANAGED_CHANGED: managed_changed_list,
                SyncStatus.TARGET_CHANGED: target_changed_list,
                SyncStatus.BOTH_CHANGED: both_changed_list,
            }
            status_map[status].append(item.name)

        # Create strategy-specific details
        details = CopyCheckDetails(
            in_sync=in_sync_list,
            manually_synced=manually_synced_list,
            managed_changed=managed_changed_list,
            target_changed=target_changed_list,
            both_changed=both_changed_list,
        )

        return LinkCheckResult(
            exists=in_sync_list + manually_synced_list,
            missing=missing_list,
            details=details,
        )

    def add_git_excludes(self) -> GitExcludeAddResult:
        """Add git exclude entries for all managed items (protocol method).

        PRECONDITION: This method is guaranteed to be called only when the target
        directory is inside a git repository. Callers must check git repo status
        before invoking this method.

        Returns:
            GitExcludeAddResult with added count and existing entries.
        """
        item_names = {i.name for i in self.copy_items}
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
        item_names = {i.name for i in self.copy_items}

        result.present = item_names & exclude_entries
        result.missing = item_names - exclude_entries
        # Use all_valid_entries to identify extra entries
        result.extra = exclude_entries - all_valid_entries

        return result

    # -- internal helpers ------------------------------------------------------

    def _copy_and_record(self, source: Path, destination: Path, managed: Path, target: Path) -> bool:
        """Copy a file and update the sync record on success.

        Args:
            source: File to read from.
            destination: File to write to.
            managed: Managed file path (for the sync record).
            target: Target file path (for the sync record).

        Returns:
            True on success, False on failure.
        """
        if not self._copy_file(source, destination):
            return False
        self.sync_state.update_record(managed, target)
        return True

    @staticmethod
    def _copy_file(source: Path, destination: Path) -> bool:
        """Copy a single file, creating parent directories as needed.

        Args:
            source: Source file path.
            destination: Destination file path.

        Returns:
            True on success, False on failure.
        """
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            return True
        except OSError:
            return False
