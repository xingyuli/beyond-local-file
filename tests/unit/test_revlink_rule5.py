"""Unit tests for CreateOperation._validate — Rule 5 (selective sync subpath conflicts).

Covers task 6.3:
- Test 5a (copy exists): declared ancestor subpath, managed copy present → exit 1
- Test 5a (copy missing): declared ancestor subpath, managed copy absent → exit 1
- Test 5b: rel_path is ancestor of declared subpath → exit 1
- Test: no conflict → Rule 5 has no effect, validation continues
- Test: context is None → Rule 5 is skipped entirely

Requirements: 8 (Requirement 8 in requirements.md — Selective Sync Mapping Subpath Conflict Detection)
"""

from pathlib import Path
from unittest.mock import MagicMock

from beyond_local_file.model.config import Mapping
from beyond_local_file.operations.revlink import CreateFormatter, CreateOperation, RevlinkContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_operation(
    source: Path,
    dest_root: Path,
    rel_path: Path,
    *,
    context: RevlinkContext | None = None,
    force: bool = False,
) -> tuple[CreateOperation, MagicMock]:
    """Build a CreateOperation with a mock formatter.

    Args:
        source: Source path for the operation.
        dest_root: Destination root (managed project path).
        rel_path: Relative path from CWD to source.
        context: Optional RevlinkContext for config-aware validation.
        force: Whether to enable force mode.

    Returns:
        Tuple of (CreateOperation, mock formatter).
    """
    formatter = MagicMock(spec=CreateFormatter)
    op = CreateOperation(
        source=source,
        dest_root=dest_root,
        rel_path=rel_path,
        dry_run=False,
        force=force,
        formatter=formatter,
        context=context,
    )
    return op, formatter


def _make_context(
    cwd: Path,
    dest_root: Path,
    subpaths: list[str],
    config_path: Path | None = None,
) -> RevlinkContext:
    """Build a RevlinkContext with a selective sync mapping.

    Args:
        cwd: Current working directory.
        dest_root: Managed project path (used as a target placeholder).
        subpaths: Declared subpath list for the mapping.
        config_path: Path to the config file; defaults to cwd / 'blf.yaml'.

    Returns:
        A RevlinkContext with a selective sync Mapping.
    """
    mapping = Mapping(targets=[cwd], subpaths=subpaths, copy_paths=None)
    return RevlinkContext(
        config_path=config_path or (cwd / "blf.yaml"),
        project_name="test-project",
        matched_mapping=mapping,
        cwd=cwd,
    )


# ---------------------------------------------------------------------------
# Rule 5a — declared subpath is ancestor of (or equal to) rel_path
# ---------------------------------------------------------------------------


class TestRule5aDeclaredAncestorCopyExists:
    """Rule 5a: declared ancestor subpath, managed copy already present → exit 1."""

    def test_exact_match_copy_exists_returns_1(self, tmp_path: Path) -> None:
        """Declared subpath equals rel_path and managed copy exists → exit 1.

        Requirements: 8.1
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        # Source file exists (passes Rules 1 and 2)
        source = cwd / "notes.txt"
        source.write_text("hello")

        rel_path = Path("notes.txt")

        # Managed copy already exists at dest_root / rel_path
        managed_copy = dest_root / rel_path
        managed_copy.write_text("hello")

        context = _make_context(cwd, dest_root, subpaths=["notes.txt"])
        op, formatter = _make_operation(source, dest_root, rel_path, context=context)

        result = op._validate(dest_root / rel_path)

        assert result == 1
        formatter.error.assert_called_once()
        msg = formatter.error.call_args[0][0]
        assert "notes.txt" in msg
        assert "blf link sync" in msg
        assert str(managed_copy) in msg

    def test_ancestor_subpath_copy_exists_returns_1(self, tmp_path: Path) -> None:
        """Declared subpath is ancestor of rel_path and managed copy exists → exit 1.

        Requirements: 8.1
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        # Source is a nested file under the declared subpath
        source_dir = cwd / "docs" / "api"
        source_dir.mkdir(parents=True)
        source = source_dir / "reference.md"
        source.write_text("api docs")

        rel_path = Path("docs/api/reference.md")

        # Managed copy exists at dest_root / rel_path
        managed_copy = dest_root / rel_path
        managed_copy.parent.mkdir(parents=True)
        managed_copy.write_text("api docs")

        # Declared subpath "docs" is an ancestor of "docs/api/reference.md"
        context = _make_context(cwd, dest_root, subpaths=["docs"])
        op, formatter = _make_operation(source, dest_root, rel_path, context=context)

        result = op._validate(dest_root / rel_path)

        assert result == 1
        formatter.error.assert_called_once()
        msg = formatter.error.call_args[0][0]
        assert "docs" in msg
        assert "blf link sync" in msg

    def test_error_message_contains_managed_copy_path(self, tmp_path: Path) -> None:
        """Error message for 5a (copy exists) includes the managed copy path.

        Requirements: 8.1
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        source = cwd / "config.yaml"
        source.write_text("key: value")

        rel_path = Path("config.yaml")
        managed_copy = dest_root / rel_path
        managed_copy.write_text("key: value")

        context = _make_context(cwd, dest_root, subpaths=["config.yaml"])
        op, formatter = _make_operation(source, dest_root, rel_path, context=context)

        op._validate(dest_root / rel_path)

        msg = formatter.error.call_args[0][0]
        assert str(managed_copy) in msg
        assert "already exists" in msg


class TestRule5aDeclaredAncestorCopyMissing:
    """Rule 5a: declared ancestor subpath, managed copy absent → exit 1."""

    def test_exact_match_copy_missing_returns_1(self, tmp_path: Path) -> None:
        """Declared subpath equals rel_path but managed copy is absent → exit 1.

        Requirements: 8.2
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        source = cwd / "notes.txt"
        source.write_text("hello")

        rel_path = Path("notes.txt")
        # No managed copy created — dest_root / rel_path does not exist

        context = _make_context(cwd, dest_root, subpaths=["notes.txt"])
        op, formatter = _make_operation(source, dest_root, rel_path, context=context)

        result = op._validate(dest_root / rel_path)

        assert result == 1
        formatter.error.assert_called_once()
        msg = formatter.error.call_args[0][0]
        assert "notes.txt" in msg
        assert "blf link sync" in msg

    def test_ancestor_subpath_copy_missing_returns_1(self, tmp_path: Path) -> None:
        """Declared subpath is ancestor of rel_path and managed copy is absent → exit 1.

        Requirements: 8.2
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        source_dir = cwd / "src" / "utils"
        source_dir.mkdir(parents=True)
        source = source_dir / "helpers.py"
        source.write_text("# helpers")

        rel_path = Path("src/utils/helpers.py")
        # No managed copy — dest_root / rel_path does not exist

        # Declared subpath "src" is an ancestor of "src/utils/helpers.py"
        context = _make_context(cwd, dest_root, subpaths=["src"])
        op, formatter = _make_operation(source, dest_root, rel_path, context=context)

        result = op._validate(dest_root / rel_path)

        assert result == 1
        formatter.error.assert_called_once()
        msg = formatter.error.call_args[0][0]
        assert "src" in msg

    def test_error_message_copy_missing_contains_source_and_managed_copy(self, tmp_path: Path) -> None:
        """Error message for 5a (copy missing) includes source and managed copy paths.

        Requirements: 8.2
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        source = cwd / "data.json"
        source.write_text("{}")

        rel_path = Path("data.json")
        managed_copy = dest_root / rel_path
        # managed_copy does NOT exist

        context = _make_context(cwd, dest_root, subpaths=["data.json"])
        op, formatter = _make_operation(source, dest_root, rel_path, context=context)

        op._validate(dest_root / rel_path)

        msg = formatter.error.call_args[0][0]
        assert str(source) in msg
        assert str(managed_copy) in msg
        assert "manually" in msg

    def test_copy_missing_message_does_not_mention_already_exists(self, tmp_path: Path) -> None:
        """The 'copy missing' error message does not say 'already exists'.

        Distinguishes the two 5a variants by their message content.

        Requirements: 8.2
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        source = cwd / "readme.md"
        source.write_text("# readme")

        rel_path = Path("readme.md")

        context = _make_context(cwd, dest_root, subpaths=["readme.md"])
        op, formatter = _make_operation(source, dest_root, rel_path, context=context)

        op._validate(dest_root / rel_path)

        msg = formatter.error.call_args[0][0]
        assert "already exists" not in msg


# ---------------------------------------------------------------------------
# Rule 5b — rel_path is ancestor of a declared subpath (reverse conflict)
# ---------------------------------------------------------------------------


class TestRule5bReverseConflict:
    """Rule 5b: rel_path is ancestor of a declared subpath → exit 1."""

    def test_rel_path_ancestor_of_declared_returns_1(self, tmp_path: Path) -> None:
        """rel_path is a parent of a declared subpath → exit 1.

        Requirements: 8.3
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        # Source is "docs" directory; declared subpath is "docs/api" (narrower)
        source = cwd / "docs"
        source.mkdir()
        (source / "index.md").write_text("index")

        rel_path = Path("docs")

        context = _make_context(cwd, dest_root, subpaths=["docs/api"])
        op, formatter = _make_operation(source, dest_root, rel_path, context=context)

        result = op._validate(dest_root / rel_path)

        assert result == 1
        formatter.error.assert_called_once()
        msg = formatter.error.call_args[0][0]
        assert "docs/api" in msg
        assert "docs" in msg

    def test_reverse_conflict_error_message_content(self, tmp_path: Path) -> None:
        """Rule 5b error message mentions declared subpath, rel_path, and removal guidance.

        Requirements: 8.3
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        source = cwd / ".kiro"
        source.mkdir()

        rel_path = Path(".kiro")

        context = _make_context(cwd, dest_root, subpaths=[".kiro/specs"])
        op, formatter = _make_operation(source, dest_root, rel_path, context=context)

        op._validate(dest_root / rel_path)

        msg = formatter.error.call_args[0][0]
        assert ".kiro/specs" in msg
        assert ".kiro" in msg
        assert "conflict" in msg.lower() or "Remove" in msg

    def test_reverse_conflict_with_multiple_subpaths_first_match_wins(self, tmp_path: Path) -> None:
        """When multiple declared subpaths exist, the first reverse conflict triggers exit 1.

        Requirements: 8.3
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        source = cwd / "src"
        source.mkdir()

        rel_path = Path("src")

        # Two declared subpaths under "src"
        context = _make_context(cwd, dest_root, subpaths=["src/lib", "src/tests"])
        op, formatter = _make_operation(source, dest_root, rel_path, context=context)

        result = op._validate(dest_root / rel_path)

        assert result == 1
        # Only one error call — stops at first conflict
        assert formatter.error.call_count == 1

    def test_equal_path_is_not_reverse_conflict(self, tmp_path: Path) -> None:
        """When rel_path equals declared subpath, it is 5a (not 5b).

        The 5b condition requires declared_path != rel_path.

        Requirements: 8.3
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        source = cwd / "docs"
        source.mkdir()
        (source / "readme.md").write_text("docs")

        rel_path = Path("docs")

        # Declared subpath equals rel_path — this is 5a, not 5b
        # No managed copy exists → 5a (copy missing) fires
        context = _make_context(cwd, dest_root, subpaths=["docs"])
        op, formatter = _make_operation(source, dest_root, rel_path, context=context)

        result = op._validate(dest_root / rel_path)

        assert result == 1
        msg = formatter.error.call_args[0][0]
        # 5a message (copy missing) — not the 5b "conflict" message
        assert "conflict" not in msg.lower() or "Remove" not in msg


# ---------------------------------------------------------------------------
# Rule 5 — no conflict → validation continues
# ---------------------------------------------------------------------------


class TestRule5NoConflict:
    """Rule 5 has no effect when no declared subpath conflicts with rel_path."""

    def test_unrelated_subpath_passes_rule5(self, tmp_path: Path) -> None:
        """Declared subpath is unrelated to rel_path → Rule 5 passes, Rule 6 checked.

        Requirements: 8.4
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        source = cwd / "readme.md"
        source.write_text("readme")

        rel_path = Path("readme.md")

        # Declared subpath "docs" is unrelated to "readme.md"
        context = _make_context(cwd, dest_root, subpaths=["docs"])
        op, formatter = _make_operation(source, dest_root, rel_path, context=context)

        # dest does not exist → Rule 6 passes too → overall exit 0
        result = op._validate(dest_root / rel_path)

        assert result == 0
        formatter.error.assert_not_called()

    def test_empty_subpath_list_passes_rule5(self, tmp_path: Path) -> None:
        """Empty declared subpath list → Rule 5 loop body never executes → passes.

        Requirements: 8.4
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        source = cwd / "file.txt"
        source.write_text("data")

        rel_path = Path("file.txt")

        context = _make_context(cwd, dest_root, subpaths=[])
        op, formatter = _make_operation(source, dest_root, rel_path, context=context)

        result = op._validate(dest_root / rel_path)

        assert result == 0
        formatter.error.assert_not_called()

    def test_sibling_subpath_does_not_conflict(self, tmp_path: Path) -> None:
        """A declared subpath that is a sibling (not ancestor/descendant) does not conflict.

        Requirements: 8.4
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        source = cwd / "docs" / "guide.md"
        source.parent.mkdir(parents=True)
        source.write_text("guide")

        rel_path = Path("docs/guide.md")

        # "docs/api" is a sibling of "docs/guide.md" — no ancestor relationship
        context = _make_context(cwd, dest_root, subpaths=["docs/api"])
        op, formatter = _make_operation(source, dest_root, rel_path, context=context)

        result = op._validate(dest_root / rel_path)

        assert result == 0
        formatter.error.assert_not_called()


# ---------------------------------------------------------------------------
# Rule 5 — context is None → Rule 5 is skipped entirely
# ---------------------------------------------------------------------------


class TestRule5ContextNone:
    """Rule 5 is skipped entirely when context is None."""

    def test_no_context_skips_rule5_and_proceeds_to_rule6(self, tmp_path: Path) -> None:
        """When context is None, Rule 5 is not evaluated; Rule 6 is checked instead.

        Requirements: 8.5
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        source = cwd / "file.txt"
        source.write_text("data")

        rel_path = Path("file.txt")

        # No context — Rule 5 must be skipped
        op, formatter = _make_operation(source, dest_root, rel_path, context=None)

        # dest does not exist → Rule 6 passes → overall exit 0
        result = op._validate(dest_root / rel_path)

        assert result == 0
        formatter.error.assert_not_called()

    def test_no_context_rule6_still_fires(self, tmp_path: Path) -> None:
        """When context is None, Rule 6 (dest exists) still fires after Rule 5 is skipped.

        Requirements: 8.5
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        source = cwd / "file.txt"
        source.write_text("data")

        rel_path = Path("file.txt")

        # Create the dest so Rule 6 fires
        dest = dest_root / rel_path
        dest.write_text("existing")

        op, formatter = _make_operation(source, dest_root, rel_path, context=None)

        result = op._validate(dest)

        # Rule 6 fires (dest exists, no --force)
        assert result == 1
        formatter.error.assert_called_once()
        msg = formatter.error.call_args[0][0]
        assert "Destination already exists" in msg

    def test_no_context_no_subpath_conflict_check(self, tmp_path: Path) -> None:
        """With context=None, no subpath conflict check is performed even if subpaths exist.

        This verifies the skip is unconditional when context is None.

        Requirements: 8.5
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        source = cwd / "notes.txt"
        source.write_text("notes")

        rel_path = Path("notes.txt")

        # Even though a managed copy exists, without context Rule 5 is skipped
        managed_copy = dest_root / rel_path
        managed_copy.write_text("notes")

        # No context — Rule 5 cannot fire; Rule 6 fires instead
        op, formatter = _make_operation(source, dest_root, rel_path, context=None)

        result = op._validate(managed_copy)

        # Rule 6 fires (dest exists, no --force) — not a Rule 5 error
        assert result == 1
        msg = formatter.error.call_args[0][0]
        assert "Destination already exists" in msg
