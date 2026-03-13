"""Integration tests for enhanced overwrite prompt."""

from unittest.mock import Mock

import pytest

from beyond_local_file.models import Project, ProjectItem
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
    manager = SymlinkManager(project, temp_target_dir)
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
    manager = SymlinkManager(project, temp_target_dir)
    result = manager.sync(ask_callback=mock_callback)

    # Verify the symlink was created
    assert len(result.created) == 1
    assert "file1.txt" in result.created
    assert (temp_target_dir / "file1.txt").is_symlink()
    assert (temp_target_dir / "file1.txt").resolve() == (temp_project_dir / "file1.txt").resolve()
