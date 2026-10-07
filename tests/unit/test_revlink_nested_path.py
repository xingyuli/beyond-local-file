"""Unit tests for dest path correctness with nested rel_path.

CreateOperation formats dest and exclude as the full rel_path. Disk writes
are a LiveSync item-add job (see test_live_create).
"""

from pathlib import Path
from unittest.mock import patch

from beyond_local_file.model.config import Mapping
from beyond_local_file.operations.revlink import CreateOperation, RevlinkContext

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
    mapping = Mapping(targets=[cwd], subpaths=[])
    return RevlinkContext(
        config_path=tmp_path / "config.yaml",
        project_name="project",
        matched_mapping=mapping,
        cwd=cwd,
    )


def _make_operation(  # noqa: PLR0913 -- test helper needs the CreateOperation fields
    source: Path,
    dest_root: Path,
    rel_path: Path,
    *,
    dry_run: bool = False,
    force: bool = False,
    context: RevlinkContext | None = None,
) -> CreateOperation:
    """Build a CreateOperation.

    Args:
        source: Source path for the operation.
        dest_root: Destination root for the operation.
        rel_path: Relative path from CWD to source.
        dry_run: Whether to enable dry-run mode.
        force: Whether to enable force mode.
        context: Optional RevlinkContext for config-aware validation.
    """
    return CreateOperation(
        source=source,
        dest_root=dest_root,
        rel_path=rel_path,
        dry_run=dry_run,
        force=force,
        context=context,
    )


# ---------------------------------------------------------------------------
# Task 6.4 — CreateOperation.run() dest path correctness (Requirements 1.2, 1.4)
# ---------------------------------------------------------------------------


class TestRunDestPathWithNestedRelPath:
    """CreateOperation formats dest as dest_root / rel_path and does not copy."""

    def test_run_formats_full_rel_path_not_basename(self, tmp_path: Path) -> None:
        """Formatter dest is dest_root / rel_path; run does not write the hub copy."""
        source_dir = tmp_path / "target"
        source_dir.mkdir()
        source = source_dir / ".kiro" / "specs" / "foo"
        source.mkdir(parents=True)
        (source / "file.txt").write_text("content")

        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        result = _make_operation(source, dest_root, _NESTED_REL_PATH).run()

        assert result.exit_code == 0
        assert result.source == source.as_posix()
        assert result.dest == (dest_root / _NESTED_REL_PATH).as_posix()
        assert not (dest_root / ".kiro" / "specs" / "foo").exists()
        assert not (dest_root / "foo").exists()
        assert source.is_dir()
        assert not source.is_symlink()

    def test_run_file_at_nested_rel_path_formats_full_dest(self, tmp_path: Path) -> None:
        """A nested file is formatted at dest_root / rel_path, not basename."""
        source_dir = tmp_path / "target"
        source_dir.mkdir()
        nested_dir = source_dir / ".kiro" / "specs"
        nested_dir.mkdir(parents=True)
        source = nested_dir / "foo"
        source.write_text("spec content")

        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        result = _make_operation(source, dest_root, _NESTED_REL_PATH).run()

        assert result.exit_code == 0
        assert result.source == source.as_posix()
        assert result.dest == (dest_root / _NESTED_REL_PATH).as_posix()
        assert source.is_file()
        assert not (dest_root / "foo").exists()


# ---------------------------------------------------------------------------
# Nested rel_path git-exclude preview uses the full entry name
# ---------------------------------------------------------------------------


class TestGitExcludeEntryNameWithNestedRelPath:
    """Preview uses str(rel_path) as the exclude entry name, not source.name."""

    def test_git_exclude_formatter_called_with_full_rel_path(self, tmp_path: Path) -> None:
        """formatter.git_exclude_added is called with str(rel_path), not source.name."""
        repo_dir = _make_git_repo(tmp_path / "repo")
        source = repo_dir / "foo"
        source.mkdir()

        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        context = _make_context(repo_dir, tmp_path)
        result = _make_operation(source, dest_root, _NESTED_REL_PATH, dry_run=True, context=context).run()

        assert result.git_exclude == "added"
        assert result.git_exclude_name == ".kiro/specs/foo"

    def test_git_exclude_idempotent_with_full_rel_path(self, tmp_path: Path) -> None:
        """formatter.git_exclude_exists is called with str(rel_path) when entry already present."""
        repo_dir = _make_git_repo(tmp_path / "repo")
        exclude_file = repo_dir / ".git" / "info" / "exclude"
        exclude_file.write_text(".kiro/specs/foo\n")

        source = repo_dir / "foo"
        source.mkdir()

        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        context = _make_context(repo_dir, tmp_path)
        result = _make_operation(source, dest_root, _NESTED_REL_PATH, dry_run=True, context=context).run()

        assert result.git_exclude == "exists"
        assert result.git_exclude_name == ".kiro/specs/foo"

    def test_git_exclude_basename_entry_not_treated_as_match(self, tmp_path: Path) -> None:
        """An existing entry for just 'foo' does not satisfy the '.kiro/specs/foo' check."""
        repo_dir = _make_git_repo(tmp_path / "repo")
        exclude_file = repo_dir / ".git" / "info" / "exclude"
        exclude_file.write_text("foo\n")

        source = repo_dir / "foo"
        source.mkdir()

        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        context = _make_context(repo_dir, tmp_path)
        result = _make_operation(source, dest_root, _NESTED_REL_PATH, dry_run=True, context=context).run()

        assert result.git_exclude == "added"
        assert result.git_exclude_name == ".kiro/specs/foo"


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
        mapping = Mapping(targets=[tmp_path / "target"], subpaths=subpaths)
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

        op = _make_operation(source, dest_root, _NESTED_REL_PATH, context=context)

        with patch("beyond_local_file.operations.revlink.ConfigUpdater") as MockUpdater:
            mock_instance = MockUpdater.return_value
            mock_instance.add_subpath_entry.return_value = True
            entry = op._update_config()

        mock_instance.add_subpath_entry.assert_called_once()
        _, call_args, _ = mock_instance.add_subpath_entry.mock_calls[0]
        entry_name_arg = call_args[2]  # third positional arg is entry_name

        assert entry == ".kiro/specs/foo"
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

        op = _make_operation(source, dest_root, _NESTED_REL_PATH, context=context)

        with patch("beyond_local_file.operations.revlink.ConfigUpdater") as MockUpdater:
            mock_instance = MockUpdater.return_value
            mock_instance.add_subpath_entry.return_value = True
            entry = op._update_config()

        assert entry == ".kiro/specs/foo"

    def test_update_config_skipped_when_context_is_none(self, tmp_path: Path) -> None:
        """_update_config does nothing when context is None.

        Requirements: 4.2
        """
        source = tmp_path / "target" / ".kiro" / "specs" / "foo"
        source.mkdir(parents=True)
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        op = _make_operation(source, dest_root, _NESTED_REL_PATH, context=None)

        with patch("beyond_local_file.operations.revlink.ConfigUpdater") as MockUpdater:
            entry = op._update_config()

        MockUpdater.assert_not_called()
        assert entry is None

    def test_update_config_skipped_when_mapping_is_sync_all(self, tmp_path: Path) -> None:
        """_update_config does nothing when the matched mapping uses sync-all (subpaths is None).

        Requirements: 4.2
        """
        source = tmp_path / "target" / ".kiro" / "specs" / "foo"
        source.mkdir(parents=True)
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        context = self._make_context(tmp_path, subpaths=None)

        op = _make_operation(source, dest_root, _NESTED_REL_PATH, context=context)

        with patch("beyond_local_file.operations.revlink.ConfigUpdater") as MockUpdater:
            entry = op._update_config()

        MockUpdater.assert_not_called()
        assert entry is None
