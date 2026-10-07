"""Unit tests for link check (check() rows + render adapters)."""

from pathlib import Path

import pytest

from beyond_local_file.daemon.live import scan_items
from beyond_local_file.model.config import ConfigProject, Mapping
from beyond_local_file.operations.link_check import check
from beyond_local_file.operations.result import render
from beyond_local_file.options import OutputFormat


@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory with test files."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "file1.txt").write_text("content1")
    (project_dir / "file2.txt").write_text("content2")
    return project_dir


@pytest.fixture
def temp_target_dir(tmp_path: Path) -> Path:
    """Create a temporary target directory."""
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    return target_dir


@pytest.fixture
def sample_projects(temp_project_dir: Path, temp_target_dir: Path) -> dict[str, ConfigProject]:
    """One managed project mapped to one target."""
    return {
        "test-project": ConfigProject(
            managed_project_name="test-project",
            managed_project_path=temp_project_dir,
            mappings=[Mapping(targets=[temp_target_dir], subpaths=["file1.txt", "file2.txt"])],
        )
    }


def test_link_check_reports_copy_projections_not_symlink_health(
    sample_projects: dict[str, ConfigProject],
    temp_target_dir: Path,
) -> None:
    """link check reports copy projection status, not symlink health."""
    (temp_target_dir / "file1.txt").write_text("content1")

    result = check(
        sample_projects,
        None,
        extra_exclude=False,
        output_format=OutputFormat.VERBOSE,
    )

    assert result.rows[0].copy is not None
    assert result.rows[0].copy.details.in_sync == ["file1.txt"]
    assert result.rows[0].copy.missing == ["file2.txt"]
    output = render(result)
    assert "Copy Status" in output
    assert "Copy Sync Status" in output
    assert "Symlink Status" not in output
    assert "file2.txt" in output
    assert "Processing " not in output


def test_link_check_table_reports_copy_not_symlink(
    sample_projects: dict[str, ConfigProject],
    temp_target_dir: Path,
) -> None:
    """The compact table reports copy projections, not symlink health."""
    (temp_target_dir / "file1.txt").write_text("content1")

    result = check(
        sample_projects,
        None,
        extra_exclude=False,
        output_format=OutputFormat.TABLE,
    )
    output = render(result)

    assert "Copy" in output
    assert "Symlink" not in output
    assert "Processing " not in output


def test_link_check_treats_symlink_projection_as_not_a_copy(
    sample_projects: dict[str, ConfigProject],
    temp_project_dir: Path,
    temp_target_dir: Path,
) -> None:
    """A correct blf symlink at a projection path is not reported as a healthy copy."""
    (temp_target_dir / "file1.txt").symlink_to(temp_project_dir / "file1.txt")

    result = check(
        sample_projects,
        None,
        extra_exclude=False,
        output_format=OutputFormat.VERBOSE,
    )

    assert result.rows[0].copy is not None
    assert result.rows[0].copy.incorrect == ["file1.txt"]
    output = render(result)
    assert "Symlink Status" not in output
    assert "file1.txt" in output
    assert "(in sync)" not in output
    assert "(manually synced)" not in output
    assert "not a copy" in output.lower() or "incorrect" in output.lower()


def test_live_match_is_in_sync_without_sync_state(
    sample_projects: dict[str, ConfigProject],
    temp_target_dir: Path,
    tmp_path: Path,
) -> None:
    """Matching live hashes are in-sync even when no sync-state.yml exists."""
    (temp_target_dir / "file1.txt").write_text("content1")
    (temp_target_dir / "file2.txt").write_text("content2")

    result = check(
        sample_projects,
        None,
        extra_exclude=False,
        output_format=OutputFormat.VERBOSE,
    )
    assert result.rows[0].copy is not None
    assert result.rows[0].copy.details.in_sync == ["file1.txt", "file2.txt"]
    output = render(result)

    assert "(in sync)" in output
    assert "(manually synced)" not in output
    assert not (tmp_path / "sync-state.yml").exists()


def test_live_mismatch_without_baseline_is_mismatch(
    sample_projects: dict[str, ConfigProject],
    temp_target_dir: Path,
    tmp_path: Path,
) -> None:
    """Differing live hashes with no baseline are unlabeled mismatch."""
    (temp_target_dir / "file1.txt").write_text("target-side")
    (temp_target_dir / "file2.txt").write_text("content2")

    result = check(
        sample_projects,
        None,
        extra_exclude=False,
        output_format=OutputFormat.VERBOSE,
    )
    assert result.rows[0].copy is not None
    assert result.rows[0].copy.details.mismatched == ["file1.txt"]
    assert result.rows[0].copy.details.in_sync == ["file2.txt"]
    output = render(result)

    assert "file1.txt" in output
    assert "(mismatch)" in output
    assert "(in sync)" in output
    assert "(manually synced)" not in output
    assert not (tmp_path / "sync-state.yml").exists()


def test_live_mismatch_uses_baseline_labels_not_sync_state(
    sample_projects: dict[str, ConfigProject],
    temp_project_dir: Path,
    temp_target_dir: Path,
    tmp_path: Path,
) -> None:
    """When a baseline exists, mismatch rows are labeled from those hashes."""
    (temp_target_dir / "file1.txt").write_text("content1")
    (temp_target_dir / "file2.txt").write_text("content2")
    names = ["file1.txt", "file2.txt"]
    baseline = {
        str(temp_project_dir): scan_items(temp_project_dir, names),
        str(temp_target_dir): scan_items(temp_target_dir, names),
    }
    (temp_project_dir / "file1.txt").write_text("managed-new")
    (temp_target_dir / "file2.txt").write_text("target-new")

    lying = tmp_path / "sync-state.yml"
    lying.write_text("synced_files: []\n", encoding="utf-8")
    before = lying.read_text(encoding="utf-8")

    result = check(
        sample_projects,
        baseline,
        extra_exclude=False,
        output_format=OutputFormat.VERBOSE,
    )
    assert result.rows[0].copy is not None
    assert result.rows[0].copy.details.managed_changed == ["file1.txt"]
    assert result.rows[0].copy.details.target_changed == ["file2.txt"]
    output = render(result)

    assert "(managed changed)" in output
    assert "(target changed)" in output
    assert "(mismatch)" not in output
    assert "(manually synced)" not in output
    assert lying.read_text(encoding="utf-8") == before


def test_live_mismatch_both_changed_from_baseline(
    sample_projects: dict[str, ConfigProject],
    temp_project_dir: Path,
    temp_target_dir: Path,
) -> None:
    """When both sides differ from baseline, the mismatch is both-changed."""
    (temp_target_dir / "file1.txt").write_text("content1")
    (temp_target_dir / "file2.txt").write_text("content2")
    names = ["file1.txt", "file2.txt"]
    baseline = {
        str(temp_project_dir): scan_items(temp_project_dir, names),
        str(temp_target_dir): scan_items(temp_target_dir, names),
    }
    (temp_project_dir / "file1.txt").write_text("managed-new")
    (temp_target_dir / "file1.txt").write_text("target-new")

    result = check(
        sample_projects,
        baseline,
        extra_exclude=False,
        output_format=OutputFormat.VERBOSE,
    )
    assert result.rows[0].copy is not None
    assert result.rows[0].copy.details.both_changed == ["file1.txt"]
    output = render(result)

    assert "file1.txt" in output
    assert "(conflict - both changed)" in output
    assert "(mismatch)" not in output


def test_live_match_ignores_stale_baseline_and_sync_state(
    sample_projects: dict[str, ConfigProject],
    temp_project_dir: Path,
    temp_target_dir: Path,
) -> None:
    """Live match is in-sync even when baseline hashes are stale."""
    names = ["file1.txt", "file2.txt"]
    baseline = {
        str(temp_project_dir): scan_items(temp_project_dir, names),
        str(temp_target_dir): scan_items(temp_target_dir, names),
    }
    (temp_project_dir / "file1.txt").write_text("both-new")
    (temp_target_dir / "file1.txt").write_text("both-new")
    (temp_target_dir / "file2.txt").write_text("content2")

    result = check(
        sample_projects,
        baseline,
        extra_exclude=False,
        output_format=OutputFormat.VERBOSE,
    )
    assert result.rows[0].copy is not None
    assert result.rows[0].copy.details.in_sync == ["file1.txt", "file2.txt"]
    output = render(result)

    assert "file1.txt" in output
    assert "(in sync)" in output
    assert "(both changed)" not in output
    assert "(manually synced)" not in output


def test_check_table_has_no_progress_fraction(
    sample_projects: dict[str, ConfigProject],
    temp_target_dir: Path,
) -> None:
    """The compact table does not show k/n progress in cells."""
    (temp_target_dir / "file1.txt").write_text("content1")
    (temp_target_dir / "file2.txt").write_text("content2")

    result = check(
        sample_projects,
        None,
        extra_exclude=False,
        output_format=OutputFormat.TABLE,
    )
    output = render(result)

    assert "Copy" in output
    assert "k/n" not in output
    assert "Checking " not in output


def test_check_git_exclude_covers_every_item(tmp_path: Path) -> None:
    """Git exclude entries for every projected item are not extra."""
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    info_dir = target_dir / ".git" / "info"
    info_dir.mkdir(parents=True)

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "symlink_file.txt").write_text("symlink content")
    (project_dir / "copy_file.txt").write_text("copy content")
    (info_dir / "exclude").write_text("symlink_file.txt\ncopy_file.txt\n")

    projects = {
        "mixed-project": ConfigProject(
            managed_project_name="mixed-project",
            managed_project_path=project_dir,
            mappings=[Mapping(targets=[target_dir], subpaths=None)],
        )
    }
    result = check(projects, None, extra_exclude=False, output_format=OutputFormat.TABLE)

    assert result.rows[0].git is not None
    assert result.rows[0].git.present == {"symlink_file.txt", "copy_file.txt"}
    assert not result.rows[0].git.missing
    assert not result.rows[0].git.extra
    render(result)


def test_check_skips_missing_target(tmp_path: Path) -> None:
    """A missing target directory is a skip row with today's message."""
    managed = tmp_path / "lab-app"
    managed.mkdir()
    (managed / "example.txt").write_text("x")
    target = tmp_path / "alpha"
    projects = {
        "lab-app": ConfigProject(
            managed_project_name="lab-app",
            managed_project_path=managed,
            mappings=[Mapping(targets=[target], subpaths=None)],
        )
    }
    result = check(projects, None, extra_exclude=False, output_format=OutputFormat.TABLE)
    assert len(result.rows) == 1
    assert result.rows[0].skip == "missing_target"
    assert result.rows[0].copy is None
    assert f"Target directory does not exist: {target.as_posix()}" in render(result)


def test_check_emits_progress_for_verbose_and_table(
    sample_projects: dict[str, ConfigProject],
    temp_target_dir: Path,
) -> None:
    """Progress is format-blind: every item is reported when on_progress is set."""
    (temp_target_dir / "file1.txt").write_text("content1")
    (temp_target_dir / "file2.txt").write_text("content2")
    seen: list[tuple[int, int, str]] = []
    check(
        sample_projects,
        None,
        extra_exclude=False,
        output_format=OutputFormat.VERBOSE,
        on_progress=lambda index, total, item: seen.append((index, total, item)),
        unit_count=1,
    )
    assert seen == [(1, 1, "file1.txt"), (1, 1, "file2.txt")]


def test_check_skips_empty_sync_all(tmp_path: Path) -> None:
    """An empty sync-all hub produces no check row."""
    hub = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    hub.mkdir()
    alpha.mkdir()
    projects = {
        "lab-app": ConfigProject(
            managed_project_name="lab-app",
            managed_project_path=hub,
            mappings=[Mapping(targets=[alpha], subpaths=None)],
        )
    }

    result = check(projects, None, extra_exclude=False, output_format=OutputFormat.TABLE)

    assert result.rows == ()


def test_check_missing_hub_with_present_replica_is_mismatch(tmp_path: Path) -> None:
    """A declared name whose hub file is missing and whose replica exists is a mismatch."""
    hub = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    hub.mkdir()
    alpha.mkdir()
    (alpha / "notes.md").write_text("draft")
    projects = {
        "lab-app": ConfigProject(
            managed_project_name="lab-app",
            managed_project_path=hub,
            mappings=[Mapping(targets=[alpha], subpaths=["notes.md"])],
        )
    }

    result = check(projects, None, extra_exclude=False, output_format=OutputFormat.VERBOSE)

    assert result.rows[0].copy is not None
    assert result.rows[0].copy.details.mismatched == ["notes.md"]
