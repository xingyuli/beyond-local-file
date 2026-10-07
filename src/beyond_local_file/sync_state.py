"""Live hash comparison for copy projections.

Match is in-sync. Mismatch is labeled from the baseline when one exists.
There is no persisted ``sync-state.yml``.
"""

from __future__ import annotations

import hashlib
import os
from enum import StrEnum
from pathlib import Path

from .daemon.live import compute_file_hash, scan_items
from .daemon.store import BaselineTrees, get_state, state_equal
from .discovery import item_covers_rel


class SyncStatus(StrEnum):
    """Live copy status for a managed item vs its projection.

    Attributes:
        IN_SYNC: Managed and target hashes match right now.
        MISMATCH: Hashes differ and there is no baseline to label which side moved.
        MANAGED_CHANGED: Live mismatch; only the managed side differs from baseline.
        TARGET_CHANGED: Live mismatch; only the target side differs from baseline.
        BOTH_CHANGED: Live mismatch; both sides differ from baseline.
    """

    IN_SYNC = "in_sync"
    MISMATCH = "mismatch"
    MANAGED_CHANGED = "managed_changed"
    TARGET_CHANGED = "target_changed"
    BOTH_CHANGED = "both_changed"


def compute_item_hash(path: Path) -> str:
    """Compute a SHA-256 hash of a file or directory tree.

    Args:
        path: File or directory to hash.

    Returns:
        Hex-encoded SHA-256 digest of the file contents or of the
        directory's relative paths and file contents.
    """
    if path.is_dir():
        return _compute_directory_hash(path)
    return compute_file_hash(path)


type BaselineView = tuple[BaselineTrees, Path, Path, str]


def detect_status(
    managed_file: Path,
    target_file: Path,
    baseline: BaselineView | None = None,
) -> SyncStatus:
    """Classify live hashes of managed vs target, labeling from baseline.

    Args:
        managed_file: Absolute path to the managed item.
        target_file: Absolute path to the target projection.
        baseline: Optional ``(trees, managed_root, target_root, item_name)``.

    Returns:
        A SyncStatus value describing the live relationship.
    """
    if compute_item_hash(managed_file) == compute_item_hash(target_file):
        return SyncStatus.IN_SYNC
    if baseline is None:
        return SyncStatus.MISMATCH
    trees, managed_root, target_root, item_name = baseline
    managed_changed = _item_changed(trees, managed_root, item_name)
    target_changed = _item_changed(trees, target_root, item_name)
    if not managed_changed and not target_changed:
        return SyncStatus.MISMATCH
    if managed_changed and target_changed:
        return SyncStatus.BOTH_CHANGED
    if managed_changed:
        return SyncStatus.MANAGED_CHANGED
    return SyncStatus.TARGET_CHANGED


def _compute_directory_hash(directory: Path) -> str:
    """Hash a directory by walking relative paths and file contents."""
    sha256 = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(directory, followlinks=False):
        dirnames.sort()
        filenames.sort()
        rel_dir = Path(dirpath).relative_to(directory).as_posix()
        sha256.update(b"dir:")
        sha256.update(rel_dir.encode())
        for name in filenames:
            file_path = Path(dirpath) / name
            rel_file = name if rel_dir == "." else f"{rel_dir}/{name}"
            sha256.update(b"file:")
            sha256.update(rel_file.encode())
            if file_path.is_symlink():
                sha256.update(b"symlink:")
                sha256.update(os.fsencode(os.readlink(file_path)))
            elif file_path.is_file():
                sha256.update(compute_file_hash(file_path).encode())
    return sha256.hexdigest()


def _item_changed(baseline: BaselineTrees, root: Path, item_name: str) -> bool:
    live = scan_items(root, [item_name])
    stored = baseline.get(str(root), {})
    rels = set(live) | {rel for rel in stored if item_covers_rel(item_name, rel)}
    if not any(item_covers_rel(item_name, rel) for rel in stored):
        return False
    return any(not state_equal(live.get(rel), get_state(baseline, root, rel)) for rel in rels)
