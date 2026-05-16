"""link check subcommand — operation logic and output formatting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ..copy_manager import CopyManager
from ..link_strategy_protocol import (
    CopyCheckDetails,
    GitExcludeCheckResult,
    LinkCheckResult,
)
from ..model.processing import LinkStrategy, ProcessingUnit
from ..options import OutputFormat
from ..symlink_manager import SymlinkManager
from .base import CmdOperation

# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class ProcessingUnitResults:
    """Raw results collected from a single ProcessingUnit during a check.

    Attributes:
        unit: The processing unit that was checked.
        symlink_link_result: LinkCheckResult from SymlinkManager (None if no symlink items).
        symlink_git_result: GitExcludeCheckResult from SymlinkManager (None if not a git repo
            or no symlink items).
        copy_link_result: LinkCheckResult from CopyManager (None if no copy items).
        copy_git_result: GitExcludeCheckResult from CopyManager (None if not a git repo or
            no copy items).
    """

    unit: ProcessingUnit
    symlink_link_result: LinkCheckResult | None = None
    symlink_git_result: GitExcludeCheckResult | None = None
    copy_link_result: LinkCheckResult | None = None
    copy_git_result: GitExcludeCheckResult | None = None


@dataclass
class CheckRow:
    """A single row of check results ready for table rendering.

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


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


class LinkCheckFormatter:
    """Formats and prints detailed (verbose) check results for a single project.

    Handles output for both symlink and copy strategies uniformly.
    """

    def __init__(
        self,
        link_result: LinkCheckResult,
        git_result: GitExcludeCheckResult | None = None,
        show_extra: bool = False,
    ) -> None:
        """Initialize the formatter.

        Args:
            link_result: Result of the link check operation.
            git_result: Optional result of the git exclude check.
            show_extra: Whether to show extra exclude entries.
        """
        self.link_result = link_result
        self.git_result = git_result
        self.show_extra = show_extra

    def print(self, project_name: str, target_path: Path) -> None:
        """Print all output lines for this check result.

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
        label = "Copy Status" if isinstance(self.link_result.details, CopyCheckDetails) else "Symlink Status"
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
        if not isinstance(self.link_result.details, CopyCheckDetails):
            return
        details = self.link_result.details
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


class CheckTableRenderer:
    """Transforms raw :class:`ProcessingUnitResults` into :class:`CheckRow` objects.

    Handles merging of git exclude results from both strategies so the table
    formatter receives a single, unified result per row.
    """

    def __init__(self, results: list[ProcessingUnitResults]) -> None:
        """Initialize the renderer.

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
            git_result = self._merge_git_results(result.symlink_git_result, result.copy_git_result)
            rows.append(
                CheckRow(
                    project_name=result.unit.display_name,
                    target_path=result.unit.target_project_path,
                    symlink_link_result=result.symlink_link_result,
                    copy_link_result=result.copy_link_result,
                    git_result=git_result,
                )
            )
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
        return GitExcludeCheckResult(
            present=symlink_result.present | copy_result.present,
            missing=symlink_result.missing | copy_result.missing,
            extra=symlink_result.extra | copy_result.extra,
        )


class CheckTableFormatter:
    """Formats multiple check results as a compact Rich table.

    Renders one row per (project, target) pair, followed by an optional
    section listing extra exclude entries when ``show_extra`` is True.
    """

    def __init__(self, rows: list[CheckRow], show_extra: bool = False) -> None:
        """Initialize the table formatter.

        Args:
            rows: Collected check results to render.
            show_extra: Whether to show extra exclude entries below the table.
        """
        self.rows = rows
        self.show_extra = show_extra
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
            cells = [row.project_name, self._symlink_cell(row.symlink_link_result), self._exclude_cell(row.git_result)]
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


# ---------------------------------------------------------------------------
# Operation
# ---------------------------------------------------------------------------


class CheckOperation(CmdOperation):
    """Encapsulates the check operation logic for symlinks and copies.

    Supports two output formats:
    - ``OutputFormat.TABLE`` (default): collects all results and renders a compact
      Rich table after all projects are processed via :meth:`render`.
    - ``OutputFormat.VERBOSE``: prints detailed per-project output immediately.
    """

    def __init__(
        self,
        config_dir: Path,
        show_extra: bool = False,
        output_format: OutputFormat = OutputFormat.TABLE,
    ) -> None:
        """Initialize the check operation.

        Args:
            config_dir: Directory where the config file lives.
            show_extra: Whether to show extra exclude entries.
            output_format: Output format — TABLE (default) or VERBOSE.
        """
        self.config_dir = config_dir
        self.show_extra = show_extra
        self.output_format = output_format
        self._results: list[ProcessingUnitResults] = []

    @property
    def verbose_progress(self) -> bool:
        """Whether to print per-target progress lines during processing."""
        return self.output_format == OutputFormat.VERBOSE

    def execute_unit(self, unit: ProcessingUnit) -> bool:
        """Execute the check operation for a single processing unit.

        Partitions items by strategy, delegates to the appropriate managers,
        then either prints verbose output immediately or accumulates results
        for deferred table rendering.

        Args:
            unit: The processing unit to check.

        Returns:
            Always True to continue processing.
        """
        symlink_items = [i for i in unit.items if i.strategy == LinkStrategy.SYMLINK]
        copy_items = [i for i in unit.items if i.strategy == LinkStrategy.COPY]

        symlink_mgr = SymlinkManager(symlink_items, unit.target_project_path) if symlink_items else None
        copy_mgr = CopyManager(copy_items, unit.target_project_path, self.config_dir) if copy_items else None

        # Aggregate all valid entry names for git exclude checking across strategies
        all_valid_entries: set[str] = set()
        if symlink_mgr:
            all_valid_entries.update(i.name for i in symlink_mgr.get_managed_items())
        if copy_mgr:
            all_valid_entries.update(i.name for i in copy_mgr.get_managed_items())

        if self.output_format == OutputFormat.VERBOSE:
            self._execute_verbose(unit, symlink_mgr, copy_mgr, all_valid_entries)
        else:
            self._execute_table(unit, symlink_mgr, copy_mgr, all_valid_entries)

        return True

    def _execute_verbose(
        self,
        unit: ProcessingUnit,
        symlink_mgr: SymlinkManager | None,
        copy_mgr: CopyManager | None,
        all_valid_entries: set[str],
    ) -> None:
        """Run check and print verbose output immediately.

        Args:
            unit: The processing unit being checked.
            symlink_mgr: SymlinkManager for symlink items, or None.
            copy_mgr: CopyManager for copy items, or None.
            all_valid_entries: All managed item names across both strategies.
        """
        if symlink_mgr:
            link_result = symlink_mgr.check_links()
            git_result = (
                symlink_mgr.check_git_excludes(all_valid_entries) if symlink_mgr.git_manager.is_git_repo() else None
            )
            LinkCheckFormatter(link_result, git_result, self.show_extra).print(
                unit.display_name, unit.target_project_path
            )

        if copy_mgr:
            link_result = copy_mgr.check_links()
            git_result = copy_mgr.check_git_excludes(all_valid_entries) if copy_mgr.git_manager.is_git_repo() else None
            LinkCheckFormatter(link_result, git_result, self.show_extra).print(
                unit.display_name, unit.target_project_path
            )

    def _execute_table(
        self,
        unit: ProcessingUnit,
        symlink_mgr: SymlinkManager | None,
        copy_mgr: CopyManager | None,
        all_valid_entries: set[str],
    ) -> None:
        """Run check and accumulate results for deferred table rendering.

        Args:
            unit: The processing unit being checked.
            symlink_mgr: SymlinkManager for symlink items, or None.
            copy_mgr: CopyManager for copy items, or None.
            all_valid_entries: All managed item names across both strategies.
        """
        symlink_link_result = None
        symlink_git_result = None
        if symlink_mgr:
            symlink_link_result = symlink_mgr.check_links()
            if symlink_mgr.git_manager.is_git_repo():
                symlink_git_result = symlink_mgr.check_git_excludes(all_valid_entries)

        copy_link_result = None
        copy_git_result = None
        if copy_mgr:
            copy_link_result = copy_mgr.check_links()
            if copy_mgr.git_manager.is_git_repo():
                copy_git_result = copy_mgr.check_git_excludes(all_valid_entries)

        self._results.append(
            ProcessingUnitResults(
                unit=unit,
                symlink_link_result=symlink_link_result,
                symlink_git_result=symlink_git_result,
                copy_link_result=copy_link_result,
                copy_git_result=copy_git_result,
            )
        )

    def render(self) -> None:
        """Render collected results as a table.

        No-op when ``output_format`` is VERBOSE since output is already printed.
        """
        if self.output_format != OutputFormat.VERBOSE and self._results:
            rows = CheckTableRenderer(self._results).transform()
            CheckTableFormatter(rows, self.show_extra).render()
