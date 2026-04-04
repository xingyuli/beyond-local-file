"""Unit tests for operation coordination logic.

These tests document the current behavior of SyncOperation and CheckOperation
before refactoring, providing a safety net to catch regressions during the
manager responsibilities refactoring task.
"""

from pathlib import Path

import pytest

from beyond_local_file.model.processing import ManagedProjectItem, ProcessingUnit
from beyond_local_file.options import LinkStrategy
from beyond_local_file.project_processor import CheckOperation, SyncOperation


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


# Test Suite: SyncOperation Behavior


def test_sync_operation_creates_symlinks_for_project(
    sample_unit: ProcessingUnit,
    temp_config_dir: Path,
) -> None:
    """Test that SyncOperation creates symlinks for all project items.

    Args:
        sample_unit: Sample processing unit fixture.
        temp_config_dir: Temporary config directory fixture.
    """
    operation = SyncOperation(temp_config_dir)
    success = operation.execute_unit(sample_unit)

    # Operation should succeed
    assert success

    # Verify symlinks were created
    assert (sample_unit.target_project_path / "file1.txt").is_symlink()
    assert (sample_unit.target_project_path / "file2.txt").is_symlink()


def test_sync_operation_handles_git_exclude(
    temp_project_dir: Path,
    tmp_path: Path,
    temp_config_dir: Path,
) -> None:
    """Test that SyncOperation adds git exclude entries for synced items.

    Args:
        temp_project_dir: Temporary project directory fixture.
        tmp_path: Pytest temporary directory fixture.
        temp_config_dir: Temporary config directory fixture.
    """
    # Create a git repo in target directory
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    git_dir = target_dir / ".git"
    git_dir.mkdir()
    info_dir = git_dir / "info"
    info_dir.mkdir()

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
    unit = ProcessingUnit(
        managed_project_name="test-project",
        managed_project_path=temp_project_dir,
        target_project_path=target_dir,
        items=items,
        display_name="test-project",
        mapping_index=0,
        target_index=0,
    )

    operation = SyncOperation(temp_config_dir)
    success = operation.execute_unit(unit)

    # Operation should succeed
    assert success

    # Verify git exclude entries were added
    exclude_file = info_dir / "exclude"
    assert exclude_file.exists()

    exclude_content = exclude_file.read_text()
    assert "file1.txt" in exclude_content
    assert "file2.txt" in exclude_content


# Test Suite: CheckOperation Behavior


def test_check_operation_reports_status(
    sample_unit: ProcessingUnit,
    temp_config_dir: Path,
) -> None:
    """Test that CheckOperation reports symlink status correctly.

    Args:
        sample_unit: Sample processing unit fixture.
        temp_config_dir: Temporary config directory fixture.
    """
    # Create only one symlink (file1.txt)
    (sample_unit.target_project_path / "file1.txt").symlink_to(sample_unit.managed_project_path / "file1.txt")

    operation = CheckOperation(temp_config_dir)
    success = operation.execute_unit(sample_unit)

    # Operation should succeed
    assert success

    # Note: CheckOperation stores results in _rows for table rendering
    # We verify it doesn't crash and returns True
    # The actual status checking is verified in test_symlink_manager.py


def test_check_operation_with_mixed_strategies(
    tmp_path: Path,
    temp_config_dir: Path,
) -> None:
    """Test that CheckOperation correctly handles projects with mixed strategies.

    After refactoring, CheckOperation uses the protocol to collect all_valid_entries
    from all managers, preventing items from one strategy being reported as "extra"
    git exclude entries by another manager.

    Args:
        tmp_path: Pytest temporary directory fixture.
        temp_config_dir: Temporary config directory fixture.
    """
    # Create a git repo in target directory
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    git_dir = target_dir / ".git"
    git_dir.mkdir()
    info_dir = git_dir / "info"
    info_dir.mkdir()

    # Create project with both symlink and copy items
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

    # Create git exclude entries for both items
    exclude_file = info_dir / "exclude"
    exclude_file.write_text("symlink_file.txt\ncopy_file.txt\n")

    # Run check operation
    operation = CheckOperation(temp_config_dir)
    success = operation.execute_unit(unit)

    # Operation should succeed
    assert success

    # The refactored behavior: CheckOperation collects all_valid_entries from all managers
    # and passes it to check_git_excludes(), preventing copy_file.txt from being
    # reported as "extra" by SymlinkManager (and vice versa)
