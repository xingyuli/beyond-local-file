"""Unit tests for the link sync operation (SyncOperation + LinkSyncFormatter)."""

from pathlib import Path

import pytest

from beyond_local_file.model.processing import LinkStrategy, ManagedProjectItem, MappingUnit
from beyond_local_file.operations.link_sync import SyncOperation


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


def test_link_sync_projects_file_item_as_regular_file_copy(
    sample_unit: MappingUnit,
    temp_config_dir: Path,
) -> None:
    """A file item is projected as a regular file copy, not a symlink."""
    operation = SyncOperation(temp_config_dir)
    success = operation.execute_unit(sample_unit)

    assert success
    file1 = sample_unit.target_project_path / "file1.txt"
    file2 = sample_unit.target_project_path / "file2.txt"
    assert file1.is_file()
    assert file2.is_file()
    assert not file1.is_symlink()
    assert not file2.is_symlink()
    assert file1.read_text() == "content1"
    assert file2.read_text() == "content2"


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
            strategy=LinkStrategy.COPY,
        ),
        ManagedProjectItem(
            name="file2.txt",
            path=temp_project_dir / "file2.txt",
            strategy=LinkStrategy.COPY,
        ),
    ]
    unit = MappingUnit(
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


def test_link_sync_projects_directory_item_as_real_directory_tree(
    tmp_path: Path,
    temp_config_dir: Path,
) -> None:
    """A directory item is projected as a real directory tree, not a symlink."""
    managed = tmp_path / "managed"
    hooks = managed / ".kiro" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "hook.json").write_text('{"name": "hook"}')
    (hooks / "nested").mkdir()
    (hooks / "nested" / "inner.txt").write_text("inner")

    target = tmp_path / "target"
    target.mkdir()

    unit = MappingUnit(
        managed_project_name="managed",
        managed_project_path=managed,
        target_project_path=target,
        items=[
            ManagedProjectItem(
                name=".kiro/hooks",
                path=hooks,
                strategy=LinkStrategy.COPY,
            ),
        ],
        display_name="managed",
        mapping_index=0,
        target_index=0,
    )

    success = SyncOperation(temp_config_dir).execute_unit(unit)

    assert success
    projected = target / ".kiro" / "hooks"
    assert projected.is_dir()
    assert not projected.is_symlink()
    assert (projected / "hook.json").is_file()
    assert not (projected / "hook.json").is_symlink()
    assert (projected / "hook.json").read_text() == '{"name": "hook"}'
    assert (projected / "nested" / "inner.txt").read_text() == "inner"


def test_link_sync_converts_correct_blf_symlink_projection_to_copy(
    tmp_path: Path,
    temp_config_dir: Path,
) -> None:
    """A projection path that is a symlink to the managed item becomes a copy."""
    managed = tmp_path / "managed"
    managed.mkdir()
    item = managed / "file1.txt"
    item.write_text("content1")

    target = tmp_path / "target"
    target.mkdir()
    projection = target / "file1.txt"
    projection.symlink_to(item)

    unit = MappingUnit(
        managed_project_name="managed",
        managed_project_path=managed,
        target_project_path=target,
        items=[
            ManagedProjectItem(
                name="file1.txt",
                path=item,
                strategy=LinkStrategy.COPY,
            ),
        ],
        display_name="managed",
        mapping_index=0,
        target_index=0,
    )

    success = SyncOperation(temp_config_dir).execute_unit(unit)

    assert success
    assert projection.is_file()
    assert not projection.is_symlink()
    assert projection.read_text() == "content1"
    assert item.read_text() == "content1"


def test_link_sync_converts_correct_directory_symlink_projection_to_copy(
    tmp_path: Path,
    temp_config_dir: Path,
) -> None:
    """A directory symlink at a projection path is converted to a real tree."""
    managed = tmp_path / "managed"
    hooks = managed / ".kiro" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "hook.json").write_text("{}")

    target = tmp_path / "target"
    (target / ".kiro").mkdir(parents=True)
    projection = target / ".kiro" / "hooks"
    projection.symlink_to(hooks)

    unit = MappingUnit(
        managed_project_name="managed",
        managed_project_path=managed,
        target_project_path=target,
        items=[
            ManagedProjectItem(
                name=".kiro/hooks",
                path=hooks,
                strategy=LinkStrategy.COPY,
            ),
        ],
        display_name="managed",
        mapping_index=0,
        target_index=0,
    )

    success = SyncOperation(temp_config_dir).execute_unit(unit)

    assert success
    assert projection.is_dir()
    assert not projection.is_symlink()
    assert (projection / "hook.json").is_file()
    assert not (projection / "hook.json").is_symlink()
    assert (projection / "hook.json").read_text() == "{}"
    assert (hooks / "hook.json").read_text() == "{}"
