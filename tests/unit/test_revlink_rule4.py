"""Unit tests for CreateOperation._validate Rule 4 (sync-all + nested path).

Covers task 6.2:
- sync-all mapping + rel_path with 2 parts → exit 1 with error message
- sync-all mapping + rel_path with 1 part → Rule 4 has no effect
- context is None → Rule 4 is skipped entirely

Requirements: 6 (Requirement 7 in requirements.md)
"""

from pathlib import Path
from unittest.mock import MagicMock

from beyond_local_file.model.config import Mapping
from beyond_local_file.operations.revlink import CreateFormatter, CreateOperation, RevlinkContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RULE4_ERROR_FRAGMENT = "is a nested path. This mapping uses sync-all"


def _make_sync_all_context(cwd: Path, dest_root: Path) -> RevlinkContext:
    """Build a RevlinkContext whose matched_mapping is a sync-all mapping.

    A sync-all mapping has ``subpaths=None``.

    Args:
        cwd: The current working directory to embed in the context.
        dest_root: The managed project path (used as the config path parent).

    Returns:
        A ``RevlinkContext`` with a sync-all ``Mapping``.
    """
    mapping = Mapping(targets=[cwd], subpaths=None, copy_paths=None)
    return RevlinkContext(
        config_path=dest_root / "config.yaml",
        project_name="test-project",
        matched_mapping=mapping,
        cwd=cwd,
    )


def _make_operation(
    source: Path,
    dest_root: Path,
    rel_path: Path,
    *,
    context: RevlinkContext | None = None,
) -> tuple[CreateOperation, MagicMock]:
    """Build a CreateOperation with a mock formatter.

    Args:
        source: Source path for the operation.
        dest_root: Destination root for the operation.
        rel_path: Relative path from CWD to source.
        context: Optional RevlinkContext; ``None`` skips config-aware rules.

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
# Rule 4 — sync-all mapping rejects nested paths
# ---------------------------------------------------------------------------


class TestRule4SyncAllNestedPath:
    """Tests for Rule 4: sync-all mapping + nested rel_path → exit 1."""

    def test_nested_rel_path_returns_exit_1(self, tmp_path: Path) -> None:
        """sync-all mapping with a 2-part rel_path exits with code 1.

        Requirements: 7.1
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        # Source is a real file so Rules 1 and 2 pass
        nested_dir = cwd / "subdir"
        nested_dir.mkdir()
        source = nested_dir / "file.txt"
        source.write_text("data")

        rel_path = Path("subdir/file.txt")
        context = _make_sync_all_context(cwd, dest_root)
        op, _ = _make_operation(source, dest_root, rel_path, context=context)

        result = op._validate(dest_root / rel_path)

        assert result == 1

    def test_nested_rel_path_emits_error_message(self, tmp_path: Path) -> None:
        """sync-all mapping with a nested rel_path emits the Rule 4 error message.

        Requirements: 7.1
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        nested_dir = cwd / "subdir"
        nested_dir.mkdir()
        source = nested_dir / "file.txt"
        source.write_text("data")

        rel_path = Path("subdir/file.txt")
        context = _make_sync_all_context(cwd, dest_root)
        op, formatter = _make_operation(source, dest_root, rel_path, context=context)

        op._validate(dest_root / rel_path)

        formatter.error.assert_called_once()
        error_msg = formatter.error.call_args[0][0]
        assert _RULE4_ERROR_FRAGMENT in error_msg

    def test_nested_rel_path_error_message_contains_rel_path(self, tmp_path: Path) -> None:
        """The Rule 4 error message includes the rel_path value.

        Requirements: 7.1
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        nested_dir = cwd / "subdir"
        nested_dir.mkdir()
        source = nested_dir / "file.txt"
        source.write_text("data")

        rel_path = Path("subdir/file.txt")
        context = _make_sync_all_context(cwd, dest_root)
        op, formatter = _make_operation(source, dest_root, rel_path, context=context)

        op._validate(dest_root / rel_path)

        error_msg = formatter.error.call_args[0][0]
        assert str(rel_path) in error_msg

    def test_deeply_nested_rel_path_returns_exit_1(self, tmp_path: Path) -> None:
        """sync-all mapping with a 3-part rel_path also exits with code 1.

        Requirements: 7.1
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        deep_dir = cwd / "a" / "b"
        deep_dir.mkdir(parents=True)
        source = deep_dir / "file.txt"
        source.write_text("data")

        rel_path = Path("a/b/file.txt")
        context = _make_sync_all_context(cwd, dest_root)
        op, _ = _make_operation(source, dest_root, rel_path, context=context)

        result = op._validate(dest_root / rel_path)

        assert result == 1


# ---------------------------------------------------------------------------
# Rule 4 — sync-all mapping allows top-level paths (1 part)
# ---------------------------------------------------------------------------


class TestRule4SyncAllTopLevelPath:
    """Tests for Rule 4: sync-all mapping + 1-part rel_path → Rule 4 has no effect."""

    def test_top_level_rel_path_rule4_has_no_effect(self, tmp_path: Path) -> None:
        """sync-all mapping with a 1-part rel_path does not trigger Rule 4.

        Validation continues past Rule 4 (exits 0 when dest does not exist).

        Requirements: 7.2
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        source = cwd / "file.txt"
        source.write_text("data")

        rel_path = Path("file.txt")
        context = _make_sync_all_context(cwd, dest_root)
        op, formatter = _make_operation(source, dest_root, rel_path, context=context)

        result = op._validate(dest_root / rel_path)

        # Rule 4 does not fire; dest does not exist so Rule 6 also passes → exit 0
        assert result == 0
        formatter.error.assert_not_called()

    def test_top_level_rel_path_no_rule4_error_emitted(self, tmp_path: Path) -> None:
        """No Rule 4 error message is emitted for a 1-part rel_path.

        Requirements: 7.2
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        source = cwd / "myfile.txt"
        source.write_text("data")

        rel_path = Path("myfile.txt")
        context = _make_sync_all_context(cwd, dest_root)
        op, formatter = _make_operation(source, dest_root, rel_path, context=context)

        op._validate(dest_root / rel_path)

        # Confirm the Rule 4 error fragment is absent from any error calls
        for call in formatter.error.call_args_list:
            assert _RULE4_ERROR_FRAGMENT not in call[0][0]


# ---------------------------------------------------------------------------
# Rule 4 — context is None → Rule 4 is skipped entirely
# ---------------------------------------------------------------------------


class TestRule4ContextNone:
    """Tests for Rule 4: context is None → Rule 4 is skipped entirely."""

    def test_no_context_nested_path_rule4_skipped(self, tmp_path: Path) -> None:
        """When context is None, Rule 4 is not evaluated even for nested rel_path.

        Validation continues past Rule 4 (exits 0 when dest does not exist).

        Requirements: 7.3
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        nested_dir = cwd / "subdir"
        nested_dir.mkdir()
        source = nested_dir / "file.txt"
        source.write_text("data")

        rel_path = Path("subdir/file.txt")
        # No context — Rule 4 must be skipped
        op, formatter = _make_operation(source, dest_root, rel_path, context=None)

        result = op._validate(dest_root / rel_path)

        # Rule 4 is skipped; dest does not exist so Rule 6 also passes → exit 0
        assert result == 0
        formatter.error.assert_not_called()

    def test_no_context_no_rule4_error_emitted(self, tmp_path: Path) -> None:
        """No Rule 4 error message is emitted when context is None.

        Requirements: 7.3
        """
        cwd = tmp_path / "target"
        cwd.mkdir()
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        nested_dir = cwd / "deep" / "path"
        nested_dir.mkdir(parents=True)
        source = nested_dir / "item.txt"
        source.write_text("data")

        rel_path = Path("deep/path/item.txt")
        op, formatter = _make_operation(source, dest_root, rel_path, context=None)

        op._validate(dest_root / rel_path)

        for call in formatter.error.call_args_list:
            assert _RULE4_ERROR_FRAGMENT not in call[0][0]
