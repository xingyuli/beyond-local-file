"""Result formatters for CLI output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import click
from rich.console import Console
from rich.table import Table

from .link_strategy_protocol import (
    CopyCheckDetails,
    CopyCreateDetails,
    GitExcludeAddResult,
    GitExcludeCheckResult,
    LinkCheckResult,
    LinkCreateResult,
)
from .model.processing import ProcessingUnit


class ResultFormatter(Protocol):
    """Protocol for result formatters."""

    def format(self, project_name: str, target_path: Path) -> None:
        """Format and output the result."""
        ...


class LinkSyncFormatter:
    """Formatter for link sync operation results (unified protocol).

    Handles output for link creation operations using the unified protocol types.
    Works uniformly across different link strategies (symlink, copy).
    """

    def __init__(
        self,
        project_name: str,
        project_directory: Path,
        link_result: LinkCreateResult,
        git_result: GitExcludeAddResult | None = None,
    ):
        """Initialize formatter with unified protocol results.

        Args:
            project_name: Name of the project that was synced.
            project_directory: Directory path of the managed project.
            link_result: Result of link creation operation.
            git_result: Optional result of git exclude operation.
        """
        self.project_name = project_name
        self.project_directory = project_directory
        self.link_result = link_result
        self.git_result = git_result

    def format(self, project_name: str, target_path: Path) -> None:
        """Format and output link sync result.

        Args:
            project_name: Name of the project.
            target_path: Target path where links were created.
        """
        self._format_already_correct(target_path)
        self._format_created(target_path)
        self._format_reverse_copied(target_path)
        self._format_skipped(target_path)
        self._format_failed()
        self._format_git_entries()
        self._format_progress()

    def _format_already_correct(self, target_path: Path) -> None:
        """Format already correct links."""
        for item in sorted(self.link_result.already_correct):
            source_path = self.project_directory / item
            link_path = target_path / item

            # Detect strategy from details
            if isinstance(self.link_result.details, CopyCreateDetails):
                click.echo(f"Copy already in sync: {item}")
            else:
                click.echo(f"Symlink already correct: {link_path} -> {source_path}")

    def _format_created(self, target_path: Path) -> None:
        """Format newly created links."""
        for item in sorted(self.link_result.created):
            source_path = self.project_directory / item
            link_path = target_path / item

            # Detect strategy from details
            if isinstance(self.link_result.details, CopyCreateDetails):
                click.echo(f"Copied: {item} -> {link_path}")
            else:
                click.echo(f"Created symlink: {link_path} -> {source_path}")

    def _format_skipped(self, target_path: Path) -> None:
        """Format skipped links."""
        for item in sorted(self.link_result.skipped):
            link_path = target_path / item

            # Detect strategy from details
            if isinstance(self.link_result.details, CopyCreateDetails):
                click.echo(f"Copy skipped: {item}")
            else:
                click.echo(f"Skipped: {link_path}")

    def _format_failed(self) -> None:
        """Format failed links."""
        for item in sorted(self.link_result.failed):
            # Detect strategy from details
            if isinstance(self.link_result.details, CopyCreateDetails):
                click.echo(f"Copy failed: {item}")
            else:
                click.echo(f"Failed to create symlink: {item}")

    def _format_git_entries(self) -> None:
        """Format Git exclude entries."""
        if self.git_result is None:
            return

        for item in sorted(self.git_result.existing):
            click.echo(f"Git exclude already have: {item}")

        if self.git_result.added > 0:
            click.echo(f"Added {self.git_result.added} entries to .git/info/exclude")

    def _format_progress(self) -> None:
        """Format progress information if operation was aborted."""
        if self.link_result.progress.aborted:
            click.echo(
                f"Operation aborted: {self.link_result.progress.completed_items}/"
                f"{self.link_result.progress.total_items} items processed"
            )

    def _format_reverse_copied(self, target_path: Path) -> None:
        """Format reverse-copied items (copy strategy only)."""
        if not isinstance(self.link_result.details, CopyCreateDetails):
            return

        for item in sorted(self.link_result.details.reverse_copied):
            click.echo(f"Reverse synced: {item} (target -> managed)")


class LinkCheckFormatter:
    """Formatter for link check operation results (unified protocol).

    Handles check output for both symlink and copy strategies uniformly.
    """

    def __init__(
        self,
        link_result: LinkCheckResult,
        git_result: GitExcludeCheckResult | None = None,
        show_extra: bool = False,
    ):
        """Initialize formatter with unified protocol results.

        Args:
            link_result: Result of link check operation.
            git_result: Optional result of git exclude check.
            show_extra: Whether to show extra exclude entries.
        """
        self.link_result = link_result
        self.git_result = git_result
        self.show_extra = show_extra

    def format(self, project_name: str, target_path: Path) -> None:
        """Format and output check result.

        Args:
            project_name: Name of the project.
            target_path: Target path that was checked.
        """
        click.echo(f"\nChecking {project_name} -> {target_path}")
        click.echo("=" * 60)
        self._format_link_status()
        self._format_copy_details()
        self._format_exclude_status()

    def _format_link_status(self) -> None:
        """Format link status (exists/missing/incorrect)."""
        # Detect strategy from details type
        if isinstance(self.link_result.details, CopyCheckDetails):
            label = "Copy Status"
        else:
            label = "Symlink Status"

        has_issues = self.link_result.missing or self.link_result.incorrect

        if has_issues:
            click.echo(f"\n{label}:")
            click.echo(f"  Exists: {len(self.link_result.exists)}")
            for item in self.link_result.exists:
                click.echo(f"    ✓ {item}")

            if self.link_result.incorrect:
                click.echo(f"  Incorrect: {len(self.link_result.incorrect)}")
                for item in self.link_result.incorrect:
                    click.echo(f"    ⚠ {item} (points to wrong source)")

            if self.link_result.missing:
                click.echo(f"  Missing: {len(self.link_result.missing)}")
                for item in self.link_result.missing:
                    click.echo(f"    ✗ {item}")
        else:
            click.echo(f"\n{label}: ✓")

    def _format_copy_details(self) -> None:
        """Format copy-specific sync status details."""
        if not isinstance(self.link_result.details, CopyCheckDetails):
            return

        details = self.link_result.details

        # Show detailed sync status for copy items
        click.echo("\nCopy Sync Status:")
        for item in details.in_sync:
            click.echo(f"  ✓ {item} (in sync)")
        for item in details.manually_synced:
            click.echo(f"  ✓ {item} (manually synced)")
        for item in details.managed_changed:
            click.echo(f"  ⚠ {item} (managed changed)")
        for item in details.target_changed:
            click.echo(f"  ⚠ {item} (target changed)")
        for item in details.both_changed:
            click.echo(f"  ✗ {item} (conflict - both changed)")

    def _format_exclude_status(self) -> None:
        """Format Git exclude status section."""
        if self.git_result is None:
            click.echo("\nTarget is not a git repository")
            return

        has_exclude_data = (
            self.git_result.present or self.git_result.missing or (self.show_extra and self.git_result.extra)
        )

        if not has_exclude_data:
            click.echo("\nTarget is not a git repository")
            return

        if self.git_result.missing:
            click.echo("\nGit Exclude Status:")
            click.echo(f"  Missing entries: {len(self.git_result.missing)}")
            for item in sorted(self.git_result.missing):
                click.echo(f"    ✗ {item}")
        else:
            click.echo("\nGit Exclude Status: ✓")

        if self.show_extra and self.git_result.extra:
            click.echo(f"  Extra entries: {len(self.git_result.extra)}")
            for item in sorted(self.git_result.extra):
                click.echo(f"    ! {item}")


@dataclass
class CheckRow:
    """A single row of check results for table rendering.

    This class reorganizes raw protocol results into a reader-friendly format.

    IMPORTANT: There is a hidden relationship between link strategies and table columns:
    - symlink_link_result → "Symlink" column
    - copy_link_result → "Copy" column
    - git_result → "Exclude" column (shared across strategies)

    This design is acceptable for now as we only have two strategies. If more strategies
    are added in the future, consider a more flexible column mapping approach.

    Attributes:
        project_name: Name of the project.
        target_path: Target path that was checked.
        symlink_link_result: LinkCheckResult from symlink strategy (None if no symlink items).
        copy_link_result: LinkCheckResult from copy strategy (None if no copy items).
        git_result: Merged git exclude result (shared across strategies).
    """

    project_name: str
    target_path: Path
    symlink_link_result: LinkCheckResult | None = None
    copy_link_result: LinkCheckResult | None = None
    git_result: GitExcludeCheckResult | None = None


class CheckTableFormatter:
    """Formats multiple check results as a compact table.

    Renders a Rich table with one row per (project, target) pair, followed
    by a section listing extra exclude entries when ``show_extra`` is True.
    """

    def __init__(self, rows: list[CheckRow], show_extra: bool = False):
        """Initialize the table formatter.

        Args:
            rows: Collected check results to render.
            show_extra: Whether to show extra exclude entries below the table.
        """
        self.rows = rows
        self.show_extra = show_extra
        # Detect if any row has copy strategy
        self._has_copy = any(row.copy_link_result is not None for row in rows)

    def render(self) -> None:
        """Render the table and optional extra-exclude section to stdout."""
        console = Console()

        table = Table(show_header=True, header_style="bold")
        table.add_column("Project")
        table.add_column("Symlink", justify="center")
        table.add_column("Exclude", justify="center")
        if self._has_copy:
            table.add_column("Copy", justify="center")
        table.add_column("Target Path")

        for row in self.rows:
            symlink_cell = self._symlink_cell(row.symlink_link_result)
            exclude_cell = self._exclude_cell(row.git_result)
            cells = [row.project_name, symlink_cell, exclude_cell]
            if self._has_copy:
                cells.append(self._copy_cell(row.copy_link_result))
            cells.append(str(row.target_path))
            table.add_row(*cells)

        console.print(table)

        if self.show_extra:
            self._render_extra_entries(console)

    def _symlink_cell(self, link_result: LinkCheckResult | None) -> str:
        """Build the symlink status cell text.

        Args:
            link_result: The link check result for this row, or None if no symlink items.

        Returns:
            A short status string: ✓ when all symlinks exist and are correct,
            ⚠ when some are incorrect, or ✗ when some are missing.
        """
        if link_result is None:
            return "[dim]n/a[/dim]"

        issues = []
        if link_result.missing:
            issues.append(f"{len(link_result.missing)} missing")
        if link_result.incorrect:
            issues.append(f"{len(link_result.incorrect)} incorrect")

        if issues:
            status = "[red]✗[/red]" if link_result.missing else "[yellow]⚠[/yellow]"
            return f"{status} ({', '.join(issues)})"

        return "[green]✓[/green]"

    def _exclude_cell(self, git_result: GitExcludeCheckResult | None) -> str:
        """Build the git exclude status cell text.

        Args:
            git_result: The git exclude check result for this row, or None if not a git repo.

        Returns:
            A short status string indicating exclude health and extra entry count.
        """
        if git_result is None:
            return "[dim]n/a[/dim]"

        has_exclude_data = git_result.present or git_result.missing or (self.show_extra and git_result.extra)
        if not has_exclude_data:
            return "[dim]n/a[/dim]"

        if git_result.missing:
            return f"[red]✗ ({len(git_result.missing)} missing)[/red]"

        extra_count = len(git_result.extra) if self.show_extra and git_result.extra else 0
        if extra_count:
            return f"[green]✓[/green] [dim](+{extra_count})[/dim]"
        return "[green]✓[/green]"

    def _render_extra_entries(self, console: Console) -> None:
        """Render the extra exclude entries section below the table.

        Args:
            console: Rich console to write output to.
        """
        extras = [
            (row.project_name, sorted(row.git_result.extra))
            for row in self.rows
            if row.git_result and row.git_result.extra
        ]
        if not extras:
            return

        console.print("\nExtra exclude entries:")
        for project_name, entries in extras:
            console.print(f"  {project_name}: {', '.join(entries)}")

    def _copy_cell(self, link_result: LinkCheckResult | None) -> str:
        """Build the copy sync status cell text.

        Args:
            link_result: The link check result. If details is CopyCheckDetails,
                        renders copy-specific status; otherwise returns n/a.

        Returns:
            A short status string for the Copy column.
        """
        if link_result is None:
            return "[dim]n/a[/dim]"

        if not isinstance(link_result.details, CopyCheckDetails):
            return "[dim]n/a[/dim]"

        details = link_result.details

        problems = (
            len(details.managed_changed)
            + len(details.target_changed)
            + len(details.both_changed)
            + len(link_result.missing)
        )
        manually_synced_count = len(details.manually_synced)

        if problems:
            parts: list[str] = []
            if link_result.missing:
                parts.append(f"{len(link_result.missing)} missing")
            if details.both_changed:
                parts.append(f"{len(details.both_changed)} conflict")
            out_of_sync = len(details.managed_changed) + len(details.target_changed)
            if out_of_sync:
                parts.append(f"{out_of_sync} out of sync")
            return f"[red]✗ ({', '.join(parts)})[/red]"

        if manually_synced_count:
            return f"[green]✓[/green] [dim](+{manually_synced_count} manual)[/dim]"
        return "[green]✓[/green]"


@dataclass
class ProcessingUnitResults:
    """Raw results from a single ProcessingUnit.

    Attributes:
        unit: The processing unit that was checked.
        symlink_link_result: LinkCheckResult from SymlinkManager (None if no symlink items).
        symlink_git_result: GitExcludeCheckResult from SymlinkManager (None if no git repo or no symlink items).
        copy_link_result: LinkCheckResult from CopyManager (None if no copy items).
        copy_git_result: GitExcludeCheckResult from CopyManager (None if no git repo or no copy items).
    """

    unit: ProcessingUnit
    symlink_link_result: LinkCheckResult | None = None
    symlink_git_result: GitExcludeCheckResult | None = None
    copy_link_result: LinkCheckResult | None = None
    copy_git_result: GitExcludeCheckResult | None = None


class CheckTableRenderer:
    """Transforms raw protocol results into reader-friendly table rows.

    This class encapsulates the logic for reorganizing results from multiple
    ProcessingUnits into CheckRow objects suitable for table rendering.

    The transformation handles:
    - Merging symlink and copy results for the same target
    - Combining git exclude results from both strategies
    - Creating empty results for missing strategies
    """

    def __init__(self, results: list[ProcessingUnitResults]):
        """Initialize renderer with raw results.

        Args:
            results: List of raw results from all ProcessingUnits.
        """
        self.results = results

    def transform(self) -> list[CheckRow]:
        """Transform raw results into CheckRow objects for table rendering.

        Returns:
            List of CheckRow objects, one per (project, target) pair.
        """
        rows = []
        for result in self.results:
            # Merge git exclude results from both strategies
            git_result = self._merge_git_results(result.symlink_git_result, result.copy_git_result)

            row = CheckRow(
                project_name=result.unit.display_name,
                target_path=result.unit.target_project_path,
                symlink_link_result=result.symlink_link_result,
                copy_link_result=result.copy_link_result,
                git_result=git_result,
            )
            rows.append(row)

        return rows

    def _merge_git_results(
        self,
        symlink_result: GitExcludeCheckResult | None,
        copy_result: GitExcludeCheckResult | None,
    ) -> GitExcludeCheckResult | None:
        """Merge git exclude results from symlink and copy strategies.

        Args:
            symlink_result: Git exclude result from symlink strategy.
            copy_result: Git exclude result from copy strategy.

        Returns:
            Merged git exclude result, or None if both are None.
        """
        if symlink_result is None and copy_result is None:
            return None

        if symlink_result is None:
            return copy_result

        if copy_result is None:
            return symlink_result

        # Both results exist - merge them
        return GitExcludeCheckResult(
            present=symlink_result.present | copy_result.present,
            missing=symlink_result.missing | copy_result.missing,
            extra=symlink_result.extra | copy_result.extra,
        )
