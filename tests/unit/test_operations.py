"""Unit tests for operation coordination logic.

These tests document the current behavior of SyncOperation and CheckOperation
before refactoring, providing a safety net to catch regressions during the
manager responsibilities refactoring task.
"""

from pathlib import Path

import pytest

from beyond_local_file.models import Project, ProjectItem
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
def sample_project(temp_project_dir: Path) -> Project:
    """Create a sample project with symlink items.

    Args:
        temp_project_dir: Temporary project directory fixture.

    Returns:
        Project instance with test items.
    """
    items = [
        ProjectItem(
            name="file1.txt",
            is_directory=False,
            source_path=temp_project_dir / "file1.txt",
            strategy=LinkStrategy.SYMLINK,
        ),
        ProjectItem(
            name="file2.txt",
            is_directory=False,
            source_path=temp_project_dir / "file2.txt",
            strategy=LinkStrategy.SYMLINK,
        ),
    ]
    return Project(name="test-project", directory=temp_project_dir, items=items)


# Test Suite: SyncOperation Behavior


def test_sync_operation_creates_symlinks_for_project(
    sample_project: Project,
    temp_target_dir: Path,
    temp_config_dir: Path,
) -> None:
    """Test that SyncOperation creates symlinks for all project items.

    Args:
        sample_project: Sample project fixture.
        temp_target_dir: Temporary target directory fixture.
        temp_config_dir: Temporary config directory fixture.
    """
    operation = SyncOperation(temp_config_dir)
    success = operation.execute(sample_project, temp_target_dir)

    # Operation should succeed
    assert success

    # Verify symlinks were created
    assert (temp_target_dir / "file1.txt").is_symlink()
    assert (temp_target_dir / "file2.txt").is_symlink()


def test_sync_operation_handles_git_exclude(
    sample_project: Project,
    tmp_path: Path,
    temp_config_dir: Path,
) -> None:
    """Test that SyncOperation adds git exclude entries for synced items.

    Args:
        sample_project: Sample project fixture.
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

    operation = SyncOperation(temp_config_dir)
    success = operation.execute(sample_project, target_dir)

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
    sample_project: Project,
    temp_target_dir: Path,
    temp_config_dir: Path,
) -> None:
    """Test that CheckOperation reports symlink status correctly.

    Args:
        sample_project: Sample project fixture.
        temp_target_dir: Temporary target directory fixture.
        temp_config_dir: Temporary config directory fixture.
    """
    # Create only one symlink (file1.txt)
    (temp_target_dir / "file1.txt").symlink_to(sample_project.directory / "file1.txt")

    operation = CheckOperation(temp_config_dir)
    success = operation.execute(sample_project, temp_target_dir)

    # Operation should succeed
    assert success

    # Note: CheckOperation stores results in _rows for table rendering
    # We verify it doesn't crash and returns True
    # The actual status checking is verified in test_symlink_manager.py


def test_check_operation_uses_all_item_names(
    tmp_path: Path,
    temp_config_dir: Path,
) -> None:
    """Test that CheckOperation passes all_item_names to SymlinkManager.check().

    This tests the current hack where CheckOperation gets all project item names
    (both symlink and copy) and passes them to SymlinkManager.check() to prevent
    copy items from being reported as "extra" git exclude entries.

    NOTE: This test documents the hack that will be removed during refactoring.

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
        ProjectItem(
            name="symlink_file.txt",
            is_directory=False,
            source_path=project_dir / "symlink_file.txt",
            strategy=LinkStrategy.SYMLINK,
        ),
        ProjectItem(
            name="copy_file.txt",
            is_directory=False,
            source_path=project_dir / "copy_file.txt",
            strategy=LinkStrategy.COPY,
        ),
    ]
    project = Project(name="mixed-project", directory=project_dir, items=items)

    # Create git exclude entries for both items
    exclude_file = info_dir / "exclude"
    exclude_file.write_text("symlink_file.txt\ncopy_file.txt\n")

    # Run check operation
    operation = CheckOperation(temp_config_dir)
    success = operation.execute(project, target_dir)

    # Operation should succeed
    assert success

    # The key behavior: CheckOperation gets all_item_names and passes to SymlinkManager.check()
    # This prevents copy_file.txt from being reported as "extra"
    # We verify this indirectly by checking that the operation completes without errors
    # The actual behavior is tested in test_symlink_manager.py::test_check_with_all_item_names_excludes_copy_items
