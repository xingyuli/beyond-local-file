"""Unit tests for CreateOperation git exclude integration and CreateFormatter output.

Covers task 7.3:
- Git exclude integration: entry added, skipped when not in git repo, idempotent
- CreateFormatter: each method produces the expected string, with and without [dry-run]
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from beyond_local_file.operations.revlink import CreateFormatter, CreateOperation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_git_repo(base: Path) -> Path:
    """Create a minimal .git/info/ structure under *base* and return *base*.

    Args:
        base: Directory that should become a fake git repository.

    Returns:
        The same *base* path, now containing ``.git/info/``.
    """
    (base / ".git" / "info").mkdir(parents=True)
    return base


def _make_operation(
    source: Path,
    dest_root: Path,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> tuple[CreateOperation, MagicMock]:
    """Build a CreateOperation with a mock formatter.

    Args:
        source: Source path for the operation.
        dest_root: Destination root for the operation.
        dry_run: Whether to enable dry-run mode.
        force: Whether to enable force mode.

    Returns:
        Tuple of (CreateOperation, mock formatter).
    """
    formatter = MagicMock(spec=CreateFormatter)
    op = CreateOperation(
        source=source,
        dest_root=dest_root,
        dry_run=dry_run,
        force=force,
        formatter=formatter,
    )
    return op, formatter


# ---------------------------------------------------------------------------
# Git exclude integration tests (Requirements 6.1, 6.2, 6.3)
# ---------------------------------------------------------------------------


class TestGitExcludeIntegration:
    """Tests for CreateOperation._git_exclude() behaviour."""

    def test_entry_added_when_in_git_repo(self, tmp_path: Path) -> None:
        """Entry is written to .git/info/exclude when source is inside a git repo.

        Requirements: 6.1
        """
        repo_dir = _make_git_repo(tmp_path / "repo")
        source = repo_dir / "myfile.txt"
        source.write_text("hello")

        op, formatter = _make_operation(source, tmp_path / "managed")
        op._git_exclude()

        exclude_file = repo_dir / ".git" / "info" / "exclude"
        assert exclude_file.exists(), "exclude file should have been created"
        assert "myfile.txt" in exclude_file.read_text()
        formatter.git_exclude_added.assert_called_once_with("myfile.txt")
        formatter.git_exclude_exists.assert_not_called()

    def test_skipped_when_not_in_git_repo(self, tmp_path: Path) -> None:
        """No .git/info/exclude is created when source is not inside a git repo.

        Requirements: 6.3
        """
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        source = plain_dir / "myfile.txt"
        source.write_text("hello")

        op, formatter = _make_operation(source, tmp_path / "managed")
        result = op._git_exclude()

        assert result == 0
        assert not (plain_dir / ".git").exists(), ".git dir should not be created"
        formatter.git_exclude_added.assert_not_called()
        formatter.git_exclude_exists.assert_not_called()

    def test_idempotent_when_entry_already_present(self, tmp_path: Path) -> None:
        """formatter.git_exclude_exists is called when entry is already in exclude file.

        Requirements: 6.2
        """
        repo_dir = _make_git_repo(tmp_path / "repo")
        exclude_file = repo_dir / ".git" / "info" / "exclude"
        exclude_file.write_text("myfile.txt\n")

        source = repo_dir / "myfile.txt"
        source.write_text("hello")

        op, formatter = _make_operation(source, tmp_path / "managed")
        op._git_exclude()

        # File content should still contain the entry (unchanged)
        assert "myfile.txt" in exclude_file.read_text()
        formatter.git_exclude_exists.assert_called_once_with("myfile.txt")
        formatter.git_exclude_added.assert_not_called()

    def test_git_exclude_returns_zero(self, tmp_path: Path) -> None:
        """_git_exclude always returns 0 regardless of outcome.

        Requirements: 6.1, 6.2, 6.3
        """
        # In git repo
        repo_dir = _make_git_repo(tmp_path / "repo")
        source = repo_dir / "f.txt"
        source.write_text("x")
        op, _ = _make_operation(source, tmp_path / "managed")
        assert op._git_exclude() == 0

        # Not in git repo
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        source2 = plain_dir / "f.txt"
        source2.write_text("x")
        op2, _ = _make_operation(source2, tmp_path / "managed2")
        assert op2._git_exclude() == 0


# ---------------------------------------------------------------------------
# CreateFormatter tests (Requirements 7.1-7.7)
# ---------------------------------------------------------------------------


class TestCreateFormatterNoDryRun:
    """Tests for CreateFormatter with dry_run=False."""

    def setup_method(self) -> None:
        """Create a formatter with dry_run=False for each test."""
        self.formatter = CreateFormatter(dry_run=False)

    def test_computing_checksum(self) -> None:
        """computing_checksum emits the expected message without prefix.

        Requirements: 7.1
        """
        with patch("click.echo") as mock_echo:
            self.formatter.computing_checksum(Path("/some/path"))
        mock_echo.assert_called_once_with("Computing checksum of /some/path")

    def test_copying(self) -> None:
        """copying emits the expected message without prefix.

        Requirements: 7.2
        """
        with patch("click.echo") as mock_echo:
            self.formatter.copying(Path("/src"), Path("/dst"))
        mock_echo.assert_called_once_with("Copying /src -> /dst")

    def test_checksum_ok(self) -> None:
        """checksum_ok emits the expected message without prefix.

        Requirements: 7.3
        """
        with patch("click.echo") as mock_echo:
            self.formatter.checksum_ok()
        mock_echo.assert_called_once_with("✓ MD5 checksum verified")

    def test_symlink_created(self) -> None:
        """symlink_created emits the expected message without prefix.

        Requirements: 7.4
        """
        with patch("click.echo") as mock_echo:
            self.formatter.symlink_created(Path("/link"), Path("/target"))
        mock_echo.assert_called_once_with("✓ Symlink created: /link -> /target")

    def test_git_exclude_added(self) -> None:
        """git_exclude_added emits the expected message without prefix.

        Requirements: 7.5
        """
        with patch("click.echo") as mock_echo:
            self.formatter.git_exclude_added("myfile")
        mock_echo.assert_called_once_with("Added 'myfile' to .git/info/exclude")

    def test_git_exclude_exists(self) -> None:
        """git_exclude_exists emits the expected message without prefix.

        Requirements: 7.5
        """
        with patch("click.echo") as mock_echo:
            self.formatter.git_exclude_exists("myfile")
        mock_echo.assert_called_once_with("'myfile' already in .git/info/exclude")

    def test_force_warning(self) -> None:
        """force_warning emits the expected message without prefix.

        Requirements: 7.7
        """
        with patch("click.echo") as mock_echo:
            self.formatter.force_warning(Path("/dest"))
        mock_echo.assert_called_once_with("Warning: overwriting existing managed copy at /dest")

    def test_error(self) -> None:
        """error emits the expected message without prefix.

        Requirements: 7.1-7.7 (error path)
        """
        with patch("click.echo") as mock_echo:
            self.formatter.error("some error")
        mock_echo.assert_called_once_with("Error: some error")


class TestCreateFormatterDryRun:
    """Tests for CreateFormatter with dry_run=True — all output prefixed with [dry-run].

    Requirements: 7.6
    """

    def setup_method(self) -> None:
        """Create a formatter with dry_run=True for each test."""
        self.formatter = CreateFormatter(dry_run=True)

    def test_computing_checksum_dry_run(self) -> None:
        """computing_checksum emits [dry-run] prefix when dry_run=True.

        Requirements: 7.1, 7.6
        """
        with patch("click.echo") as mock_echo:
            self.formatter.computing_checksum(Path("/some/path"))
        mock_echo.assert_called_once_with("[dry-run] Computing checksum of /some/path")

    def test_copying_dry_run(self) -> None:
        """copying emits [dry-run] prefix when dry_run=True.

        Requirements: 7.2, 7.6
        """
        with patch("click.echo") as mock_echo:
            self.formatter.copying(Path("/src"), Path("/dst"))
        mock_echo.assert_called_once_with("[dry-run] Copying /src -> /dst")

    def test_checksum_ok_dry_run(self) -> None:
        """checksum_ok emits [dry-run] prefix when dry_run=True.

        Requirements: 7.3, 7.6
        """
        with patch("click.echo") as mock_echo:
            self.formatter.checksum_ok()
        mock_echo.assert_called_once_with("[dry-run] ✓ MD5 checksum verified")

    def test_symlink_created_dry_run(self) -> None:
        """symlink_created emits [dry-run] prefix when dry_run=True.

        Requirements: 7.4, 7.6
        """
        with patch("click.echo") as mock_echo:
            self.formatter.symlink_created(Path("/link"), Path("/target"))
        mock_echo.assert_called_once_with("[dry-run] ✓ Symlink created: /link -> /target")

    def test_git_exclude_added_dry_run(self) -> None:
        """git_exclude_added emits [dry-run] prefix when dry_run=True.

        Requirements: 7.5, 7.6
        """
        with patch("click.echo") as mock_echo:
            self.formatter.git_exclude_added("myfile")
        mock_echo.assert_called_once_with("[dry-run] Added 'myfile' to .git/info/exclude")

    def test_git_exclude_exists_dry_run(self) -> None:
        """git_exclude_exists emits [dry-run] prefix when dry_run=True.

        Requirements: 7.5, 7.6
        """
        with patch("click.echo") as mock_echo:
            self.formatter.git_exclude_exists("myfile")
        mock_echo.assert_called_once_with("[dry-run] 'myfile' already in .git/info/exclude")

    def test_force_warning_dry_run(self) -> None:
        """force_warning emits [dry-run] prefix when dry_run=True.

        Requirements: 7.6, 7.7
        """
        with patch("click.echo") as mock_echo:
            self.formatter.force_warning(Path("/dest"))
        mock_echo.assert_called_once_with("[dry-run] Warning: overwriting existing managed copy at /dest")

    def test_error_dry_run(self) -> None:
        """error emits [dry-run] prefix when dry_run=True.

        Requirements: 7.6
        """
        with patch("click.echo") as mock_echo:
            self.formatter.error("some error")
        mock_echo.assert_called_once_with("[dry-run] Error: some error")
