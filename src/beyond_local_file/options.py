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
