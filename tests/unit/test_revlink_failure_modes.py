"""Unit tests for CreateOperation failure modes.

Covers:
- MD5 mismatch: failed copy is deleted, source is untouched, exit code 1
- Copy-only create leaves the target path as a regular file

Requirements: 4.3, 4.4
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from beyond_local_file.operations.revlink import ChecksumVerifier, CreateFormatter, CreateOperation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_operation(
    source: Path,
    dest_root: Path,
    *,
    force: bool = False,
) -> tuple[CreateOperation, MagicMock]:
    """Build a CreateOperation with a mock formatter.

    Args:
        source: Source path for the operation.
        dest_root: Destination root for the operation.
        force: Whether to enable force mode.

    Returns:
        Tuple of (CreateOperation, mock formatter).
    """
    formatter = MagicMock(spec=CreateFormatter)
    op = CreateOperation(
        source=source,
        dest_root=dest_root,
        rel_path=Path(source.name),
        dry_run=False,
        force=force,
        formatter=formatter,
    )
    return op, formatter


# ---------------------------------------------------------------------------
# Requirement 4.3, 4.4 — MD5 mismatch recovery
# ---------------------------------------------------------------------------


class TestMd5MismatchRecovery:
    """Tests for _verify() when checksums do not match."""

    def test_mismatch_deletes_copy_and_returns_1(self, tmp_path: Path) -> None:
        """Failed copy is deleted and exit code 1 is returned on checksum mismatch.

        Requirements: 4.3, 4.4
        """
        source = tmp_path / "source.txt"
        source.write_text("original")
        dest_root = tmp_path / "managed"
        dest_root.mkdir()
        dest = dest_root / "source.txt"
        dest.write_text("copy")  # dest exists so _verify can delete it

        op, _formatter = _make_operation(source, dest_root)

        # Return different digests to simulate a corrupt copy
        with patch.object(ChecksumVerifier, "compute", side_effect=["aaa", "bbb"]):
            result = op._verify(dest)

        assert result == 1
        assert not dest.exists(), "corrupt copy must be deleted on mismatch"

    def test_mismatch_leaves_source_untouched(self, tmp_path: Path) -> None:
        """Source file is not modified when checksum mismatch is detected.

        Requirements: 4.4
        """
        source = tmp_path / "source.txt"
        source.write_text("original content")
        dest_root = tmp_path / "managed"
        dest_root.mkdir()
        dest = dest_root / "source.txt"
        dest.write_text("copy")

        op, _ = _make_operation(source, dest_root)

        with patch.object(ChecksumVerifier, "compute", side_effect=["aaa", "bbb"]):
            op._verify(dest)

        assert source.exists(), "source must still exist after mismatch"
        assert source.read_text() == "original content", "source content must be unchanged"

    def test_mismatch_emits_error_message(self, tmp_path: Path) -> None:
        """formatter.error is called with the checksum-mismatch message.

        Requirements: 4.3
        """
        source = tmp_path / "source.txt"
        source.write_text("original")
        dest_root = tmp_path / "managed"
        dest_root.mkdir()
        dest = dest_root / "source.txt"
        dest.write_text("copy")

        op, formatter = _make_operation(source, dest_root)

        with patch.object(ChecksumVerifier, "compute", side_effect=["aaa", "bbb"]):
            op._verify(dest)

        formatter.error.assert_called_once()
        error_msg = formatter.error.call_args[0][0]
        assert "mismatch" in error_msg.lower() or "checksum" in error_msg.lower()

    def test_mismatch_on_directory_deletes_copy_tree(self, tmp_path: Path) -> None:
        """A directory copy is removed (not just unlinked) on checksum mismatch.

        Requirements: 4.4
        """
        source = tmp_path / "srcdir"
        source.mkdir()
        (source / "file.txt").write_text("data")
        dest_root = tmp_path / "managed"
        dest_root.mkdir()
        dest = dest_root / "srcdir"
        dest.mkdir()
        (dest / "file.txt").write_text("data")

        op, _ = _make_operation(source, dest_root)

        with patch.object(ChecksumVerifier, "compute", side_effect=["aaa", "bbb"]):
            result = op._verify(dest)

        assert result == 1
        assert not dest.exists(), "corrupt directory copy must be deleted on mismatch"


# ---------------------------------------------------------------------------
# Copy-only create leaves the target path in place
# ---------------------------------------------------------------------------


class TestCreateLeavesTargetInPlace:
    """Create no longer replaces the source with a symlink."""

    def test_run_leaves_regular_file(self, tmp_path: Path) -> None:
        """run() keeps the source as a regular file and reports it left in place."""
        source = tmp_path / "source.txt"
        source.write_text("data")
        dest_root = tmp_path / "managed"
        dest_root.mkdir()

        op, formatter = _make_operation(source, dest_root)
        result = op.run()

        assert result == 0
        assert source.is_file()
        assert not source.is_symlink()
        assert source.read_text() == "data"
        assert (dest_root / "source.txt").read_text() == "data"
        formatter.target_left_in_place.assert_called_once_with(source)
