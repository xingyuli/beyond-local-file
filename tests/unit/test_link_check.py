"""Unit tests for the link check operation (CheckOperation + formatters)."""

from pathlib import Path

import pytest

from beyond_local_file.daemon.catchup import scan_items
from beyond_local_file.model.processing import LinkStrategy, ManagedProjectItem, MappingUnit
from beyond_local_file.operations.link_check import CheckOperation
from beyond_local_file.options import OutputFormat


@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory with test files.

    Args:
        tmp_path: Pytest temporary directory fixture.

    Returns:
        Path to the project directory.
    """
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "file1.txt").write_text("content1")
    (project_dir / "file2.txt").write_text("content2")
    return project_dir


@pytest.fixture
def temp_target_dir(tmp_path: Path) -> Path:
    """Create a temporary target directory.

    Args:
        tmp_path: Pytest temporary directory fixture.

    Returns:
        Path to the target directory.
    """
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    return target_dir


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory.

    Args:
        tmp_path: Pytest temporary directory fixture.

    Returns:
        Path to the config directory.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def sample_unit(temp_project_dir: Path, temp_target_dir: Path) -> MappingUnit:
    """Create a sample mapping unit with copy items.

    Args:
        temp_project_dir: Temporary project directory fixture.
        temp_target_dir: Temporary target directory fixture.

    Returns:
        MappingUnit instance with test items.
    """
    items = [
        ManagedProjectItem(
            name="file1.txt",
            path=temp_project_dir / "file1.txt",
            strategy=LinkStrategy.COPY,
        ),
        ManagedProjectItem(
            name="file2.txt",
            path=temp_project_dir / "file2.txt",
            strategy=LinkStrategy.COPY,
        ),
    ]
    return MappingUnit(
        managed_project_name="test-project",
        managed_project_path=temp_project_dir,
        target_project_path=temp_target_dir,
        items=items,
        display_name="test-project",
        mapping_index=0,
        target_index=0,
    )


def test_link_check_reports_copy_projections_not_symlink_health(
    sample_unit: MappingUnit,
    temp_config_dir: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """link check reports copy projection status, not symlink health."""
    (sample_unit.target_project_path / "file1.txt").write_text("content1")

    operation = CheckOperation(temp_config_dir, output_format=OutputFormat.VERBOSE)
    success = operation.execute_unit(sample_unit)

    assert success
    output = capsys.readouterr().out
    assert "Copy Status" in output
    assert "Copy Sync Status" in output
    assert "Symlink Status" not in output
    assert "file2.txt" in output


def test_link_check_table_reports_copy_not_symlink(
    sample_unit: MappingUnit,
    temp_config_dir: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """The compact table reports copy projections, not symlink health."""
    (sample_unit.target_project_path / "file1.txt").write_text("content1")

    operation = CheckOperation(temp_config_dir)
    success = operation.execute_unit(sample_unit)
    operation.render()

    assert success
    output = capsys.readouterr().out
    assert "Copy" in output
    assert "Symlink" not in output


def test_link_check_treats_symlink_projection_as_not_a_copy(
    sample_unit: MappingUnit,
    temp_config_dir: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """A correct blf symlink at a projection path is not reported as a healthy copy."""
    (sample_unit.target_project_path / "file1.txt").symlink_to(sample_unit.managed_project_path / "file1.txt")

    operation = CheckOperation(temp_config_dir, output_format=OutputFormat.VERBOSE)
    success = operation.execute_unit(sample_unit)

    assert success
    output = capsys.readouterr().out
    assert "Symlink Status" not in output
    assert "file1.txt" in output
    assert "(in sync)" not in output
    assert "(manually synced)" not in output
    assert "not a copy" in output.lower() or "incorrect" in output.lower()


def test_live_match_is_in_sync_without_sync_state(
    sample_unit: MappingUnit,
    temp_config_dir: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """Matching live hashes are in-sync even when no sync-state.yml exists."""
    target = sample_unit.target_project_path
    (target / "file1.txt").write_text("content1")
    (target / "file2.txt").write_text("content2")

    operation = CheckOperation(temp_config_dir, output_format=OutputFormat.VERBOSE)
    assert operation.execute_unit(sample_unit)
    output = capsys.readouterr().out

    assert "(in sync)" in output
    assert "(manually synced)" not in output
    assert not (temp_config_dir / "sync-state.yml").exists()


def test_live_mismatch_without_baseline_is_mismatch(
    sample_unit: MappingUnit,
    temp_config_dir: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """Differing live hashes with no baseline are unlabeled mismatch."""
    target = sample_unit.target_project_path
    (target / "file1.txt").write_text("target-side")
    (target / "file2.txt").write_text("content2")

    operation = CheckOperation(temp_config_dir, output_format=OutputFormat.VERBOSE)
    assert operation.execute_unit(sample_unit)
    output = capsys.readouterr().out

    assert "file1.txt" in output
    assert "(mismatch)" in output
    assert "(in sync)" in output
    assert "(manually synced)" not in output
    assert not (temp_config_dir / "sync-state.yml").exists()


def test_live_mismatch_uses_baseline_labels_not_sync_state(
    sample_unit: MappingUnit,
    temp_config_dir: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """When a baseline exists, mismatch rows are labeled from those hashes."""
    managed = sample_unit.managed_project_path
    target = sample_unit.target_project_path
    (target / "file1.txt").write_text("content1")
    (target / "file2.txt").write_text("content2")
    names = ["file1.txt", "file2.txt"]
    baseline = {
        str(managed): scan_items(managed, names),
        str(target): scan_items(target, names),
    }
    (managed / "file1.txt").write_text("managed-new")
    (target / "file2.txt").write_text("target-new")

    lying = temp_config_dir / "sync-state.yml"
    lying.write_text("synced_files: []\n", encoding="utf-8")
    before = lying.read_text(encoding="utf-8")

    operation = CheckOperation(temp_config_dir, output_format=OutputFormat.VERBOSE)
    operation.baseline = baseline
    assert operation.execute_unit(sample_unit)
    output = capsys.readouterr().out

    assert "(managed changed)" in output
    assert "(target changed)" in output
    assert "(mismatch)" not in output
    assert "(manually synced)" not in output
    assert lying.read_text(encoding="utf-8") == before


def test_live_mismatch_both_changed_from_baseline(
    sample_unit: MappingUnit,
    temp_config_dir: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """When both sides differ from baseline, the mismatch is both-changed."""
    managed = sample_unit.managed_project_path
    target = sample_unit.target_project_path
    (target / "file1.txt").write_text("content1")
    (target / "file2.txt").write_text("content2")
    names = ["file1.txt", "file2.txt"]
    baseline = {
        str(managed): scan_items(managed, names),
        str(target): scan_items(target, names),
    }
    (managed / "file1.txt").write_text("managed-new")
    (target / "file1.txt").write_text("target-new")

    operation = CheckOperation(temp_config_dir, output_format=OutputFormat.VERBOSE)
    operation.baseline = baseline
    assert operation.execute_unit(sample_unit)
    output = capsys.readouterr().out

    assert "file1.txt" in output
    assert "(conflict - both changed)" in output
    assert "(mismatch)" not in output


def test_live_match_ignores_stale_baseline_and_sync_state(
    sample_unit: MappingUnit,
    temp_config_dir: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """Live match is in-sync even when baseline hashes are stale."""
    managed = sample_unit.managed_project_path
    target = sample_unit.target_project_path
    names = ["file1.txt", "file2.txt"]
    baseline = {
        str(managed): scan_items(managed, names),
        str(target): scan_items(target, names),
    }
    (managed / "file1.txt").write_text("both-new")
    (target / "file1.txt").write_text("both-new")
    (target / "file2.txt").write_text("content2")

    operation = CheckOperation(temp_config_dir, output_format=OutputFormat.VERBOSE)
    operation.baseline = baseline
    assert operation.execute_unit(sample_unit)
    output = capsys.readouterr().out

    assert "file1.txt" in output
    assert "(in sync)" in output
    assert "(both changed)" not in output
    assert "(manually synced)" not in output


def test_check_table_has_no_progress_fraction(
    sample_unit: MappingUnit,
    temp_config_dir: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """The compact table does not show k/n progress in cells."""
    (sample_unit.target_project_path / "file1.txt").write_text("content1")
    (sample_unit.target_project_path / "file2.txt").write_text("content2")

    operation = CheckOperation(temp_config_dir)
    assert operation.execute_unit(sample_unit)
    operation.render()
    output = capsys.readouterr().out

    assert "Copy" in output
    assert "k/n" not in output
    assert "Checking " not in output


def test_check_operation_mixed_strategies_no_false_extra(
    tmp_path: Path,
    temp_config_dir: Path,
) -> None:
    """CheckOperation passes all_valid_entries across strategies.

    When a project has both symlink and copy items, git exclude entries for
    copy items must not be reported as "extra" by the symlink manager (and
    vice versa). This test verifies that the aggregated all_valid_entries set
    prevents false positives.

    Args:
        tmp_path: Pytest temporary directory fixture.
        temp_config_dir: Temporary config directory fixture.
    """
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    info_dir = target_dir / ".git" / "info"
    info_dir.mkdir(parents=True)

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "symlink_file.txt").write_text("symlink content")
    (project_dir / "copy_file.txt").write_text("copy content")

    items = [
        ManagedProjectItem(
            name="symlink_file.txt",
            path=project_dir / "symlink_file.txt",
            strategy=LinkStrategy.SYMLINK,
        ),
        ManagedProjectItem(
            name="copy_file.txt",
            path=project_dir / "copy_file.txt",
            strategy=LinkStrategy.COPY,
        ),
    ]
    unit = MappingUnit(
        managed_project_name="mixed-project",
        managed_project_path=project_dir,
        target_project_path=target_dir,
        items=items,
        display_name="mixed-project",
        mapping_index=0,
        target_index=0,
    )

    # Pre-populate git exclude with entries for both strategies
    (info_dir / "exclude").write_text("symlink_file.txt\ncopy_file.txt\n")

    operation = CheckOperation(temp_config_dir)
    success = operation.execute_unit(unit)

    assert success

    # After render(), the table should have been built without errors
    operation.render()
