"""Enumerated option values for CLI commands.

All fixed option value sets must be defined here to avoid magic strings
scattered across the codebase.
"""

from enum import Enum, StrEnum


class ConflictResolution(Enum):
    """User-facing actions when a path conflict is detected during sync.

    Presented as a numbered prompt — users type 1, 2, or 3 to choose.

    Attributes:
        SKIP: Leave the existing path untouched and continue.
        OVERWRITE: Remove the existing path and create the link.
        ABORT: Stop the sync operation immediately.
    """

    SKIP = 1
    OVERWRITE = 2
    ABORT = 3


class CopyConflictResolution(StrEnum):
    """User-facing resolution choices when a bidirectional copy conflict is detected.

    Presented as a single-letter prompt — users type m, t, or s to choose.

    Attributes:
        MANAGED: Overwrite the target with the managed (source) file.
        TARGET: Overwrite the managed file with the target file (reverse sync).
        SKIP: Leave both files unchanged.
    """

    MANAGED = "managed"
    TARGET = "target"
    SKIP = "skip"


class OutputFormat(StrEnum):
    """Output format options for the check command.

    Attributes:
        TABLE: Compact Rich table — one row per (project, target) pair.
        VERBOSE: Detailed per-project output printed as each result arrives.
    """

    TABLE = "table"
    VERBOSE = "verbose"
