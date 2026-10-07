"""link check: projects x baseline to rows, plus render adapters."""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ..daemon.store import BaselineTrees
from ..git_manager import GitExcludeManager
from ..model.config import ConfigProject
from ..model.processing import MappingUnit
from ..model.translator import translate_config_to_mapping_units
from ..options import OutputFormat
from ..sync_state import SyncStatus, detect_status
from .result import CheckResult, CheckRow

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


def check(  # noqa: PLR0913
    projects: dict[str, ConfigProject],
    baseline: BaselineTrees | None,
    *,
    extra_exclude: bool,
    output_format: OutputFormat,
    on_progress: ItemProgress | None = None,
    unit_count: int = 0,
) -> CheckResult:
    """Check copy projections and git excludes for *projects*.

    Always walks mapping units and collects skip rows. Table vs verbose is a
    later :func:`~beyond_local_file.operations.result.render` of the same rows.
    Progress is streamed through *on_progress* regardless of output format.

    Args:
        projects: Managed projects to check.
        baseline: Baseline trees for mismatch labels, or ``None``.
        extra_exclude: Whether extras belong in the later render.
        output_format: Table or verbose; stored so render needs no request.
        on_progress: Optional ``(index, total, item)`` callback per item.
        unit_count: Progress total. ``0`` uses the number of mapping units.

    Returns:
        Check rows for every mapping unit, including skipped directories.
    """
    _mark_check_started(projects)
    with redirect_stdout(StringIO()):
        units = translate_config_to_mapping_units(projects)
    total = unit_count if unit_count else len(units)
    rows: list[CheckRow] = []
    unit_index = 0
    for unit in units:
        if not unit.managed_project_path.exists():
            rows.append(
                CheckRow(
                    project_name=unit.display_name,
                    target_path=unit.managed_project_path.as_posix(),
                    skip="missing_project",
                    copy=None,
                    git=None,
                )
            )
            continue
        if not unit.target_project_path.exists():
            rows.append(
                CheckRow(
                    project_name=unit.display_name,
                    target_path=unit.target_project_path.as_posix(),
                    skip="missing_target",
                    copy=None,
                    git=None,
                )
            )
            continue
        unit_index += 1
        copy = _check_copies(
            unit,
            baseline,
            on_progress=on_progress,
            unit_index=unit_index,
            unit_count=total,
        )
        git = _check_git_excludes(unit.target_project_path, {item.name for item in unit.items})
        rows.append(
            CheckRow(
                project_name=unit.display_name,
                target_path=unit.target_project_path.as_posix(),
                skip=None,
                copy=copy,
                git=git,
            )
        )
    return CheckResult(
        exit_code=0,
        extra_exclude=extra_exclude,
        output_format=output_format,
        rows=tuple(rows),
        not_found=None,
    )


def check_concat(parts: list[CheckResult]) -> CheckResult:
    """Concatenate per-worker-unit check results into one result.

    Args:
        parts: Check results in worker-unit order.

    Returns:
        One result whose rows are *parts* concatenated. Flags come from the
        first part. An empty list is an empty table result.
    """
    if not parts:
        return CheckResult(
            exit_code=0,
            extra_exclude=False,
            output_format=OutputFormat.TABLE,
            rows=(),
            not_found=None,
        )
    rows: list[CheckRow] = []
    not_found: str | None = None
    exit_code = 0
    for part in parts:
        rows.extend(part.rows)
        if part.not_found is not None:
            not_found = part.not_found
        if part.exit_code != 0:
            exit_code = part.exit_code
    return CheckResult(
        exit_code=exit_code,
        extra_exclude=parts[0].extra_exclude,
        output_format=parts[0].output_format,
        rows=tuple(rows),
        not_found=not_found,
    )


class LinkCheckFormatter:
    """Formats detailed (verbose) check results for a single row."""

    def __init__(
        self,
        link_result: LinkCheckResult,
        git_result: GitExcludeStatus | None = None,
        show_extra: bool = False,
    ) -> None:
        self.link_result = link_result
        self.git_result = git_result
        self.show_extra = show_extra

    def render(self, project_name: str, target_path: str) -> str:
        """Return the verbose block for this row, including trailing newline."""
        lines = [
            f"\nChecking {project_name} -> {target_path}",
            "=" * 60,
            *self._link_status_lines(),
            *self._copy_detail_lines(),
            *self._exclude_status_lines(),
        ]
        return "\n".join(lines) + "\n"

    def _link_status_lines(self) -> list[str]:
        has_issues = self.link_result.missing or self.link_result.incorrect
        if has_issues:
            lines = [
                "\nCopy Status:",
                f"  Exists: {len(self.link_result.exists)}",
            ]
            for item in self.link_result.exists:
                lines.append(f"    ✓ {item}")
            if self.link_result.incorrect:
                lines.append(f"  Incorrect: {len(self.link_result.incorrect)}")
                for item in self.link_result.incorrect:
                    lines.append(f"    ⚠ {item} (not a copy)")
            if self.link_result.missing:
                lines.append(f"  Missing: {len(self.link_result.missing)}")
                for item in self.link_result.missing:
                    lines.append(f"    ✗ {item}")
            return lines
        return ["\nCopy Status: ✓"]

    def _copy_detail_lines(self) -> list[str]:
        details = self.link_result.details
        lines = ["\nCopy Sync Status:"]
        for item in details.in_sync:
            lines.append(f"  ✓ {item} (in sync)")
        for item in details.mismatched:
            lines.append(f"  ⚠ {item} (mismatch)")
        for item in details.managed_changed:
            lines.append(f"  ⚠ {item} (managed changed)")
        for item in details.target_changed:
            lines.append(f"  ⚠ {item} (target changed)")
        for item in details.both_changed:
            lines.append(f"  ✗ {item} (conflict - both changed)")
        return lines

    def _exclude_status_lines(self) -> list[str]:
        if self.git_result is None:
            return ["\nTarget is not a git repository"]
        has_exclude_data = (
            self.git_result.present or self.git_result.missing or (self.show_extra and self.git_result.extra)
        )
        if not has_exclude_data:
            return ["\nTarget is not a git repository"]
        if self.git_result.missing:
            lines = [
                "\nGit Exclude Status:",
                f"  Missing entries: {len(self.git_result.missing)}",
            ]
            for item in sorted(self.git_result.missing):
                lines.append(f"    ✗ {item}")
        else:
            lines = ["\nGit Exclude Status: ✓"]
        if self.show_extra and self.git_result.extra:
            lines.append(f"  Extra entries: {len(self.git_result.extra)}")
            for item in sorted(self.git_result.extra):
                lines.append(f"    ! {item}")
        return lines


class CheckTableFormatter:
    """Formats multiple check results as a compact Rich table."""

    def __init__(self, rows: list[CheckRow], show_extra: bool = False) -> None:
        self.rows = rows
        self.show_extra = show_extra

    def render(self) -> str:
        """Return the table and optional extra-exclude section."""
        buffer = StringIO()
        console = Console(file=buffer, force_terminal=False, color_system=None, highlight=False)
        table = Table(show_header=True, header_style="bold")
        table.add_column("Project")
        table.add_column("Exclude", justify="center")
        table.add_column("Copy", justify="center")
        table.add_column("Target Path")
        for row in self.rows:
            table.add_row(
                row.project_name,
                self._exclude_cell(row.git),
                self._copy_cell(row.copy),
                row.target_path,
            )
        console.print(table)
        if self.show_extra:
            self._render_extra_entries(console)
        return buffer.getvalue()

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
        extras = [(row.project_name, sorted(row.git.extra)) for row in self.rows if row.git and row.git.extra]
        if not extras:
            return
        console.print("\nExtra exclude entries:")
        for project_name, entries in extras:
            console.print(f"  {project_name}: {', '.join(entries)}")


def _check_copies(
    unit: MappingUnit,
    baseline: BaselineTrees | None,
    *,
    on_progress: ItemProgress | None,
    unit_index: int,
    unit_count: int,
) -> LinkCheckResult:
    details = CopyCheckDetails()
    in_sync: list[str] = []
    missing: list[str] = []
    incorrect: list[str] = []
    for item in unit.items:
        if on_progress is not None:
            on_progress(unit_index, unit_count, item.name)
        target_file = unit.target_project_path / item.name
        if target_file.is_symlink():
            incorrect.append(item.name)
            continue
        if not target_file.exists():
            missing.append(item.name)
            continue
        baseline_view = (
            (baseline, unit.managed_project_path, unit.target_project_path, item.name) if baseline is not None else None
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


def _mark_check_started(projects: dict[str, ConfigProject]) -> None:
    raw = os.environ.get("BLF_TEST_CHECK_STARTED")
    if not raw:
        return
    root = Path(raw)
    root.mkdir(parents=True, exist_ok=True)
    for project in projects.values():
        (root / project.managed_project_name).write_text("1", encoding="utf-8")
