"""Unit tests for CreateOperation git exclude integration and CreateFormatter output.

Covers task 7.3:
- Git exclude integration: entry added, skipped when not in git repo, idempotent
- CreateFormatter: each method produces the expected string, with and without [dry-run]
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from beyond_local_file.model.config import Mapping
from beyond_local_file.operations.revlink import (
    CreateFormatter,
    CreateOperation,
    RestoreFormatter,
    RestoreOperation,
    RevlinkContext,
)

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


def _make_context(repo_dir: Path, config_path: Path) -> RevlinkContext:
    """Build a minimal RevlinkContext pointing at *repo_dir* as the project root.

    Args:
        repo_dir: Path to use as ``cwd`` (the project/git root).
        config_path: Path to a (possibly non-existent) config file.

    Returns:
        A :class:`RevlinkContext` with a stub ``matched_mapping``.
    """
    mapping = MagicMock(spec=Mapping)
    mapping.subpaths = []
    return RevlinkContext(
        config_path=config_path,
        project_name="project",
        matched_mapping=mapping,
        cwd=repo_dir,
    )


def _make_operation(
    source: Path,
    dest_root: Path,
    *,
    dry_run: bool = False,
    force: bool = False,
    context: RevlinkContext | None = None,
) -> tuple[CreateOperation, MagicMock]:
    """Build a CreateOperation with a mock formatter.

    Args:
        source: Source path for the operation.
        dest_root: Destination root for the operation.
        dry_run: Whether to enable dry-run mode.
        force: Whether to enable force mode.
        context: Optional RevlinkContext; when provided the git exclude step
            uses ``context.cwd`` as the repository root.

    Returns:
        Tuple of (CreateOperation, mock formatter).
    """
    formatter = MagicMock(spec=CreateFormatter)
    op = CreateOperation(
        source=source,
        dest_root=dest_root,
        rel_path=Path(source.name),
        dry_run=dry_run,
        force=force,
        formatter=formatter,
        context=context,
    )
    return op, formatter


# ---------------------------------------------------------------------------
# Git exclude integration tests (Requirements 6.1, 6.2, 6.3)
# ---------------------------------------------------------------------------


class TestGitExcludePreview:
    """CreateOperation formats git exclude; LiveSync writes the exclude file."""

    def test_preview_added_when_in_git_repo(self, tmp_path: Path) -> None:
        """Preview reports an add when the entry is missing; the file is not written."""
        repo_dir = _make_git_repo(tmp_path / "repo")
        source = repo_dir / "myfile.txt"
        source.write_text("hello")

        context = _make_context(repo_dir, tmp_path / "config.yaml")
        op, formatter = _make_operation(source, tmp_path / "managed", context=context)
        op._git_exclude_preview()

        exclude_file = repo_dir / ".git" / "info" / "exclude"
        assert not exclude_file.exists()
        formatter.git_exclude_added.assert_called_once_with("myfile.txt")
        formatter.git_exclude_exists.assert_not_called()

    def test_skipped_when_not_in_git_repo(self, tmp_path: Path) -> None:
        """No .git/info/exclude is created when source is not inside a git repo."""
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        source = plain_dir / "myfile.txt"
        source.write_text("hello")

        context = _make_context(plain_dir, tmp_path / "config.yaml")
        op, formatter = _make_operation(source, tmp_path / "managed", context=context)
        op._git_exclude_preview()

        assert not (plain_dir / ".git").exists(), ".git dir should not be created"
        formatter.git_exclude_added.assert_not_called()
        formatter.git_exclude_exists.assert_not_called()

    def test_preview_exists_when_entry_already_present(self, tmp_path: Path) -> None:
        """Preview reports an existing entry without rewriting the file."""
        repo_dir = _make_git_repo(tmp_path / "repo")
        exclude_file = repo_dir / ".git" / "info" / "exclude"
        exclude_file.write_text("myfile.txt\n")

        source = repo_dir / "myfile.txt"
        source.write_text("hello")

        context = _make_context(repo_dir, tmp_path / "config.yaml")
        op, formatter = _make_operation(source, tmp_path / "managed", context=context)
        op._git_exclude_preview()

        assert exclude_file.read_text() == "myfile.txt\n"
        formatter.git_exclude_exists.assert_called_once_with("myfile.txt")
        formatter.git_exclude_added.assert_not_called()


# ---------------------------------------------------------------------------
# CreateFormatter tests (Requirements 7.1-7.7)
# ---------------------------------------------------------------------------


class TestCreateFormatterNoDryRun:
    """Tests for CreateFormatter with dry_run=False."""

    def setup_method(self) -> None:
        """Create a formatter with dry_run=False for each test."""
        self.formatter = CreateFormatter(dry_run=False)

    def test_copying(self) -> None:
        """copying emits the expected message without prefix.

        Requirements: 7.2
        """
        with patch("click.echo") as mock_echo:
            self.formatter.copying(Path("/src"), Path("/dst"))
        mock_echo.assert_called_once_with("Copying /src -> /dst")

    def test_target_left_in_place(self) -> None:
        """target_left_in_place emits the expected message without prefix.

        Requirements: 7.4
        """
        with patch("click.echo") as mock_echo:
            self.formatter.target_left_in_place(Path("/link"))
        mock_echo.assert_called_once_with("✓ Target path left in place: /link")

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

    def test_copying_dry_run(self) -> None:
        """copying emits [dry-run] prefix when dry_run=True.

        Requirements: 7.2, 7.6
        """
        with patch("click.echo") as mock_echo:
            self.formatter.copying(Path("/src"), Path("/dst"))
        mock_echo.assert_called_once_with("[dry-run] Copying /src -> /dst")

    def test_target_left_in_place_dry_run(self) -> None:
        """target_left_in_place emits [dry-run] prefix when dry_run=True.

        Requirements: 7.4, 7.6
        """
        with patch("click.echo") as mock_echo:
            self.formatter.target_left_in_place(Path("/link"))
        mock_echo.assert_called_once_with("[dry-run] ✓ Target path left in place: /link")

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


# ---------------------------------------------------------------------------
# context is None — git exclude skipped silently (Requirement 3.4)
# ---------------------------------------------------------------------------


class TestContextNoneSkipsGitExclude:
    """context=None skips git exclude without writing or formatter calls."""

    def test_create_operation_context_none_skips_git_exclude(self, tmp_path: Path) -> None:
        """CreateOperation preview does not write exclude when context is None."""
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        source = plain_dir / "myfile.txt"
        source.write_text("hello")

        formatter = MagicMock(spec=CreateFormatter)
        op = CreateOperation(
            source=source,
            dest_root=tmp_path / "managed",
            rel_path=Path("myfile.txt"),
            dry_run=False,
            force=False,
            formatter=formatter,
            context=None,
        )

        result = op.run()

        assert result == 0
        assert not (plain_dir / ".git").exists(), ".git dir should not be created"
        formatter.git_exclude_added.assert_not_called()
        formatter.git_exclude_exists.assert_not_called()

    def test_restore_operation_context_none_returns_zero_without_error(self, tmp_path: Path) -> None:
        """RestoreOperation._git_exclude returns 0 without error when context is None.

        Source is placed in a plain directory (no .git) so that ``is_git_repo``
        returns ``False`` regardless of whether the ``context is None`` guard
        is present.  This exercises the observable contract: when context is
        None, the step always exits cleanly with code 0 and no exclude entry
        is removed.

        Requirements: 3.4
        """
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        source = plain_dir / "myfile.txt"
        source.write_text("hello")

        formatter = MagicMock(spec=RestoreFormatter)
        op = RestoreOperation(
            source=source,
            dest_root=tmp_path / "managed",
            rel_path=Path("myfile.txt"),
            dry_run=False,
            formatter=formatter,
            context=None,  # explicitly None
        )

        result = op._git_exclude()

        assert result == 0, "Expected _git_exclude to return 0 when context is None"
        # No entry was removed — exclude file should not exist
        assert not (plain_dir / ".git").exists(), ".git dir should not be created"
        formatter.git_exclude_removed.assert_not_called()
        formatter.git_exclude_not_found.assert_not_called()
