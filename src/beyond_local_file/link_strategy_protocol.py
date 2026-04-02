"""Protocol definition for link strategy managers.

This protocol defines the interface that all link strategy managers
(SymlinkManager, CopyManager) must implement, enabling polymorphic
handling of different linking strategies.
"""

from dataclasses import dataclass, field
from typing import Protocol

# Base result types with consistent naming


@dataclass
class LinkCreateResult:
    """Result of creating links (unified across all strategies).

    Attributes:
        created: Items successfully created.
        already_correct: Items already in correct state.
        skipped: Items skipped by user choice.
        failed: Items that failed to create.
        details: Strategy-specific details (optional).
    """

    created: set[str] = field(default_factory=set)
    already_correct: set[str] = field(default_factory=set)
    skipped: set[str] = field(default_factory=set)
    failed: set[str] = field(default_factory=set)
    details: "LinkCreateDetails | None" = None


@dataclass
class LinkCheckResult:
    """Result of checking link status (unified across all strategies).

    Attributes:
        exists: Items where link exists and is correct.
        missing: Items where link is missing.
        details: Strategy-specific details (optional).
    """

    exists: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    details: "LinkCheckDetails | None" = None


@dataclass
class GitExcludeAddResult:
    """Result of adding git exclude entries.

    Attributes:
        added: Number of entries added.
        existing: Set of entries that already existed.
    """

    added: int = 0
    existing: set[str] = field(default_factory=set)


@dataclass
class GitExcludeCheckResult:
    """Result of checking git exclude status.

    Attributes:
        present: Items present in git exclude.
        missing: Items missing from git exclude.
        extra: Extra entries in git exclude (not in any managed items).
    """

    present: set[str] = field(default_factory=set)
    missing: set[str] = field(default_factory=set)
    extra: set[str] = field(default_factory=set)


# Protocol for strategy-specific details


class LinkCreateDetails(Protocol):
    """Protocol for strategy-specific create details.

    Strategies can provide additional information about the create operation
    by implementing this protocol.
    """

    def get_summary(self) -> str:
        """Get a human-readable summary of strategy-specific details.

        Returns:
            Summary string describing strategy-specific information.
        """
        ...


class LinkCheckDetails(Protocol):
    """Protocol for strategy-specific check details.

    Strategies can provide additional information about the check operation
    by implementing this protocol.
    """

    def get_summary(self) -> str:
        """Get a human-readable summary of strategy-specific details.

        Returns:
            Summary string describing strategy-specific information.
        """
        ...


# Strategy-specific detail implementations


@dataclass
class CopyCreateDetails:
    """Copy-specific details for create operations.

    Attributes:
        reverse_copied: Items synced from target back to managed.
    """

    reverse_copied: set[str] = field(default_factory=set)

    def get_summary(self) -> str:
        """Get summary of copy-specific create details."""
        if self.reverse_copied:
            return f"Reverse copied: {len(self.reverse_copied)} items"
        return "No reverse copies"


@dataclass
class CopyCheckDetails:
    """Copy-specific details for check operations.

    Attributes:
        in_sync: Items in sync (content matches).
        manually_synced: Items manually synced (content matches but state outdated).
        managed_changed: Items where managed file changed.
        target_changed: Items where target file changed.
        both_changed: Items where both sides changed (conflict).
    """

    in_sync: list[str] = field(default_factory=list)
    manually_synced: list[str] = field(default_factory=list)
    managed_changed: list[str] = field(default_factory=list)
    target_changed: list[str] = field(default_factory=list)
    both_changed: list[str] = field(default_factory=list)

    def get_summary(self) -> str:
        """Get summary of copy-specific check details."""
        parts = []
        if self.in_sync:
            parts.append(f"In sync: {len(self.in_sync)}")
        if self.manually_synced:
            parts.append(f"Manually synced: {len(self.manually_synced)}")
        if self.managed_changed:
            parts.append(f"Managed changed: {len(self.managed_changed)}")
        if self.target_changed:
            parts.append(f"Target changed: {len(self.target_changed)}")
        if self.both_changed:
            parts.append(f"Conflicts: {len(self.both_changed)}")
        return ", ".join(parts) if parts else "No details"


class LinkStrategyManager(Protocol):
    """Protocol for managing link operations (symlink or copy).

    All link strategy managers must implement this interface to provide
    uniform operations for creating, checking, and managing links.

    This protocol defines two groups of operations:
    1. Link operations: create_links() and check_links()
    2. Git exclude operations: add_git_excludes() and check_git_excludes()
    """

    def get_managed_items(self) -> list:
        """Return the list of items this manager handles.

        Returns:
            List of ProjectItem instances managed by this manager.
        """
        ...

    def create_links(self) -> LinkCreateResult:
        """Create all links for managed items.

        Returns:
            LinkCreateResult with created, skipped, failed items.
        """
        ...

    def check_links(self) -> LinkCheckResult:
        """Check status of all links for managed items.

        Returns:
            LinkCheckResult with exists, missing items.
        """
        ...

    def add_git_excludes(self) -> GitExcludeAddResult:
        """Add git exclude entries for all managed items.

        Returns:
            GitExcludeAddResult with added count and existing entries.
        """
        ...

    def check_git_excludes(self, all_valid_entries: set[str]) -> GitExcludeCheckResult:
        """Check git exclude status for managed items.

        Args:
            all_valid_entries: Set of ALL valid entry names from all managers.
                             Used to identify extra/stale entries.

        Returns:
            GitExcludeCheckResult with present, missing, extra entries.
        """
        ...
