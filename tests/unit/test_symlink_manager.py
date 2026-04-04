"""Unit tests for SymlinkManager.

These tests document the current behavior of SymlinkManager before refactoring,
providing a safety net to catch regressions during the manager responsibilities
refactoring task.
"""

from pathlib import Path

import pytest

from beyond_local_file.model.processing import ManagedProjectItem
from beyond_local_file.options import LinkStrategy
from beyond_local_file.symlink_manager import Action, SymlinkManager


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
    (project_dir / "subdir").mkdir()
    (project_dir / "subdir" / "file3.txt").write_text("content3")
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
def sample_items(temp_project_dir: Path) -> list[ManagedProjectItem]:
    """Create a sample list of managed project items.

    Args:
        temp_project_dir: Temporary project directory fixture.

    Returns:
        List of ManagedProjectItem instances.
    """
    return [
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
        ManagedProjectItem(
            name="subdir",
            path=temp_project_dir / "subdir",
            strategy=LinkStrategy.SYMLINK,
        ),
    ]


# Test Suite: SymlinkManager Sync Behavior


def test_sync_creates_symlinks_for_all_items(
    sample_items: list[ManagedProjectItem], temp_project_dir: Path, temp_target_dir: Path
) -> None:
    """Test that sync creates symlinks for all project items.

    Args:
        sample_items: Sample managed project items fixture.
        temp_project_dir: Temporary project directory fixture.
        temp_target_dir: Temporary target directory fixture.
    """
    manager = SymlinkManager(sample_items, temp_target_dir)
    result = manager.sync()

    # All items should be created
    assert len(result.created) == 3  # noqa: PLR2004 - test expects 3 items
    assert "file1.txt" in result.created
    assert "file2.txt" in result.created
    assert "subdir" in result.created

    # No items should be skipped or failed
    assert len(result.already_correct) == 0
    assert len(result.skipped) == 0
    assert len(result.failed) == 0
    assert not result.aborted

    # Verify symlinks exist and point to correct sources
    assert (temp_target_dir / "file1.txt").is_symlink()
    assert (temp_target_dir / "file2.txt").is_symlink()
    assert (temp_target_dir / "subdir").is_symlink()

    assert (temp_target_dir / "file1.txt").resolve() == (temp_project_dir / "file1.txt").resolve()
    assert (temp_target_dir / "file2.txt").resolve() == (temp_project_dir / "file2.txt").resolve()
    assert (temp_target_dir / "subdir").resolve() == (temp_project_dir / "subdir").resolve()


def test_sync_skips_existing_correct_symlinks(sample_items: list[ManagedProjectItem], temp_target_dir: Path) -> None:
    """Test that sync skips symlinks that already exist and are correct.

    Args:
        sample_items: Sample managed project items fixture.
        temp_target_dir: Temporary target directory fixture.
    """
    manager = SymlinkManager(sample_items, temp_target_dir)

    # First sync creates symlinks
    result1 = manager.sync()
    assert len(result1.created) == 3  # noqa: PLR2004 - test expects 3 items

    # Second sync should skip all items (already correct)
    result2 = manager.sync()
    assert len(result2.already_correct) == 3  # noqa: PLR2004 - test expects 3 items
    assert "file1.txt" in result2.already_correct
    assert "file2.txt" in result2.already_correct
    assert "subdir" in result2.already_correct

    assert len(result2.created) == 0
    assert len(result2.skipped) == 0
    assert len(result2.failed) == 0


def test_sync_detects_incorrect_symlinks(
    sample_items: list[ManagedProjectItem], temp_target_dir: Path
) -> None:
    """Test that sync detects symlinks pointing to wrong sources.

    Args:
        sample_items: Sample managed project items fixture.
        temp_target_dir: Temporary target directory fixture.
    """
    # Create incorrect symlinks (pointing to wrong sources)
    wrong_source = temp_target_dir / "wrong_source"
    wrong_source.mkdir()
    (temp_target_dir / "file1.txt").symlink_to(wrong_source)

    # Callback that returns SKIP
    def skip_callback(target_path: str, expected_source: str) -> Action:
        return Action.SKIP

    manager = SymlinkManager(sample_items, temp_target_dir)
    result = manager.sync(ask_callback=skip_callback)

    # file1.txt should be skipped (incorrect symlink)
    assert "file1.txt" in result.skipped
    # Other items should be created
    assert "file2.txt" in result.created
    assert "subdir" in result.created

    # Verify file1.txt still points to wrong source
    assert (temp_target_dir / "file1.txt").resolve() == wrong_source.resolve()


def test_sync_overwrites_with_callback_approval(
    sample_items: list[ManagedProjectItem], temp_project_dir: Path, temp_target_dir: Path
) -> None:
    """Test that sync overwrites incorrect symlinks when callback approves.

    Args:
        sample_items: Sample managed project items fixture.
        temp_project_dir: Temporary project directory fixture.
        temp_target_dir: Temporary target directory fixture.
    """
    # Create incorrect symlink
    wrong_source = temp_target_dir / "wrong_source"
    wrong_source.mkdir()
    (temp_target_dir / "file1.txt").symlink_to(wrong_source)

    # Callback that returns OVERWRITE
    def overwrite_callback(target_path: str, expected_source: str) -> Action:
        return Action.OVERWRITE

    manager = SymlinkManager(sample_items, temp_target_dir)
    result = manager.sync(ask_callback=overwrite_callback)

    # All items should be created (file1.txt overwritten)
    assert len(result.created) == 3  # noqa: PLR2004 - test expects 3 items
    assert "file1.txt" in result.created
    assert "file2.txt" in result.created
    assert "subdir" in result.created

    # Verify file1.txt now points to correct source
    assert (temp_target_dir / "file1.txt").resolve() == (temp_project_dir / "file1.txt").resolve()


# Test Suite: SymlinkManager Check Behavior


def test_check_reports_existing_symlinks(sample_items: list[ManagedProjectItem], temp_target_dir: Path) -> None:
    """Test that check reports symlinks that exist.

    Args:
        sample_items: Sample managed project items fixture.
        temp_target_dir: Temporary target directory fixture.
    """
    # Create symlinks
    manager = SymlinkManager(sample_items, temp_target_dir)
    manager.sync()

    # Check should report all symlinks as existing
    result = manager.check()
    assert len(result.symlink_exists) == 3  # noqa: PLR2004 - test expects 3 items
    assert "file1.txt" in result.symlink_exists
    assert "file2.txt" in result.symlink_exists
    assert "subdir" in result.symlink_exists

    assert len(result.symlink_missing) == 0


def test_check_reports_missing_symlinks(sample_items: list[ManagedProjectItem], temp_target_dir: Path) -> None:
    """Test that check reports symlinks that are missing.

    Args:
        sample_items: Sample managed project items fixture.
        temp_target_dir: Temporary target directory fixture.
    """
    manager = SymlinkManager(sample_items, temp_target_dir)

    # Check without creating symlinks
    result = manager.check()
    assert len(result.symlink_missing) == 3  # noqa: PLR2004 - test expects 3 items
    assert "file1.txt" in result.symlink_missing
    assert "file2.txt" in result.symlink_missing
    assert "subdir" in result.symlink_missing

    assert len(result.symlink_exists) == 0


# Test Suite: SymlinkManager Git Exclude Behavior


def test_check_reports_git_exclude_status(sample_items: list[ManagedProjectItem], tmp_path: Path) -> None:
    """Test that check reports git exclude status correctly.

    Args:
        sample_items: Sample managed project items fixture.
        tmp_path: Pytest temporary directory fixture.
    """
    # Create a git repo in target directory
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    git_dir = target_dir / ".git"
    git_dir.mkdir()
    info_dir = git_dir / "info"
    info_dir.mkdir()

    # Create exclude file with some entries
    exclude_file = info_dir / "exclude"
    exclude_file.write_text("file1.txt\n")

    manager = SymlinkManager(sample_items, target_dir)
    result = manager.check()

    # file1.txt should be in exclude_present
    assert "file1.txt" in result.exclude_present

    # file2.txt and subdir should be in exclude_missing
    assert "file2.txt" in result.exclude_missing
    assert "subdir" in result.exclude_missing


def test_check_git_excludes_with_protocol(sample_items: list[ManagedProjectItem], tmp_path: Path) -> None:
    """Test that check_git_excludes protocol method correctly identifies extra entries.

    After refactoring, managers use check_git_excludes(all_valid_entries) to
    identify extra git exclude entries. The all_valid_entries parameter contains
    names from ALL managers, preventing cross-manager false positives.

    Args:
        sample_items: Sample managed project items fixture.
        tmp_path: Pytest temporary directory fixture.
    """
    # Create a git repo in target directory
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    git_dir = target_dir / ".git"
    git_dir.mkdir()
    info_dir = git_dir / "info"
    info_dir.mkdir()

    # Create exclude file with symlink items + a copy item + a truly extra item
    exclude_file = info_dir / "exclude"
    exclude_file.write_text("file1.txt\nfile2.txt\nsubdir\ncopy_file.txt\nold_file.txt\n")

    # Simulate all_valid_entries from all managers (symlink + copy)
    all_valid_entries = {"file1.txt", "file2.txt", "subdir", "copy_file.txt"}

    manager = SymlinkManager(sample_items, target_dir)
    result = manager.check_git_excludes(all_valid_entries)

    # All symlink items should be in present
    assert "file1.txt" in result.present
    assert "file2.txt" in result.present
    assert "subdir" in result.present

    # copy_file.txt should NOT be in extra (it's in all_valid_entries from CopyManager)
    assert "copy_file.txt" not in result.extra

    # old_file.txt should be in extra (not in any manager)
    assert "old_file.txt" in result.extra
