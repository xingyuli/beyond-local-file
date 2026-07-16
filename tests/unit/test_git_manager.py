"""Unit tests for GitExcludeManager.

Covers the append-only write and line-level remove behaviour that preserves
pre-existing comments and blank lines in .git/info/exclude.
"""

from pathlib import Path

import pytest

from beyond_local_file.git_manager import GitExcludeManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal fake git repository.

    Args:
        tmp_path: Pytest temporary directory fixture.

    Returns:
        Path to the repo root (contains .git/info/exclude).
    """
    info_dir = tmp_path / ".git" / "info"
    info_dir.mkdir(parents=True)
    return tmp_path


def make_exclude(repo: Path, content: str) -> Path:
    """Write content to .git/info/exclude and return its path.

    Args:
        repo: Repo root path.
        content: File content to write.

    Returns:
        Path to the exclude file.
    """
    exclude = repo / ".git" / "info" / "exclude"
    exclude.write_text(content)
    return exclude


# ---------------------------------------------------------------------------
# write_entries — comment preservation
# ---------------------------------------------------------------------------


def test_write_entries_preserves_existing_comments(git_repo: Path) -> None:
    """write_entries must not strip pre-existing comment lines.

    Args:
        git_repo: Fake git repo fixture.
    """
    make_exclude(git_repo, "# git ls-files --others --exclude-from=.git/info/exclude\n# Lines that start with '#' are comments.\n")

    mgr = GitExcludeManager(git_repo)
    mgr.write_entries({"file.txt"})

    content = (git_repo / ".git" / "info" / "exclude").read_text()
    assert "# git ls-files" in content
    assert "# Lines that start" in content
    assert "file.txt" in content


def test_write_entries_preserves_blank_lines(git_repo: Path) -> None:
    """write_entries must not strip blank lines that already exist.

    Args:
        git_repo: Fake git repo fixture.
    """
    make_exclude(git_repo, "# header\n\nexisting.txt\n")

    mgr = GitExcludeManager(git_repo)
    mgr.write_entries({"new.txt"})

    content = (git_repo / ".git" / "info" / "exclude").read_text()
    assert "# header" in content
    assert "\n\n" in content  # blank line preserved
    assert "existing.txt" in content
    assert "new.txt" in content


def test_write_entries_does_not_duplicate_existing_entry(git_repo: Path) -> None:
    """write_entries must not append an entry that already exists.

    Args:
        git_repo: Fake git repo fixture.
    """
    make_exclude(git_repo, "already.txt\n")

    mgr = GitExcludeManager(git_repo)
    added, existing = mgr.write_entries({"already.txt"})

    content = (git_repo / ".git" / "info" / "exclude").read_text()
    assert content.count("already.txt") == 1
    assert added == 0
    assert "already.txt" in existing


def test_write_entries_appends_only_new_entries(git_repo: Path) -> None:
    """write_entries appends new entries and reports correct counts.

    Args:
        git_repo: Fake git repo fixture.
    """
    make_exclude(git_repo, "old.txt\n")

    mgr = GitExcludeManager(git_repo)
    added, existing = mgr.write_entries({"old.txt", "new.txt"})

    content = (git_repo / ".git" / "info" / "exclude").read_text()
    assert "old.txt" in content
    assert "new.txt" in content
    assert added == 1
    assert existing == {"old.txt"}


def test_write_entries_creates_file_when_missing(git_repo: Path) -> None:
    """write_entries creates .git/info/exclude when it does not yet exist.

    Args:
        git_repo: Fake git repo fixture.
    """
    mgr = GitExcludeManager(git_repo)
    added, existing = mgr.write_entries({"file.txt"})

    content = (git_repo / ".git" / "info" / "exclude").read_text()
    assert "file.txt" in content
    assert added == 1
    assert existing == set()


# ---------------------------------------------------------------------------
# remove_entries — comment preservation
# ---------------------------------------------------------------------------


def test_remove_entries_preserves_comments(git_repo: Path) -> None:
    """remove_entries must not strip comment lines.

    Args:
        git_repo: Fake git repo fixture.
    """
    make_exclude(git_repo, "# managed by blf\nkeep.txt\nremove.txt\n")

    mgr = GitExcludeManager(git_repo)
    removed = mgr.remove_entries({"remove.txt"})

    content = (git_repo / ".git" / "info" / "exclude").read_text()
    assert "# managed by blf" in content
    assert "keep.txt" in content
    assert "remove.txt" not in content
    assert removed == {"remove.txt"}


def test_remove_entries_preserves_blank_lines(git_repo: Path) -> None:
    """remove_entries must not strip blank lines.

    Args:
        git_repo: Fake git repo fixture.
    """
    make_exclude(git_repo, "keep.txt\n\nremove.txt\n")

    mgr = GitExcludeManager(git_repo)
    mgr.remove_entries({"remove.txt"})

    content = (git_repo / ".git" / "info" / "exclude").read_text()
    assert "keep.txt" in content
    assert "\n\n" in content  # blank line preserved
    assert "remove.txt" not in content


def test_remove_entries_only_removes_exact_match(git_repo: Path) -> None:
    """remove_entries must not touch lines it was not asked to remove.

    Args:
        git_repo: Fake git repo fixture.
    """
    make_exclude(git_repo, "alpha.txt\nbeta.txt\ngamma.txt\n")

    mgr = GitExcludeManager(git_repo)
    removed = mgr.remove_entries({"beta.txt"})

    content = (git_repo / ".git" / "info" / "exclude").read_text()
    assert "alpha.txt" in content
    assert "beta.txt" not in content
    assert "gamma.txt" in content
    assert removed == {"beta.txt"}


def test_remove_entries_returns_empty_set_when_file_missing(git_repo: Path) -> None:
    """remove_entries returns empty set when exclude file does not exist.

    Args:
        git_repo: Fake git repo fixture.
    """
    mgr = GitExcludeManager(git_repo)
    removed = mgr.remove_entries({"ghost.txt"})
    assert removed == set()


def test_remove_entries_returns_only_actually_removed(git_repo: Path) -> None:
    """remove_entries returns only entries that were actually present.

    Args:
        git_repo: Fake git repo fixture.
    """
    make_exclude(git_repo, "present.txt\n")

    mgr = GitExcludeManager(git_repo)
    removed = mgr.remove_entries({"present.txt", "absent.txt"})

    assert removed == {"present.txt"}
