"""Integration tests for enhanced overwrite prompt."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from beyond_local_file.models import Project, ProjectItem
from beyond_local_file.options import LinkStrategy
from beyond_local_file.project_processor import CheckOperation, SyncOperation
from beyond_local_file.symlink_manager import Action, SymlinkManager


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory with test files."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "file1.txt").write_text("content1")
    (project_dir / "file2.txt").write_text("content2")
    return project_dir


@pytest.fixture
def temp_target_dir(tmp_path):
    """Create a temporary target directory."""
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    return target_dir


def test_callback_receives_both_paths(temp_project_dir, temp_target_dir):
    """Test that the callback receives both target path and expected source."""
    # Create a project
    items = [
        ProjectItem(name="file1.txt", is_directory=False, source_path=temp_project_dir / "file1.txt"),
    ]
    project = Project(name="test-project", directory=temp_project_dir, items=items)

    # Create an existing file at target
    existing_file = temp_target_dir / "file1.txt"
    existing_file.write_text("existing content")

    # Create a mock callback to capture arguments
    mock_callback = Mock(return_value=Action.SKIP)

    # Run sync
    manager = SymlinkManager(project.items, temp_target_dir)
    result = manager.sync(ask_callback=mock_callback)

    # Verify callback was called with both arguments
    assert mock_callback.call_count == 1
    call_args = mock_callback.call_args[0]
    expected_arg_count = 2  # target_path and expected_source
    assert len(call_args) == expected_arg_count
    assert call_args[0] == str(temp_target_dir / "file1.txt")
    assert call_args[1] == str(temp_project_dir / "file1.txt")
    assert len(result.skipped) == 1


def test_callback_with_overwrite_action(temp_project_dir, temp_target_dir):
    """Test that overwrite action works correctly."""
    # Create a project
    items = [
        ProjectItem(name="file1.txt", is_directory=False, source_path=temp_project_dir / "file1.txt"),
    ]
    project = Project(name="test-project", directory=temp_project_dir, items=items)

    # Create an existing file at target
    existing_file = temp_target_dir / "file1.txt"
    existing_file.write_text("existing content")

    # Create a callback that returns OVERWRITE
    mock_callback = Mock(return_value=Action.OVERWRITE)

    # Run sync
    manager = SymlinkManager(project.items, temp_target_dir)
    result = manager.sync(ask_callback=mock_callback)

    # Verify the symlink was created
    assert len(result.created) == 1
    assert "file1.txt" in result.created
    assert (temp_target_dir / "file1.txt").is_symlink()
    assert (temp_target_dir / "file1.txt").resolve() == (temp_project_dir / "file1.txt").resolve()


# Test Suite: Multi-Strategy Integration


def test_sync_with_mixed_strategies(tmp_path: Path) -> None:
    """Test sync operation with both symlink and copy items.

    This test verifies that the refactored architecture correctly handles
    projects with mixed strategies using the divide-and-conquer approach.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    # Create project directory with files
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "symlink1.txt").write_text("symlink content 1")
    (project_dir / "symlink2.txt").write_text("symlink content 2")
    (project_dir / "copy1.txt").write_text("copy content 1")
    (project_dir / "copy2.txt").write_text("copy content 2")

    # Create target directory
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    # Create config directory
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create project with mixed strategies
    items = [
        ProjectItem(
            name="symlink1.txt",
            is_directory=False,
            source_path=project_dir / "symlink1.txt",
            strategy=LinkStrategy.SYMLINK,
        ),
        ProjectItem(
            name="symlink2.txt",
            is_directory=False,
            source_path=project_dir / "symlink2.txt",
            strategy=LinkStrategy.SYMLINK,
        ),
        ProjectItem(
            name="copy1.txt",
            is_directory=False,
            source_path=project_dir / "copy1.txt",
            strategy=LinkStrategy.COPY,
        ),
        ProjectItem(
            name="copy2.txt",
            is_directory=False,
            source_path=project_dir / "copy2.txt",
            strategy=LinkStrategy.COPY,
        ),
    ]
    project = Project(name="mixed-project", directory=project_dir, items=items)

    # Run sync operation (uses current architecture)
    operation = SyncOperation(config_dir)
    success = operation.execute(project, target_dir)

    # Verify operation succeeded
    assert success

    # Verify symlinks were created
    assert (target_dir / "symlink1.txt").is_symlink()
    assert (target_dir / "symlink2.txt").is_symlink()
    assert (target_dir / "symlink1.txt").resolve() == (project_dir / "symlink1.txt").resolve()
    assert (target_dir / "symlink2.txt").resolve() == (project_dir / "symlink2.txt").resolve()

    # Verify copies were created
    assert (target_dir / "copy1.txt").exists()
    assert (target_dir / "copy2.txt").exists()
    assert not (target_dir / "copy1.txt").is_symlink()
    assert not (target_dir / "copy2.txt").is_symlink()
    assert (target_dir / "copy1.txt").read_text() == "copy content 1"
    assert (target_dir / "copy2.txt").read_text() == "copy content 2"


def test_check_git_exclude_with_mixed_strategies(tmp_path: Path) -> None:
    """Test git exclude entries with mixed strategies.

    This test verifies that the refactored architecture correctly handles
    git exclude entries for projects with mixed strategies. The protocol-based
    approach collects all_valid_entries from all managers to prevent false
    positives when checking for extra entries.

    Args:
        tmp_path: Pytest temporary directory fixture.
    """
    # Create a git repo in target directory
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    git_dir = target_dir / ".git"
    git_dir.mkdir()
    info_dir = git_dir / "info"
    info_dir.mkdir()

    # Create project directory with files
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "symlink_file.txt").write_text("symlink content")
    (project_dir / "copy_file.txt").write_text("copy content")

    # Create config directory
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create project with mixed strategies
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

    # Sync first to create items and git exclude entries
    sync_op = SyncOperation(config_dir)
    sync_op.execute(project, target_dir)

    # Verify git exclude file has entries for both strategies
    exclude_file = info_dir / "exclude"
    assert exclude_file.exists()
    exclude_content = exclude_file.read_text()
    assert "symlink_file.txt" in exclude_content
    assert "copy_file.txt" in exclude_content

    # Run check operation (uses current architecture with all_item_names hack)
    check_op = CheckOperation(config_dir)
    success = check_op.execute(project, target_dir)

    # Verify operation succeeded
    assert success

    # The refactored behavior: CheckOperation collects all_valid_entries from all managers
    # and passes it to check_git_excludes(), preventing copy_file.txt from being
    # reported as "extra" by SymlinkManager (and vice versa)
