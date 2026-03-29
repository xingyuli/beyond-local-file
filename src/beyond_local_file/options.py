"""Enumerated option values for CLI commands.

All fixed option value sets must be defined here to avoid magic strings
scattered across the codebase.
"""

from enum import StrEnum


class OutputFormat(StrEnum):
    """Output format options for the check command.

    Attributes:
        TABLE: Compact Rich table — one row per (project, target) pair.
        VERBOSE: Detailed per-project output printed as each result arrives.
    """

    TABLE = "table"
    VERBOSE = "verbose"


class LinkStrategy(StrEnum):
    """Strategy for linking a project item to the target.

    Attributes:
        SYMLINK: Create a symbolic link (default).
        COPY: Create a physical file copy.
    """

    SYMLINK = "symlink"
    COPY = "copy"


class SyncStatus(StrEnum):
    """Sync status for a copied file.

    Attributes:
        IN_SYNC: Managed and target files are identical and match recorded state.
        MANUALLY_SYNCED: Managed and target files are identical but differ from recorded state.
        MANAGED_CHANGED: Only the managed (source) file changed since last sync.
        TARGET_CHANGED: Only the target file changed since last sync.
        BOTH_CHANGED: Both files changed — conflict.
        UNKNOWN: No previous sync state recorded.
    """

    IN_SYNC = "in_sync"
    MANUALLY_SYNCED = "manually_synced"
    MANAGED_CHANGED = "managed_changed"
    TARGET_CHANGED = "target_changed"
    BOTH_CHANGED = "both_changed"
    UNKNOWN = "unknown"
