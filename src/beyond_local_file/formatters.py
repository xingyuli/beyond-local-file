"""Result formatters for CLI output."""

from pathlib import Path
from typing import Protocol

import click

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
