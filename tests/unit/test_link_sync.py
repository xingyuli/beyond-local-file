"""Unit tests for the link sync operation (SyncOperation + LinkSyncFormatter)."""

from pathlib import Path

import pytest

from beyond_local_file.model.processing import ManagedProjectItem, ProcessingUnit
from beyond_local_file.operations.link_sync import SyncOperation
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


def test_sync_operation_creates_symlinks(
    sample_unit: ProcessingUnit,
    temp_config_dir: Path,
) -> None:
    """SyncOperation creates symlinks for all project items.

    Args:
        sample_unit: Sample processing unit fixture.
        temp_config_dir: Temporary config directory fixture.
    """
    operation = SyncOperation(temp_config_dir)
    success = operation.execute_unit(sample_unit)

    assert success
    assert (sample_unit.target_project_path / "file1.txt").is_symlink()
    assert (sample_unit.target_project_path / "file2.txt").is_symlink()


def test_sync_operation_adds_git_excludes(
    temp_project_dir: Path,
    tmp_path: Path,
    temp_config_dir: Path,
) -> None:
    """SyncOperation writes git exclude entries when target is a git repo.

    Args:
        temp_project_dir: Temporary project directory fixture.
        tmp_path: Pytest temporary directory fixture.
        temp_config_dir: Temporary config directory fixture.
    """
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    info_dir = target_dir / ".git" / "info"
    info_dir.mkdir(parents=True)

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

    assert success
    exclude_content = (info_dir / "exclude").read_text()
    assert "file1.txt" in exclude_content
    assert "file2.txt" in exclude_content
