"""Sync state tracking for physically copied files.

Stores per-file SHA-256 hashes so that change detection can distinguish
which side (managed, target, or both) has been modified since the last sync.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .options import SyncStatus

STATE_DIR = ".blf"
STATE_FILE = "sync-state.yml"


def compute_file_hash(filepath: Path) -> str:
    """Compute the SHA-256 hash of a file.

    Args:
        filepath: Path to the file.

    Returns:
        Hex-encoded SHA-256 digest.
    """
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


@dataclass
class SyncRecord:
    """A single file's sync state.

    Attributes:
        managed_path: Absolute path to the managed (source) file.
        target_path: Absolute path to the target (copied) file.
        last_sync_hash: SHA-256 hash at the time of last successful sync.
        last_sync_time: Timestamp of last successful sync.
    """

    managed_path: str
    target_path: str
    last_sync_hash: str
    last_sync_time: str

    def to_dict(self) -> dict[str, str]:
        """Serialize to a plain dict for YAML output."""
        return {
            "managed_path": self.managed_path,
            "target_path": self.target_path,
            "last_sync_hash": self.last_sync_hash,
            "last_sync_time": self.last_sync_time,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "SyncRecord":
        """Deserialize from a plain dict."""
        return cls(
            managed_path=data["managed_path"],
            target_path=data["target_path"],
            last_sync_hash=data["last_sync_hash"],
            last_sync_time=data["last_sync_time"],
        )


@dataclass
class SyncState:
    """Manages sync state for all copied files.

    The state file lives at ``<config_dir>/.blf/sync-state.yml``
    where config_dir is the directory containing the config file.

    Attributes:
        config_dir: The directory where the config file lives.
        records: Mapping from target-relative path to its SyncRecord.
    """

    config_dir: Path
    records: dict[str, SyncRecord] = field(default_factory=dict)

    @property
    def _state_file(self) -> Path:
        return self.config_dir / STATE_DIR / STATE_FILE

    # -- persistence -----------------------------------------------------------

    def load(self) -> None:
        """Load state from disk. No-op if the file does not exist."""
        if not self._state_file.exists():
            return
        with open(self._state_file) as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
        synced_files = data.get("synced_files") or []
        for entry in synced_files:
            record = SyncRecord.from_dict(entry)
            self.records[record.target_path] = record

    def save(self) -> None:
        """Persist current state to disk."""
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"synced_files": [r.to_dict() for r in self.records.values()]}
        with open(self._state_file, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    # -- queries ---------------------------------------------------------------

    def get_record(self, target_path: str) -> SyncRecord | None:
        """Look up the sync record for a target path."""
        return self.records.get(target_path)

    def detect_status(self, managed_file: Path, target_file: Path) -> SyncStatus:
        """Detect the sync status between managed and target files.

        Args:
            managed_file: Absolute path to the managed (source) file.
            target_file: Absolute path to the target (copied) file.

        Returns:
            A SyncStatus value describing the relationship.
        """
        managed_hash = compute_file_hash(managed_file)
        target_hash = compute_file_hash(target_file)

        # If files are identical, they're in sync regardless of record
        if managed_hash == target_hash:
            return SyncStatus.IN_SYNC

        record = self.get_record(str(target_file))
        if record is None:
            # No sync record exists - treat as managed changed (needs initial sync)
            return SyncStatus.MANAGED_CHANGED

        last = record.last_sync_hash
        if managed_hash == last:
            return SyncStatus.TARGET_CHANGED
        if target_hash == last:
            return SyncStatus.MANAGED_CHANGED
        return SyncStatus.BOTH_CHANGED

    # -- mutations -------------------------------------------------------------

    def update_record(self, managed_file: Path, target_file: Path) -> None:
        """Create or update the sync record after a successful copy.

        Args:
            managed_file: Absolute path to the managed (source) file.
            target_file: Absolute path to the target (copied) file.
        """
        file_hash = compute_file_hash(target_file)
        self.records[str(target_file)] = SyncRecord(
            managed_path=str(managed_file),
            target_path=str(target_file),
            last_sync_hash=file_hash,
            last_sync_time=datetime.now(tz=UTC).isoformat(),
        )
