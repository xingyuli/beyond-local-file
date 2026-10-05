"""link check subcommand — operation logic and output formatting."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ..daemon.store import BaselineTrees
from ..git_manager import GitExcludeManager
from ..model.processing import MappingUnit
from ..options import OutputFormat
from ..sync_state import SyncStatus, detect_status
from .base import CmdOperation

type ItemProgress = Callable[[int, int, str], None]


@dataclass
class CopyCheckDetails:
    """Live hash labels for copy projections."""

    in_sync: list[str] = field(default_factory=list)
    mismatched: list[str] = field(default_factory=list)
    managed_changed: list[str] = field(default_factory=list)
    target_changed: list[str] = field(default_factory=list)
    both_changed: list[str] = field(default_factory=list)


@dataclass
class LinkCheckResult:
    """Result of checking copy projections on one mapping unit."""

    exists: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    incorrect: list[str] = field(default_factory=list)
    details: CopyCheckDetails = field(default_factory=CopyCheckDetails)


@dataclass
class GitExcludeStatus:
    """Git exclude present, missing, and extra entries for one target."""

    present: set[str] = field(default_factory=set)
    missing: set[str] = field(default_factory=set)
    extra: set[str] = field(default_factory=set)


@dataclass
class MappingUnitResults:
    """Raw results collected from a single mapping unit during a check."""

    unit: MappingUnit
    copy_link_result: LinkCheckResult | None = None
    git_result: GitExcludeStatus | None = None


@dataclass
class CheckRow:
    """A single row of check results ready for table rendering."""

    project_name: str
    target_path: Path
    copy_link_result: LinkCheckResult | None = None
    git_result: GitExcludeStatus | None = None


class LinkCheckFormatter:
    """Formats and prints detailed (verbose) check results for a single project."""

    def __init__(
        self,
        link_result: LinkCheckResult,
        git_result: GitExcludeStatus | None = None,
        show_extra: bool = False,
    ) -> None:
        self.link_result = link_result
        self.git_result = git_result
        self.show_extra = show_extra

    def print(self, project_name: str, target_path: Path) -> None:
        """Print all output lines for this check result."""
        click.echo(f"\nChecking {project_name} -> {target_path}")
        click.echo("=" * 60)
        self._format_link_status()
        self._format_copy_details()
        self._format_exclude_status()

    def _format_link_status(self) -> None:
        has_issues = self.link_result.missing or self.link_result.incorrect
        if has_issues:
            click.echo("\nCopy Status:")
            click.echo(f"  Exists: {len(self.link_result.exists)}")
            for item in self.link_result.exists:
                click.echo(f"    ✓ {item}")
            if self.link_result.incorrect:
                click.echo(f"  Incorrect: {len(self.link_result.incorrect)}")
                for item in self.link_result.incorrect:
                    click.echo(f"    ⚠ {item} (not a copy)")
            if self.link_result.missing:
                click.echo(f"  Missing: {len(self.link_result.missing)}")
                for item in self.link_result.missing:
                    click.echo(f"    ✗ {item}")
        else:
            click.echo("\nCopy Status: ✓")

    def _format_copy_details(self) -> None:
        details = self.link_result.details
        click.echo("\nCopy Sync Status:")
        for item in details.in_sync:
            click.echo(f"  ✓ {item} (in sync)")
        for item in details.mismatched:
            click.echo(f"  ⚠ {item} (mismatch)")
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
    """Transforms raw mapping-unit results into table rows."""

    def __init__(self, results: list[MappingUnitResults]) -> None:
        self.results = results

    def transform(self) -> list[CheckRow]:
        """Transform raw results into CheckRow objects for table rendering."""
        return [
            CheckRow(
                project_name=result.unit.display_name,
                target_path=result.unit.target_project_path,
                copy_link_result=result.copy_link_result,
                git_result=result.git_result,
            )
            for result in self.results
        ]


class CheckTableFormatter:
    """Formats multiple check results as a compact Rich table."""

    def __init__(self, rows: list[CheckRow], show_extra: bool = False) -> None:
        self.rows = rows
        self.show_extra = show_extra

    def render(self) -> None:
        """Render the table and optional extra-exclude section to stdout."""
        console = Console()
        table = Table(show_header=True, header_style="bold")
        table.add_column("Project")
        table.add_column("Exclude", justify="center")
        table.add_column("Copy", justify="center")
        table.add_column("Target Path")
        for row in self.rows:
            table.add_row(
                row.project_name,
                self._exclude_cell(row.git_result),
                self._copy_cell(row.copy_link_result),
                str(row.target_path),
            )
        console.print(table)
        if self.show_extra:
            self._render_extra_entries(console)

    def _exclude_cell(self, git_result: GitExcludeStatus | None) -> str:
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
        if link_result is None:
            return "[dim]n/a[/dim]"
        details = link_result.details
        problems = (
            len(details.mismatched)
            + len(details.managed_changed)
            + len(details.target_changed)
            + len(details.both_changed)
            + len(link_result.missing)
            + len(link_result.incorrect)
        )
        if problems:
            parts: list[str] = []
            if link_result.missing:
                parts.append(f"{len(link_result.missing)} missing")
            if link_result.incorrect:
                parts.append(f"{len(link_result.incorrect)} not a copy")
            if details.both_changed:
                parts.append(f"{len(details.both_changed)} conflict")
            out_of_sync = len(details.managed_changed) + len(details.target_changed)
            if out_of_sync:
                parts.append(f"{out_of_sync} out of sync")
            if details.mismatched:
                parts.append(f"{len(details.mismatched)} mismatch")
            return f"[red]✗ ({', '.join(parts)})[/red]"
        return "[green]✓[/green]"

    def _render_extra_entries(self, console: Console) -> None:
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


class CheckOperation(CmdOperation):
    """Check live copy projections and git exclude entries per mapping unit."""

    def __init__(
        self,
        config_dir: Path,
        show_extra: bool = False,
        output_format: OutputFormat = OutputFormat.TABLE,
    ) -> None:
        self.config_dir = config_dir
        self.show_extra = show_extra
        self.output_format = output_format
        self.baseline: BaselineTrees | None = None
        self.on_progress: ItemProgress | None = None
        self.unit_count = 0
        self._unit_index = 0
        self._results: list[MappingUnitResults] = []

    @property
    def results(self) -> list[MappingUnitResults]:
        """Return collected per-mapping-unit check results."""
        return list(self._results)

    def extend_results(self, results: list[MappingUnitResults]) -> None:
        """Append *results* from another check run for a later table render."""
        self._results.extend(results)

    @property
    def verbose_progress(self) -> bool:
        """Whether to print per-target progress lines during processing."""
        return self.output_format == OutputFormat.VERBOSE

    def execute_unit(self, unit: MappingUnit) -> bool:
        """Check one mapping unit's copy projections and git exclude."""
        self._unit_index += 1
        item_names = {item.name for item in unit.items}
        link_result = self._check_copies(unit)
        git_result = _check_git_excludes(unit.target_project_path, item_names)
        if self.output_format == OutputFormat.VERBOSE:
            LinkCheckFormatter(link_result, git_result, self.show_extra).print(
                unit.display_name, unit.target_project_path
            )
        else:
            self._results.append(MappingUnitResults(unit=unit, copy_link_result=link_result, git_result=git_result))
        return True

    def _check_copies(self, unit: MappingUnit) -> LinkCheckResult:
        details = CopyCheckDetails()
        in_sync: list[str] = []
        missing: list[str] = []
        incorrect: list[str] = []
        for item in unit.items:
            self._emit(item.name)
            target_file = unit.target_project_path / item.name
            if target_file.is_symlink():
                incorrect.append(item.name)
                continue
            if not target_file.exists():
                missing.append(item.name)
                continue
            baseline_view = (
                (self.baseline, unit.managed_project_path, unit.target_project_path, item.name)
                if self.baseline is not None
                else None
            )
            status = detect_status(item.path, target_file, baseline_view)
            status_map = {
                SyncStatus.IN_SYNC: details.in_sync,
                SyncStatus.MISMATCH: details.mismatched,
                SyncStatus.MANAGED_CHANGED: details.managed_changed,
                SyncStatus.TARGET_CHANGED: details.target_changed,
                SyncStatus.BOTH_CHANGED: details.both_changed,
            }
            status_map[status].append(item.name)
            if status == SyncStatus.IN_SYNC:
                in_sync.append(item.name)
        return LinkCheckResult(exists=in_sync, missing=missing, incorrect=incorrect, details=details)

    def render(self) -> None:
        """Render collected results as a table."""
        if self.output_format != OutputFormat.VERBOSE and self._results:
            rows = CheckTableRenderer(self._results).transform()
            CheckTableFormatter(rows, self.show_extra).render()

    def _emit(self, item_name: str) -> None:
        if self.on_progress is None or self.output_format == OutputFormat.VERBOSE:
            return
        self.on_progress(self._unit_index, self.unit_count, item_name)


def _check_git_excludes(target_path: Path, item_names: set[str]) -> GitExcludeStatus | None:
    manager = GitExcludeManager(target_path)
    if not manager.is_git_repo():
        return None
    exclude_entries = manager.read_entries()
    return GitExcludeStatus(
        present=item_names & exclude_entries,
        missing=item_names - exclude_entries,
        extra=exclude_entries - item_names,
    )
