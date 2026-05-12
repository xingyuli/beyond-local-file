"""Unit tests for the link check operation (CheckOperation + formatters)."""

from pathlib import Path

import pytest

from beyond_local_file.model.processing import ManagedProjectItem, ProcessingUnit
from beyond_local_file.operations.link_check import CheckOperation
from beyond_local_file.options import LinkStrategy


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
def sample_unit(temp_project_dir: Path, temp_target_dir: Path) -> ProcessingUnit:
    """Create a sample processing unit with symlink items.

    Args:
        temp_project_dir: Temporary project directory fixture.
        temp_target_dir: Temporary target directory fixture.

    Returns:
        ProcessingUnit instance with test items.
    """
    items = [
        ManagedProjectItem(
            name="file1.txt",
            path=temp_project_dir / "file1.txt",
            strategy=LinkStrategy.SYMLINK,
        ),
        ManagedProjectItem(
            name="file2.txt",
            path=temp_project_dir / "file2.txt",
            strategy=LinkStrategy.SYMLINK,
        ),
    ]
    return ProcessingUnit(
        managed_project_name="test-project",
        managed_project_path=temp_project_dir,
        target_project_path=temp_target_dir,
        items=items,
        display_name="test-project",
        mapping_index=0,
        target_index=0,
    )


def test_check_operation_reports_status(
    sample_unit: ProcessingUnit,
    temp_config_dir: Path,
) -> None:
    """CheckOperation completes without error and returns True.

    Args:
        sample_unit: Sample processing unit fixture.
        temp_config_dir: Temporary config directory fixture.
    """
    # Create only one symlink so there is a mix of exists/missing
    (sample_unit.target_project_path / "file1.txt").symlink_to(
        sample_unit.managed_project_path / "file1.txt"
    )

    operation = CheckOperation(temp_config_dir)
    success = operation.execute_unit(sample_unit)

    assert success


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
    unit = ProcessingUnit(
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
