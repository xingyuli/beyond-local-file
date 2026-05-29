"""Unit tests for CreateOperation._validate Rule 3 (intermediate symlink).

Covers task 6.1:
- Ancestor symlink resolves into managed project → exit 0 with info message
- Ancestor symlink resolves outside managed project → exit 1 with error message
- No ancestor symlink → Rule 3 has no effect, validation continues
- context is None → Rule 3 is skipped entirely

Requirements: 5 (Requirement 6 in requirements.md)
"""

from pathlib import Path
from unittest.mock import MagicMock

from beyond_local_file.model.config import Mapping
from beyond_local_file.operations.revlink import CreateFormatter, CreateOperation, RevlinkContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(cwd: Path, dest_root: Path, *, subpaths: list[str] | None = None) -> RevlinkContext:
    """Build a RevlinkContext with a minimal Mapping.

    Args:
        cwd: The current working directory for the context.
        dest_root: The managed project path (used as the config_path parent
            and as the dest_root for the operation).
        subpaths: Optional subpath list for the matched mapping.

    Returns:
        A RevlinkContext whose matched_mapping targets ``cwd``.
    """
    mapping = Mapping(targets=[cwd], subpaths=subpaths)
    return RevlinkContext(
        config_path=dest_root / "blf.yaml",
        project_name="test-project",
        matched_mapping=mapping,
        cwd=cwd,
    )


def _make_operation(
    source: Path,
    dest_root: Path,
    rel_path: Path,
    context: RevlinkContext | None,
) -> tuple[CreateOperation, MagicMock]:
    """Build a CreateOperation with a mock formatter.

    Args:
        source: Absolute source path for the operation.
        dest_root: Destination root (managed project path).
        rel_path: Relative path from CWD to source.
        context: RevlinkContext to attach, or None.

    Returns:
        Tuple of (CreateOperation, mock formatter).
    """
    formatter = MagicMock(spec=CreateFormatter)
    op = CreateOperation(
        source=source,
        dest_root=dest_root,
        rel_path=rel_path,
        dry_run=False,
        force=False,
        formatter=formatter,
        context=context,
    )
    return op, formatter


# ---------------------------------------------------------------------------
# Rule 3 — ancestor symlink resolves into managed project → exit 0
# ---------------------------------------------------------------------------


class TestRule3ManagedSymlink:
    """Ancestor symlink resolves into the managed project — already managed."""

    def test_managed_ancestor_returns_0(self, tmp_path: Path) -> None:
        """_validate returns 0 when an ancestor symlink resolves into dest_root.

        Requirements: 6.1
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        # Create the real directory inside the managed project
        real_dir = dest_root / ".kiro"
        real_dir.mkdir()

        # Create a symlink at cwd/.kiro → managed/.kiro
        symlink_dir = cwd / ".kiro"
        symlink_dir.symlink_to(real_dir)

        # Source is a real file under the symlinked ancestor
        source = cwd / ".kiro" / "specs" / "foo.txt"
        # source doesn't need to exist for Rule 3 to fire — but Rule 1 runs first.
        # Create the real file via the managed path so source.exists() is True.
        (real_dir / "specs").mkdir()
        (real_dir / "specs" / "foo.txt").write_text("data")

        rel_path = Path(".kiro/specs/foo.txt")
        context = _make_context(cwd, dest_root, subpaths=[".kiro/specs/foo.txt"])
        op, _ = _make_operation(source, dest_root, rel_path, context)

        result = op._validate(dest_root / rel_path)

        assert result == 0

    def test_managed_ancestor_emits_info_message(self, tmp_path: Path) -> None:
        """formatter.info is called with the managed-symlink message.

        Requirements: 6.1
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        real_dir = dest_root / ".kiro"
        real_dir.mkdir()
        symlink_dir = cwd / ".kiro"
        symlink_dir.symlink_to(real_dir)

        (real_dir / "specs").mkdir()
        (real_dir / "specs" / "foo.txt").write_text("data")

        rel_path = Path(".kiro/specs/foo.txt")
        context = _make_context(cwd, dest_root, subpaths=[".kiro/specs/foo.txt"])
        op, formatter = _make_operation(
            source=cwd / ".kiro" / "specs" / "foo.txt",
            dest_root=dest_root,
            rel_path=rel_path,
            context=context,
        )

        op._validate(dest_root / rel_path)

        formatter.info.assert_called_once()
        msg = formatter.info.call_args[0][0]
        assert "managed symlink" in msg
        assert "Nothing to do" in msg

    def test_managed_ancestor_message_contains_anc_and_rel_path(self, tmp_path: Path) -> None:
        """The info message includes the ancestor name and the rel_path.

        Requirements: 6.1
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        real_dir = dest_root / ".kiro"
        real_dir.mkdir()
        (cwd / ".kiro").symlink_to(real_dir)

        (real_dir / "specs").mkdir()
        (real_dir / "specs" / "foo.txt").write_text("data")

        rel_path = Path(".kiro/specs/foo.txt")
        context = _make_context(cwd, dest_root, subpaths=[".kiro/specs/foo.txt"])
        op, formatter = _make_operation(cwd / ".kiro" / "specs" / "foo.txt", dest_root, rel_path, context)

        op._validate(dest_root / rel_path)

        msg = formatter.info.call_args[0][0]
        assert ".kiro" in msg
        assert ".kiro/specs/foo.txt" in msg

    def test_managed_ancestor_does_not_call_error(self, tmp_path: Path) -> None:
        """formatter.error is never called when the ancestor is a managed symlink.

        Requirements: 6.1
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        real_dir = dest_root / ".kiro"
        real_dir.mkdir()
        (cwd / ".kiro").symlink_to(real_dir)

        (real_dir / "specs").mkdir()
        (real_dir / "specs" / "foo.txt").write_text("data")

        rel_path = Path(".kiro/specs/foo.txt")
        context = _make_context(cwd, dest_root, subpaths=[".kiro/specs/foo.txt"])
        op, formatter = _make_operation(cwd / ".kiro" / "specs" / "foo.txt", dest_root, rel_path, context)

        op._validate(dest_root / rel_path)

        formatter.error.assert_not_called()


# ---------------------------------------------------------------------------
# Rule 3 — ancestor symlink resolves outside managed project → exit 1
# ---------------------------------------------------------------------------


class TestRule3ForeignSymlink:
    """Ancestor symlink resolves outside the managed project — unmanaged."""

    def test_foreign_ancestor_returns_1(self, tmp_path: Path) -> None:
        """_validate returns 1 when an ancestor symlink resolves outside dest_root.

        Requirements: 6.2
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        # A directory that is NOT inside dest_root
        foreign_dir = tmp_path / "foreign"
        foreign_dir.mkdir()
        (foreign_dir / "specs").mkdir()
        (foreign_dir / "specs" / "foo.txt").write_text("data")

        # Symlink at cwd/.kiro → foreign (outside managed project)
        (cwd / ".kiro").symlink_to(foreign_dir)

        rel_path = Path(".kiro/specs/foo.txt")
        context = _make_context(cwd, dest_root, subpaths=[".kiro/specs/foo.txt"])
        op, _ = _make_operation(cwd / ".kiro" / "specs" / "foo.txt", dest_root, rel_path, context)

        result = op._validate(dest_root / rel_path)

        assert result == 1

    def test_foreign_ancestor_emits_error_message(self, tmp_path: Path) -> None:
        """formatter.error is called with the unmanaged-symlink message.

        Requirements: 6.2
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        foreign_dir = tmp_path / "foreign"
        foreign_dir.mkdir()
        (foreign_dir / "specs").mkdir()
        (foreign_dir / "specs" / "foo.txt").write_text("data")
        (cwd / ".kiro").symlink_to(foreign_dir)

        rel_path = Path(".kiro/specs/foo.txt")
        context = _make_context(cwd, dest_root, subpaths=[".kiro/specs/foo.txt"])
        op, formatter = _make_operation(cwd / ".kiro" / "specs" / "foo.txt", dest_root, rel_path, context)

        op._validate(dest_root / rel_path)

        formatter.error.assert_called_once()
        msg = formatter.error.call_args[0][0]
        assert "not managed by blf" in msg
        assert "unmanaged symlink" in msg

    def test_foreign_ancestor_message_contains_anc(self, tmp_path: Path) -> None:
        """The error message includes the ancestor directory name.

        Requirements: 6.2
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        foreign_dir = tmp_path / "foreign"
        foreign_dir.mkdir()
        (foreign_dir / "specs").mkdir()
        (foreign_dir / "specs" / "foo.txt").write_text("data")
        (cwd / ".kiro").symlink_to(foreign_dir)

        rel_path = Path(".kiro/specs/foo.txt")
        context = _make_context(cwd, dest_root, subpaths=[".kiro/specs/foo.txt"])
        op, formatter = _make_operation(cwd / ".kiro" / "specs" / "foo.txt", dest_root, rel_path, context)

        op._validate(dest_root / rel_path)

        msg = formatter.error.call_args[0][0]
        assert ".kiro" in msg

    def test_foreign_ancestor_does_not_call_info(self, tmp_path: Path) -> None:
        """formatter.info is never called when the ancestor is a foreign symlink.

        Requirements: 6.2
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        foreign_dir = tmp_path / "foreign"
        foreign_dir.mkdir()
        (foreign_dir / "specs").mkdir()
        (foreign_dir / "specs" / "foo.txt").write_text("data")
        (cwd / ".kiro").symlink_to(foreign_dir)

        rel_path = Path(".kiro/specs/foo.txt")
        context = _make_context(cwd, dest_root, subpaths=[".kiro/specs/foo.txt"])
        op, formatter = _make_operation(cwd / ".kiro" / "specs" / "foo.txt", dest_root, rel_path, context)

        op._validate(dest_root / rel_path)

        formatter.info.assert_not_called()


# ---------------------------------------------------------------------------
# Rule 3 — no ancestor symlink → Rule 3 has no effect, validation continues
# ---------------------------------------------------------------------------


class TestRule3NoSymlink:
    """No ancestor symlink — Rule 3 is a no-op and validation continues."""

    def test_no_symlink_ancestor_does_not_return_early(self, tmp_path: Path) -> None:
        """When no ancestor is a symlink, _validate does not return 0 or 1 from Rule 3.

        Validation continues to Rule 6 (dest-exists check). With no dest and
        no force, Rule 6 passes and _validate returns 0.

        Requirements: 6.3
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        # Real directory hierarchy — no symlinks
        (cwd / ".kiro" / "specs").mkdir(parents=True)
        source = cwd / ".kiro" / "specs" / "foo.txt"
        source.write_text("data")

        rel_path = Path(".kiro/specs/foo.txt")
        context = _make_context(cwd, dest_root, subpaths=[])
        op, formatter = _make_operation(source, dest_root, rel_path, context)

        result = op._validate(dest_root / rel_path)

        # Rule 3 did not fire — no info or error from it
        formatter.info.assert_not_called()
        # Rule 6 passes (dest does not exist) → overall result is 0
        assert result == 0

    def test_no_symlink_ancestor_info_not_called(self, tmp_path: Path) -> None:
        """formatter.info is not called when no ancestor is a symlink.

        Requirements: 6.3
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        (cwd / ".kiro" / "specs").mkdir(parents=True)
        source = cwd / ".kiro" / "specs" / "foo.txt"
        source.write_text("data")

        rel_path = Path(".kiro/specs/foo.txt")
        context = _make_context(cwd, dest_root, subpaths=[])
        op, formatter = _make_operation(source, dest_root, rel_path, context)

        op._validate(dest_root / rel_path)

        formatter.info.assert_not_called()

    def test_direct_child_rel_path_has_no_ancestors_to_check(self, tmp_path: Path) -> None:
        """A single-component rel_path has no ancestor directories — Rule 3 is a no-op.

        Requirements: 6.3
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        source = cwd / "foo.txt"
        source.write_text("data")

        rel_path = Path("foo.txt")
        context = _make_context(cwd, dest_root, subpaths=[])
        op, formatter = _make_operation(source, dest_root, rel_path, context)

        result = op._validate(dest_root / rel_path)

        formatter.info.assert_not_called()
        assert result == 0


# ---------------------------------------------------------------------------
# Rule 3 — context is None → Rule 3 is skipped entirely
# ---------------------------------------------------------------------------


class TestRule3ContextNone:
    """When context is None, Rule 3 is skipped regardless of filesystem state."""

    def test_context_none_skips_rule3_with_symlink_present(self, tmp_path: Path) -> None:
        """Rule 3 is not evaluated when context is None, even if a symlink exists.

        Requirements: 6.4
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        # Create a foreign symlink that would trigger Rule 3 if context were set
        foreign_dir = tmp_path / "foreign"
        foreign_dir.mkdir()
        (foreign_dir / "specs").mkdir()
        (foreign_dir / "specs" / "foo.txt").write_text("data")
        (cwd / ".kiro").symlink_to(foreign_dir)

        rel_path = Path(".kiro/specs/foo.txt")
        # context=None — Rule 3 must be skipped
        op, formatter = _make_operation(cwd / ".kiro" / "specs" / "foo.txt", dest_root, rel_path, context=None)

        # Rule 1 (source exists) passes because the file exists through the symlink.
        # Rule 2 (not a symlink) passes because the file itself is not a symlink.
        # Rule 3 is skipped.
        # Rule 4 and 5 are also skipped (context is None).
        # Rule 6: dest does not exist → passes.
        result = op._validate(dest_root / rel_path)

        assert result == 0
        formatter.info.assert_not_called()
        formatter.error.assert_not_called()

    def test_context_none_skips_rule3_no_symlink(self, tmp_path: Path) -> None:
        """Rule 3 is skipped when context is None and no symlinks exist.

        Requirements: 6.4
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        (cwd / ".kiro" / "specs").mkdir(parents=True)
        source = cwd / ".kiro" / "specs" / "foo.txt"
        source.write_text("data")

        rel_path = Path(".kiro/specs/foo.txt")
        op, formatter = _make_operation(source, dest_root, rel_path, context=None)

        result = op._validate(dest_root / rel_path)

        assert result == 0
        formatter.info.assert_not_called()
        formatter.error.assert_not_called()

    def test_context_none_does_not_raise(self, tmp_path: Path) -> None:
        """_validate does not raise when context is None.

        Requirements: 6.4
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        source = cwd / "foo.txt"
        source.write_text("data")

        rel_path = Path("foo.txt")
        op, _ = _make_operation(source, dest_root, rel_path, context=None)

        # Must not raise AttributeError or any other exception
        result = op._validate(dest_root / rel_path)
        assert result == 0
