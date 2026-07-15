"""Unit tests for dest path correctness with nested rel_path.

Covers task 6.4:
- CreateOperation.run() derives dest as dest_root / rel_path (not dest_root / rel_path.name)
- CreateOperation._git_exclude() uses str(rel_path) as the entry name, not source.name
- CreateOperation._update_config() uses str(rel_path) as the entry name, not source.name

Requirements: 1.2, 1.4, 4.1, 4.2
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from beyond_local_file.model.config import Mapping
from beyond_local_file.operations.revlink import CreateFormatter, CreateOperation, RevlinkContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NESTED_REL_PATH = Path(".kiro/specs/foo")
_NESTED_BASENAME = "foo"


def _make_git_repo(base: Path) -> Path:
    """Create a minimal .git/info/ structure under *base* and return *base*.

    Args:
        base: Directory that should become a fake git repository.

    Returns:
        The same *base* path, now containing ``.git/info/``.
    """
    (base / ".git" / "info").mkdir(parents=True)
    return base


def _make_context(cwd: Path, tmp_path: Path) -> RevlinkContext:
    """Build a minimal RevlinkContext using *cwd* as the project root.

    Args:
        cwd: The current working directory / project root for the context.
        tmp_path: Temporary directory used to place the config file.

    Returns:
        A :class:`RevlinkContext` with a stub ``matched_mapping``.
    """
    mapping = MagicMock(spec=Mapping)
    mapping.subpaths = []
    return RevlinkContext(
        config_path=tmp_path / "config.yaml",
        project_name="project",
        matched_mapping=mapping,
        cwd=cwd,
    )


def _make_operation(  # noqa: PLR0913 -- test helper needs all six fields to build CreateOperation
    source: Path,
    dest_root: Path,
    rel_path: Path,
    *,
    dry_run: bool = False,
    force: bool = False,
    context: RevlinkContext | None = None,
) -> tuple[CreateOperation, MagicMock]:
    """Build a CreateOperation with a mock formatter.

    Args:
        source: Source path for the operation.
        dest_root: Destination root for the operation.
        rel_path: Relative path from CWD to source.
        dry_run: Whether to enable dry-run mode.
        force: Whether to enable force mode.
        context: Optional RevlinkContext for config-aware validation.

    Returns:
        Tuple of (CreateOperation, mock formatter).
    """
    formatter = MagicMock(spec=CreateFormatter)
    op = CreateOperation(
        source=source,
        dest_root=dest_root,
        rel_path=rel_path,
        dry_run=dry_run,
        force=force,
        formatter=formatter,
        context=context,
    )
    return op, formatter


# ---------------------------------------------------------------------------
# Task 6.4 — CreateOperation.run() dest path correctness (Requirements 1.2, 1.4)
# ---------------------------------------------------------------------------


class TestRunDestPathWithNestedRelPath:
    """Tests that run() places the managed copy at dest_root / rel_path, not dest_root / basename."""

    def test_run_copies_to_full_rel_path_not_basename(self, tmp_path: Path) -> None:
        """Managed copy is placed at dest_root / rel_path, not dest_root / source.name.

        Requirements: 1.2, 1.4
        """
        # Set up source at a nested location
        source_dir = tmp_path / "target"
        source_dir.mkdir()
        source = source_dir / ".kiro" / "specs" / "foo"
        source.mkdir(parents=True)
        (source / "file.txt").write_text("content")

        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        op, _ = _make_operation(source, dest_root, _NESTED_REL_PATH)
        result = op.run()

        assert result == 0

        # The copy must be at dest_root / .kiro/specs/foo — NOT dest_root / foo
        correct_dest = dest_root / ".kiro" / "specs" / "foo"
        wrong_dest = dest_root / "foo"

        assert correct_dest.exists(), f"Managed copy must be at {correct_dest} (full rel_path), not at basename"
        assert not wrong_dest.exists(), f"Managed copy must NOT be at {wrong_dest} (basename only)"

    def test_run_creates_parent_dirs_for_nested_dest(self, tmp_path: Path) -> None:
        """Parent directories of the nested managed destination are created automatically.

        Requirements: 1.3
        """
        source_dir = tmp_path / "target"
        source_dir.mkdir()
        source = source_dir / ".kiro" / "specs" / "foo"
        source.mkdir(parents=True)
        (source / "readme.md").write_text("hello")

        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        op, _ = _make_operation(source, dest_root, _NESTED_REL_PATH)
        result = op.run()

        assert result == 0
        assert (dest_root / ".kiro" / "specs").is_dir(), "Intermediate parent directories must be created"

    def test_run_symlink_points_to_full_rel_path_dest(self, tmp_path: Path) -> None:
        """The symlink at source points to dest_root / rel_path, not dest_root / basename.

        Requirements: 1.4
        """
        source_dir = tmp_path / "target"
        source_dir.mkdir()
        source = source_dir / ".kiro" / "specs" / "foo"
        source.mkdir(parents=True)
        (source / "data.txt").write_text("data")

        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        op, _ = _make_operation(source, dest_root, _NESTED_REL_PATH)
        result = op.run()

        assert result == 0
        assert source.is_symlink(), "Source must have been replaced with a symlink"

        expected_target = dest_root / ".kiro" / "specs" / "foo"
        assert source.resolve() == expected_target.resolve(), (
            f"Symlink must point to {expected_target}, not {dest_root / 'foo'}"
        )

    def test_run_file_at_nested_rel_path(self, tmp_path: Path) -> None:
        """run() works correctly for a file (not directory) at a nested rel_path.

        Requirements: 1.2
        """
        source_dir = tmp_path / "target"
        source_dir.mkdir()
        nested_dir = source_dir / ".kiro" / "specs"
        nested_dir.mkdir(parents=True)
        source = nested_dir / "foo"
        source.write_text("spec content")

        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        op, _ = _make_operation(source, dest_root, _NESTED_REL_PATH)
        result = op.run()

        assert result == 0

        correct_dest = dest_root / ".kiro" / "specs" / "foo"
        wrong_dest = dest_root / "foo"

        assert correct_dest.exists(), f"File must be at {correct_dest}"
        assert not wrong_dest.exists(), f"File must NOT be at {wrong_dest}"


# ---------------------------------------------------------------------------
# Task 6.4 — CreateOperation._git_exclude() entry name (Requirement 4.1)
# ---------------------------------------------------------------------------


class TestGitExcludeEntryNameWithNestedRelPath:
    """Tests that _git_exclude() uses str(rel_path) as the entry name, not source.name.

    Note: GitExcludeManager is initialised with source.parent and checks for .git
    directly in that directory (no upward walk).  To exercise the git-repo branch,
    the source must be a direct child of the git repo root so that source.parent
    contains .git.  The rel_path is set to the nested value (.kiro/specs/foo) to
    verify the entry name — the source location relative to the repo is irrelevant
    for this test.
    """

    def test_git_exclude_entry_uses_full_rel_path_not_basename(self, tmp_path: Path) -> None:
        """Entry written to .git/info/exclude is str(rel_path), not source.name.

        Requirements: 4.1
        """
        # source.parent must contain .git — place source as a direct child of repo_dir
        repo_dir = _make_git_repo(tmp_path / "repo")
        source = repo_dir / "foo"
        source.mkdir()

        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        # rel_path is the nested path — this is what the entry name must be
        context = _make_context(repo_dir, tmp_path)
        op, _formatter = _make_operation(source, dest_root, _NESTED_REL_PATH, context=context)
        result = op._git_exclude()

        assert result == 0

        exclude_file = repo_dir / ".git" / "info" / "exclude"
        assert exclude_file.exists(), "exclude file should have been created"
        content = exclude_file.read_text()

        # Full rel_path must appear in the exclude file
        assert ".kiro/specs/foo" in content, "Exclude entry must be the full rel_path '.kiro/specs/foo'"
        # Basename alone must NOT appear as a standalone entry
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        assert "foo" not in lines, "Exclude entry must NOT be just the basename 'foo'"

    def test_git_exclude_formatter_called_with_full_rel_path(self, tmp_path: Path) -> None:
        """formatter.git_exclude_added is called with str(rel_path), not source.name.

        Requirements: 4.1
        """
        repo_dir = _make_git_repo(tmp_path / "repo")
        source = repo_dir / "foo"
        source.mkdir()

        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        context = _make_context(repo_dir, tmp_path)
        op, formatter = _make_operation(source, dest_root, _NESTED_REL_PATH, context=context)
        op._git_exclude()

        formatter.git_exclude_added.assert_called_once_with(".kiro/specs/foo")

    def test_git_exclude_idempotent_with_full_rel_path(self, tmp_path: Path) -> None:
        """formatter.git_exclude_exists is called with str(rel_path) when entry already present.

        Requirements: 4.1
        """
        repo_dir = _make_git_repo(tmp_path / "repo")
        exclude_file = repo_dir / ".git" / "info" / "exclude"
        exclude_file.write_text(".kiro/specs/foo\n")

        source = repo_dir / "foo"
        source.mkdir()

        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        context = _make_context(repo_dir, tmp_path)
        op, formatter = _make_operation(source, dest_root, _NESTED_REL_PATH, context=context)
        op._git_exclude()

        formatter.git_exclude_exists.assert_called_once_with(".kiro/specs/foo")
        formatter.git_exclude_added.assert_not_called()

    def test_git_exclude_basename_entry_not_treated_as_match(self, tmp_path: Path) -> None:
        """An existing entry for just 'foo' does not satisfy the '.kiro/specs/foo' check.

        Requirements: 4.1
        """
        repo_dir = _make_git_repo(tmp_path / "repo")
        exclude_file = repo_dir / ".git" / "info" / "exclude"
        # Only the basename is present — should NOT be treated as a match
        exclude_file.write_text("foo\n")

        source = repo_dir / "foo"
        source.mkdir()

        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        context = _make_context(repo_dir, tmp_path)
        op, formatter = _make_operation(source, dest_root, _NESTED_REL_PATH, context=context)
        op._git_exclude()

        # The full rel_path entry is missing, so it should be added
        formatter.git_exclude_added.assert_called_once_with(".kiro/specs/foo")
        formatter.git_exclude_exists.assert_not_called()


# ---------------------------------------------------------------------------
# Task 6.4 — CreateOperation._update_config() entry name (Requirement 4.2)
# ---------------------------------------------------------------------------


class TestUpdateConfigEntryNameWithNestedRelPath:
    """Tests that _update_config() uses str(rel_path) as the entry name, not source.name."""

    def _make_context(self, tmp_path: Path, *, subpaths: list[str] | None = None) -> RevlinkContext:
        """Build a minimal RevlinkContext with a selective-sync mapping.

        Args:
            tmp_path: Temporary directory for the config file.
            subpaths: Subpath list for the matched mapping. ``None`` means sync-all.

        Returns:
            A RevlinkContext with a mock matched_mapping.
        """
        config_path = tmp_path / "config.yaml"
        config_path.write_text("project: {}\n")

        mapping = MagicMock(spec=Mapping)
        mapping.subpaths = subpaths if subpaths is not None else []

        return RevlinkContext(
            config_path=config_path,
            project_name="project",
            cwd=tmp_path / "target",
            matched_mapping=mapping,
        )

    def test_update_config_uses_full_rel_path_not_basename(self, tmp_path: Path) -> None:
        """add_subpath_entry is called with str(rel_path), not source.name.

        Requirements: 4.2
        """
        source = tmp_path / "target" / ".kiro" / "specs" / "foo"
        source.mkdir(parents=True)
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        context = self._make_context(tmp_path, subpaths=[])

        op, _formatter = _make_operation(source, dest_root, _NESTED_REL_PATH, context=context)

        with patch("beyond_local_file.operations.revlink.ConfigUpdater") as MockUpdater:
            mock_instance = MockUpdater.return_value
            mock_instance.add_subpath_entry.return_value = True

            op._update_config()

        mock_instance.add_subpath_entry.assert_called_once()
        _, call_args, _ = mock_instance.add_subpath_entry.mock_calls[0]
        entry_name_arg = call_args[2]  # third positional arg is entry_name

        assert entry_name_arg == ".kiro/specs/foo", (
            f"add_subpath_entry must be called with '.kiro/specs/foo', got '{entry_name_arg}'"
        )
        assert entry_name_arg != _NESTED_BASENAME, "add_subpath_entry must NOT be called with just the basename 'foo'"

    def test_update_config_formatter_called_with_full_rel_path(self, tmp_path: Path) -> None:
        """formatter.config_updated is called with str(rel_path), not source.name.

        Requirements: 4.2
        """
        source = tmp_path / "target" / ".kiro" / "specs" / "foo"
        source.mkdir(parents=True)
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        context = self._make_context(tmp_path, subpaths=[])

        op, formatter = _make_operation(source, dest_root, _NESTED_REL_PATH, context=context)

        with patch("beyond_local_file.operations.revlink.ConfigUpdater") as MockUpdater:
            mock_instance = MockUpdater.return_value
            mock_instance.add_subpath_entry.return_value = True

            op._update_config()

        formatter.config_updated.assert_called_once_with(".kiro/specs/foo")

    def test_update_config_skipped_when_context_is_none(self, tmp_path: Path) -> None:
        """_update_config does nothing when context is None.

        Requirements: 4.2
        """
        source = tmp_path / "target" / ".kiro" / "specs" / "foo"
        source.mkdir(parents=True)
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        op, formatter = _make_operation(source, dest_root, _NESTED_REL_PATH, context=None)

        with patch("beyond_local_file.operations.revlink.ConfigUpdater") as MockUpdater:
            op._update_config()

        MockUpdater.assert_not_called()
        formatter.config_updated.assert_not_called()

    def test_update_config_skipped_when_mapping_is_sync_all(self, tmp_path: Path) -> None:
        """_update_config does nothing when the matched mapping uses sync-all (subpaths is None).

        Requirements: 4.2
        """
        source = tmp_path / "target" / ".kiro" / "specs" / "foo"
        source.mkdir(parents=True)
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        context = self._make_context(tmp_path, subpaths=None)
        context.matched_mapping.subpaths = None  # sync-all

        op, formatter = _make_operation(source, dest_root, _NESTED_REL_PATH, context=context)

        with patch("beyond_local_file.operations.revlink.ConfigUpdater") as MockUpdater:
            op._update_config()

        MockUpdater.assert_not_called()
        formatter.config_updated.assert_not_called()
