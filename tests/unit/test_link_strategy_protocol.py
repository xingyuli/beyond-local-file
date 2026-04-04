"""Unit tests for LinkStrategyManager protocol.

These tests verify that the protocol is correctly defined and that
managers implement it properly with unified signatures.
"""

from pathlib import Path

import pytest

from beyond_local_file.link_strategy_protocol import (
    GitExcludeAddResult,
    GitExcludeCheckResult,
    LinkCheckResult,
    LinkCreateResult,
    LinkStrategyManager,
)
from beyond_local_file.model.processing import ManagedProjectItem
from beyond_local_file.options import LinkStrategy
from beyond_local_file.symlink_manager import SymlinkManager


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
    ]


def test_protocol_defines_get_managed_items_method() -> None:
    """Test that the protocol defines get_managed_items method."""
    assert hasattr(LinkStrategyManager, "get_managed_items")


def test_protocol_defines_create_links_method() -> None:
    """Test that the protocol defines create_links method."""
    assert hasattr(LinkStrategyManager, "create_links")


def test_protocol_defines_check_links_method() -> None:
    """Test that the protocol defines check_links method."""
    assert hasattr(LinkStrategyManager, "check_links")


def test_protocol_defines_add_git_excludes_method() -> None:
    """Test that the protocol defines add_git_excludes method (plural)."""
    assert hasattr(LinkStrategyManager, "add_git_excludes")


def test_protocol_defines_check_git_excludes_method() -> None:
    """Test that the protocol defines check_git_excludes method (plural)."""
    assert hasattr(LinkStrategyManager, "check_git_excludes")


def test_symlink_manager_implements_protocol(
    sample_items: list[ManagedProjectItem],
    temp_target_dir: Path,
) -> None:
    """Test that SymlinkManager implements the LinkStrategyManager protocol.

    Args:
        sample_items: Sample managed project items fixture.
        temp_target_dir: Temporary target directory fixture.
    """
    manager = SymlinkManager(sample_items, temp_target_dir)

    # Verify manager has all protocol methods
    assert hasattr(manager, "get_managed_items")
    assert hasattr(manager, "create_links")
    assert hasattr(manager, "check_links")
    assert hasattr(manager, "add_git_excludes")
    assert hasattr(manager, "check_git_excludes")

    # Verify methods are callable
    assert callable(manager.get_managed_items)
    assert callable(manager.create_links)
    assert callable(manager.check_links)
    assert callable(manager.add_git_excludes)
    assert callable(manager.check_git_excludes)


def test_copy_manager_implements_protocol(
    temp_project_dir: Path,
    temp_target_dir: Path,
) -> None:
    """Test that CopyManager implements the LinkStrategyManager protocol.

    Args:
        temp_project_dir: Temporary project directory fixture.
        temp_target_dir: Temporary target directory fixture.
    """
    from beyond_local_file.copy_manager import CopyManager  # noqa: PLC0415 -- avoid circular import

    copy_items = [
        ManagedProjectItem(
            name="file1.txt",
            path=temp_project_dir / "file1.txt",
            strategy=LinkStrategy.COPY,
        ),
    ]

    manager = CopyManager(copy_items, temp_target_dir, temp_project_dir)

    # Verify manager has all protocol methods
    assert hasattr(manager, "get_managed_items")
    assert hasattr(manager, "create_links")
    assert hasattr(manager, "check_links")
    assert hasattr(manager, "add_git_excludes")
    assert hasattr(manager, "check_git_excludes")

    # Verify methods are callable
    assert callable(manager.get_managed_items)
    assert callable(manager.create_links)
    assert callable(manager.check_links)
    assert callable(manager.add_git_excludes)
    assert callable(manager.check_git_excludes)


def test_protocol_methods_return_unified_types(
    sample_items: list[ManagedProjectItem],
    temp_target_dir: Path,
) -> None:
    """Test that protocol methods return unified result types.

    Args:
        sample_items: Sample managed project items fixture.
        temp_target_dir: Temporary target directory fixture.
    """
    manager = SymlinkManager(sample_items, temp_target_dir)

    # Test get_managed_items returns list
    items = manager.get_managed_items()
    assert isinstance(items, list)
    assert len(items) == 1
    assert items[0].name == "file1.txt"

    # Test create_links returns LinkCreateResult
    link_result = manager.create_links()
    assert isinstance(link_result, LinkCreateResult)
    assert hasattr(link_result, "created")
    assert hasattr(link_result, "already_correct")
    assert hasattr(link_result, "skipped")
    assert hasattr(link_result, "failed")
    assert hasattr(link_result, "details")

    # Test check_links returns LinkCheckResult
    check_result = manager.check_links()
    assert isinstance(check_result, LinkCheckResult)
    assert hasattr(check_result, "exists")
    assert hasattr(check_result, "missing")
    assert hasattr(check_result, "details")

    # Test add_git_excludes returns GitExcludeAddResult
    git_add_result = manager.add_git_excludes()
    assert isinstance(git_add_result, GitExcludeAddResult)
    assert hasattr(git_add_result, "added")
    assert hasattr(git_add_result, "existing")

    # Test check_git_excludes returns GitExcludeCheckResult
    git_check_result = manager.check_git_excludes({"file1.txt"})
    assert isinstance(git_check_result, GitExcludeCheckResult)
    assert hasattr(git_check_result, "present")
    assert hasattr(git_check_result, "missing")
    assert hasattr(git_check_result, "extra")
