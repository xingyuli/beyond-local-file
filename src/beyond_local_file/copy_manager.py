"""Physical file copy management with bidirectional sync support.

Handles copying single files from managed projects to target directories,
with hash-based change detection and conflict resolution.
"""

import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .git_manager import GitExcludeManager
from .models import ProjectItem
from .options import LinkStrategy, SyncStatus
from .sync_state import SyncState


class CopyConflictAction:
    """Actions available when a bidirectional conflict is detected."""

    MANAGED = "managed"
    TARGET = "target"
    SKIP = "skip"


@dataclass
class CopyResult:
    """Result of a copy-sync operation for a single project/target pair.

    Attributes:
        copied: Items freshly copied from managed to target.
        reverse_copied: Items synced from target back to managed.
        in_sync: Items already in sync (no action needed).
        skipped: Items skipped by user choice.
        failed: Items that failed to copy.
        git_added: Number of entries added to .git/info/exclude.
        git_existing: Set of entries that were already in .git/info/exclude.
    """

    copied: set[str] = field(default_factory=set)
    reverse_copied: set[str] = field(default_factory=set)
    in_sync: set[str] = field(default_factory=set)
    skipped: set[str] = field(default_factory=set)
    failed: set[str] = field(default_factory=set)
    git_added: int = 0
    git_existing: set[str] = field(default_factory=set)


@dataclass
class CopyCheckResult:
    """Result of checking copy-sync status for a single project/target pair.

    Attributes:
        in_sync: Items where managed and target are identical.
        managed_changed: Items where only the managed file changed.
        target_changed: Items where only the target file changed.
        both_changed: Items where both sides changed (conflict).
        missing: Items where the target copy does not exist.
    """

    in_sync: list[str] = field(default_factory=list)
    managed_changed: list[str] = field(default_factory=list)
    target_changed: list[str] = field(default_factory=list)
    both_changed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


class CopyManager:
    """Manages physical file copies from a project to a target directory.

    Only operates on items whose strategy is ``LinkStrategy.COPY``.

    Attributes:
        copy_items: Project items that use the copy strategy.
        target_path: Target directory where copies are placed.
        config_dir: Directory where the config file lives (for sync state storage).
        sync_state: Persistent sync state tracker.
        git_manager: Manager for Git exclude file operations.
    """

    def __init__(self, copy_items: list[ProjectItem], target_path: Path, config_dir: Path):
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

    def sync(
        self,
        conflict_callback: Callable[[Path, Path], str] | None = None,
    ) -> CopyResult:
        """Synchronize copied files using bidirectional change detection.

        For each copy item:
        - If target does not exist: copy managed → target.
        - If both exist and in sync: skip.
        - If only managed changed: copy managed → target.
        - If only target changed: copy target → managed (reverse sync).
        - If both changed: invoke *conflict_callback* for user decision.

        Args:
            conflict_callback: Called on bidirectional conflict. Receives
                (managed_path, target_path) and returns one of
                ``CopyConflictAction.MANAGED``, ``TARGET``, or ``SKIP``.
                Defaults to skip when not provided.

        Returns:
            CopyResult summarizing what happened.
        """
        result = CopyResult()

        for item in self.copy_items:
            target_file = self.target_path / item.name
            managed_file = item.source_path

            if not target_file.exists():
                # First-time copy
                if self._copy_file(managed_file, target_file):
                    self.sync_state.update_record(managed_file, target_file)
                    result.copied.add(item.name)
                else:
                    result.failed.add(item.name)
                continue

            status = self.sync_state.detect_status(managed_file, target_file)
            if status == SyncStatus.BOTH_CHANGED:
                self._resolve_conflict(item.name, managed_file, target_file, result, conflict_callback)
            else:
                self._apply_sync_action(item.name, status, managed_file, target_file, result)

        self.sync_state.save()

        # Add copied items to git exclude if target is a git repo
        if self.git_manager.is_git_repo():
            all_items = result.copied | result.in_sync
            if all_items:
                added, existing = self.git_manager.write_entries(all_items)
                result.git_added = added
                result.git_existing = existing

        return result

    def check(self) -> CopyCheckResult:
        """Check sync status of all copy items without modifying files.

        Returns:
            CopyCheckResult with per-item status.
        """
        result = CopyCheckResult()

        for item in self.copy_items:
            target_file = self.target_path / item.name

            if not target_file.exists():
                result.missing.append(item.name)
                continue

            status = self.sync_state.detect_status(item.source_path, target_file)
            status_map = {
                SyncStatus.IN_SYNC: result.in_sync,
                SyncStatus.MANAGED_CHANGED: result.managed_changed,
                SyncStatus.TARGET_CHANGED: result.target_changed,
                SyncStatus.BOTH_CHANGED: result.both_changed,
                SyncStatus.UNKNOWN: result.managed_changed,  # treat unknown as needing sync
            }
            status_map[status].append(item.name)

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

    def _apply_sync_action(
        self,
        item_name: str,
        status: SyncStatus,
        managed_file: Path,
        target_file: Path,
        result: CopyResult,
    ) -> None:
        """Apply the appropriate sync action based on detected status."""
        if status == SyncStatus.IN_SYNC:
            result.in_sync.add(item_name)
        elif status in (SyncStatus.MANAGED_CHANGED, SyncStatus.UNKNOWN):
            target_set = (
                result.copied
                if self._copy_and_record(
                    managed_file,
                    target_file,
                    managed_file,
                    target_file,
                )
                else result.failed
            )
            target_set.add(item_name)
        elif status == SyncStatus.TARGET_CHANGED:
            target_set = (
                result.reverse_copied
                if self._copy_and_record(
                    target_file,
                    managed_file,
                    managed_file,
                    target_file,
                )
                else result.failed
            )
            target_set.add(item_name)

    def _resolve_conflict(
        self,
        item_name: str,
        managed_file: Path,
        target_file: Path,
        result: CopyResult,
        conflict_callback: Callable[[Path, Path], str] | None,
    ) -> None:
        """Resolve a bidirectional conflict via user callback."""
        action = conflict_callback(managed_file, target_file) if conflict_callback else CopyConflictAction.SKIP

        if action == CopyConflictAction.MANAGED:
            target_set = (
                result.copied
                if self._copy_and_record(
                    managed_file,
                    target_file,
                    managed_file,
                    target_file,
                )
                else result.failed
            )
            target_set.add(item_name)
        elif action == CopyConflictAction.TARGET:
            target_set = (
                result.reverse_copied
                if self._copy_and_record(
                    target_file,
                    managed_file,
                    managed_file,
                    target_file,
                )
                else result.failed
            )
            target_set.add(item_name)
        else:
            result.skipped.add(item_name)

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
