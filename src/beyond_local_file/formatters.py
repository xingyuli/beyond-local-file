"""Result formatters for CLI output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import click
from rich.console import Console
from rich.table import Table

from .copy_manager import CopyCheckResult, CopyResult
from .models import Project
from .symlink_manager import CheckResult, SyncResult


class ResultFormatter(Protocol):
    """Protocol for result formatters."""

    def format(self, project_name: str, target_path: Path) -> None:
        """Format and output the result."""
        ...


class SyncResultFormatter:
    """Formatter for sync operation results."""

    def __init__(self, project: Project, result: SyncResult):
        """Initialize formatter with project and result.

        Args:
            project: The project that was synced.
            result: The sync operation result.
        """
        self.project = project
        self.result = result

    def format(self, project_name: str, target_path: Path) -> None:
        """Format and output sync result.

        Args:
            project_name: Name of the project.
            target_path: Target path where symlinks were created.
        """
        self._format_already_correct(target_path)
        self._format_created(target_path)
        self._format_failed()
        self._format_git_entries()

    def _format_already_correct(self, target_path: Path) -> None:
        """Format already correct symlinks."""
        for item in sorted(self.result.already_correct):
            source_path = self.project.directory / item
            link_path = target_path / item
            click.echo(f"Symlink already correct: {link_path} -> {source_path}")

    def _format_created(self, target_path: Path) -> None:
        """Format newly created symlinks."""
        for item in sorted(self.result.created):
            source_path = self.project.directory / item
            link_path = target_path / item
            click.echo(f"Created symlink: {link_path} -> {source_path}")

    def _format_failed(self) -> None:
        """Format failed symlinks."""
        for item in sorted(self.result.failed):
            click.echo(f"Failed to create symlink: {item}")

    def _format_git_entries(self) -> None:
        """Format Git exclude entries."""
        for item in sorted(self.result.git_existing):
            click.echo(f"Git exclude already have: {item}")

        if self.result.git_added > 0:
            click.echo(f"Added {self.result.git_added} entries to .git/info/exclude")


class CheckResultFormatter:
    """Formatter for check operation results."""

    def __init__(self, result: CheckResult, show_extra: bool = False):
        """Initialize formatter with result.

        Args:
            result: The check operation result.
            show_extra: Whether to show extra exclude entries.
        """
        self.result = result
        self.show_extra = show_extra

    def format(self, project_name: str, target_path: Path) -> None:
        """Format and output check result.

        Args:
            project_name: Name of the project.
            target_path: Target path that was checked.
        """
        click.echo(f"\nChecking {project_name} -> {target_path}")
        click.echo("=" * 60)
        self._format_symlink_status()
        self._format_exclude_status()

    def _format_symlink_status(self) -> None:
        """Format symlink status section."""
        if self.result.symlink_missing:
            click.echo("\nSymlink Status:")
            click.echo(f"  Exists: {len(self.result.symlink_exists)}")
            for item in self.result.symlink_exists:
                click.echo(f"    ✓ {item}")

            click.echo(f"  Missing: {len(self.result.symlink_missing)}")
            for item in self.result.symlink_missing:
                click.echo(f"    ✗ {item}")
        else:
            click.echo("\nSymlink Status: ✓")

    def _format_exclude_status(self) -> None:
        """Format Git exclude status section."""
        has_exclude_data = (
            self.result.exclude_present
            or self.result.exclude_missing
            or (self.show_extra and self.result.exclude_extra)
        )

        if not has_exclude_data:
            click.echo("\nTarget is not a git repository")
            return

        if self.result.exclude_missing:
            click.echo("\nGit Exclude Status:")
            click.echo(f"  Missing entries: {len(self.result.exclude_missing)}")
            for item in sorted(self.result.exclude_missing):
                click.echo(f"    ✗ {item}")
        else:
            click.echo("\nGit Exclude Status: ✓")

        if self.show_extra and self.result.exclude_extra:
            click.echo(f"  Extra entries: {len(self.result.exclude_extra)}")
            for item in sorted(self.result.exclude_extra):
                click.echo(f"    ! {item}")


@dataclass
class CheckRow:
    """A single row of check results for table rendering.

    Attributes:
        project_name: Name of the project.
        target_path: Target path that was checked.
        result: The symlink check operation result.
        copy_result: Optional copy check result (None when no copy items).
    """

    project_name: str
    target_path: Path
    result: CheckResult
    copy_result: CopyCheckResult | None = None


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
        self._has_copy = any(row.copy_result is not None for row in rows)

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
            symlink_cell = self._symlink_cell(row.result)
            exclude_cell = self._exclude_cell(row.result)
            cells = [row.project_name, symlink_cell, exclude_cell]
            if self._has_copy:
                cells.append(self._copy_cell(row.copy_result))
            cells.append(str(row.target_path))
            table.add_row(*cells)

        console.print(table)

        if self.show_extra:
            self._render_extra_entries(console)

    def _symlink_cell(self, result: CheckResult) -> str:
        """Build the symlink status cell text.

        Args:
            result: The check result for this row.

        Returns:
            A short status string: ✓ when all symlinks exist, or ✗ (N missing) otherwise.
        """
        if result.symlink_missing:
            return f"[red]✗ ({len(result.symlink_missing)} missing)[/red]"
        return "[green]✓[/green]"

    def _exclude_cell(self, result: CheckResult) -> str:
        """Build the git exclude status cell text.

        Args:
            result: The check result for this row.

        Returns:
            A short status string indicating exclude health and extra entry count.
        """
        has_exclude_data = (
            result.exclude_present or result.exclude_missing or (self.show_extra and result.exclude_extra)
        )
        if not has_exclude_data:
            return "[dim]n/a[/dim]"

        if result.exclude_missing:
            return f"[red]✗ ({len(result.exclude_missing)} missing)[/red]"

        extra_count = len(result.exclude_extra) if self.show_extra and result.exclude_extra else 0
        if extra_count:
            return f"[green]✓[/green] [dim](+{extra_count})[/dim]"
        return "[green]✓[/green]"

    def _render_extra_entries(self, console: Console) -> None:
        """Render the extra exclude entries section below the table.

        Args:
            console: Rich console to write output to.
        """
        extras = [(row.project_name, sorted(row.result.exclude_extra)) for row in self.rows if row.result.exclude_extra]
        if not extras:
            return

        console.print("\nExtra exclude entries:")
        for project_name, entries in extras:
            console.print(f"  {project_name}: {', '.join(entries)}")

    def _copy_cell(self, copy_result: CopyCheckResult | None) -> str:
        """Build the copy sync status cell text.

        Args:
            copy_result: The copy check result, or None if no copy items.

        Returns:
            A short status string for the Copy column.
        """
        if copy_result is None:
            return "[dim]n/a[/dim]"

        problems = (
            len(copy_result.managed_changed)
            + len(copy_result.target_changed)
            + len(copy_result.both_changed)
            + len(copy_result.missing)
        )
        if problems:
            parts: list[str] = []
            if copy_result.missing:
                parts.append(f"{len(copy_result.missing)} missing")
            if copy_result.both_changed:
                parts.append(f"{len(copy_result.both_changed)} conflict")
            out_of_sync = len(copy_result.managed_changed) + len(copy_result.target_changed)
            if out_of_sync:
                parts.append(f"{out_of_sync} out of sync")
            return f"[red]✗ ({', '.join(parts)})[/red]"
        return "[green]✓[/green]"


class CopyResultFormatter:
    """Formatter for copy-sync operation results."""

    def __init__(self, result: CopyResult):
        """Initialize formatter with copy result.

        Args:
            result: The copy sync operation result.
        """
        self.result = result

    def format(self, project_name: str, target_path: Path) -> None:
        """Format and output copy sync result.

        Args:
            project_name: Name of the project.
            target_path: Target path where copies were placed.
        """
        for item in sorted(self.result.in_sync):
            click.echo(f"Copy already in sync: {item}")
        for item in sorted(self.result.copied):
            click.echo(f"Copied: {item} -> {target_path / item}")
        for item in sorted(self.result.reverse_copied):
            click.echo(f"Reverse synced: {item} (target -> managed)")
        for item in sorted(self.result.skipped):
            click.echo(f"Copy skipped: {item}")
        for item in sorted(self.result.failed):
            click.echo(f"Copy failed: {item}")

        # Git exclude entries
        for item in sorted(self.result.git_existing):
            click.echo(f"Git exclude already have: {item}")
        if self.result.git_added > 0:
            click.echo(f"Added {self.result.git_added} copied items to .git/info/exclude")


class CopyCheckResultFormatter:
    """Formatter for copy check results (verbose mode)."""

    def __init__(self, result: CopyCheckResult):
        """Initialize formatter with copy check result.

        Args:
            result: The copy check result.
        """
        self.result = result

    def format(self, project_name: str, target_path: Path) -> None:
        """Format and output copy check result.

        Args:
            project_name: Name of the project.
            target_path: Target path that was checked.
        """
        has_items = (
            self.result.in_sync
            or self.result.managed_changed
            or self.result.target_changed
            or self.result.both_changed
            or self.result.missing
        )
        if not has_items:
            return

        click.echo("\nCopy Status:")
        for item in self.result.in_sync:
            click.echo(f"  ✓ {item} (copied, in sync)")
        for item in self.result.managed_changed:
            click.echo(f"  ⚠ {item} (copied, managed changed)")
        for item in self.result.target_changed:
            click.echo(f"  ⚠ {item} (copied, target changed)")
        for item in self.result.both_changed:
            click.echo(f"  ✗ {item} (copied, conflict - both changed)")
        for item in self.result.missing:
            click.echo(f"  ✗ {item} (copy missing)")
