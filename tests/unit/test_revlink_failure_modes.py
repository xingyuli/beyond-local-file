"""Unit tests for RevlinkOperation failure modes.

Covers task 7.2:
- MD5 mismatch: failed copy is deleted, source is untouched, exit code 1
- Permission error on remove: correct error message, no further changes
- Symlink creation failure: inconsistent-state error message, exit code 1

Requirements: 4.3, 4.4, 5.4, 5.5
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from beyond_local_file.operations.revlink import ChecksumVerifier, RevlinkFormatter, RevlinkOperation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_operation(
    source: Path,
    dest_root: Path,
    *,
    force: bool = False,
) -> tuple[RevlinkOperation, MagicMock]:
    """Build a RevlinkOperation with a mock formatter.

    Args:
        source: Source path for the operation.
        dest_root: Destination root for the operation.
        force: Whether to enable force mode.

    Returns:
        Tuple of (RevlinkOperation, mock formatter).
    """
    formatter = MagicMock(spec=RevlinkFormatter)
    op = RevlinkOperation(
        source=source,
        dest_root=dest_root,
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
# Requirement 5.4 — Permission error on remove
# ---------------------------------------------------------------------------


class TestPermissionErrorOnRemove:
    """Tests for _replace() when removing the source raises PermissionError."""

    def test_permission_error_returns_1(self, tmp_path: Path) -> None:
        """Exit code 1 is returned when source removal raises PermissionError.

        Requirements: 5.4
        """
        source = tmp_path / "source.txt"
        source.write_text("data")
        dest_root = tmp_path / "managed"
        dest_root.mkdir()
        dest = dest_root / "source.txt"

        op, _ = _make_operation(source, dest_root)

        with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
            result = op._replace(dest)

        assert result == 1

    def test_permission_error_emits_correct_message(self, tmp_path: Path) -> None:
        """formatter.error is called with a permission-denied message.

        Requirements: 5.4
        """
        source = tmp_path / "source.txt"
        source.write_text("data")
        dest_root = tmp_path / "managed"
        dest_root.mkdir()
        dest = dest_root / "source.txt"

        op, formatter = _make_operation(source, dest_root)

        with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
            op._replace(dest)

        formatter.error.assert_called_once()
        assert "Permission denied" in formatter.error.call_args[0][0]

    def test_permission_error_source_remains(self, tmp_path: Path) -> None:
        """Source file is left untouched when removal raises PermissionError.

        Requirements: 5.4
        """
        source = tmp_path / "source.txt"
        source.write_text("data")
        dest_root = tmp_path / "managed"
        dest_root.mkdir()
        dest = dest_root / "source.txt"

        op, _ = _make_operation(source, dest_root)

        with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
            op._replace(dest)

        assert source.exists(), "source must still exist after permission error"
        assert not source.is_symlink(), "source must not have been replaced"

    def test_permission_error_no_symlink_created(self, tmp_path: Path) -> None:
        """No symlink is created when source removal fails with PermissionError.

        Requirements: 5.4
        """
        source = tmp_path / "source.txt"
        source.write_text("data")
        dest_root = tmp_path / "managed"
        dest_root.mkdir()
        dest = dest_root / "source.txt"

        op, formatter = _make_operation(source, dest_root)

        with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
            op._replace(dest)

        # symlink_created must never be called
        formatter.symlink_created.assert_not_called()


# ---------------------------------------------------------------------------
# Requirement 5.5 — Symlink creation failure (inconsistent state)
# ---------------------------------------------------------------------------


class TestSymlinkCreationFailure:
    """Tests for _replace() when symlink_to raises OSError after source removal."""

    def test_symlink_failure_returns_1(self, tmp_path: Path) -> None:
        """Exit code 1 is returned when symlink creation raises OSError.

        Requirements: 5.5
        """
        source = tmp_path / "source.txt"
        source.write_text("data")
        dest_root = tmp_path / "managed"
        dest_root.mkdir()
        dest = dest_root / "source.txt"

        op, _ = _make_operation(source, dest_root)

        with patch.object(Path, "symlink_to", side_effect=OSError("no symlinks")):
            result = op._replace(dest)

        assert result == 1

    def test_symlink_failure_emits_inconsistent_state_message(self, tmp_path: Path) -> None:
        """formatter.error is called with an inconsistent-state warning.

        Requirements: 5.5
        """
        source = tmp_path / "source.txt"
        source.write_text("data")
        dest_root = tmp_path / "managed"
        dest_root.mkdir()
        dest = dest_root / "source.txt"

        op, formatter = _make_operation(source, dest_root)

        with patch.object(Path, "symlink_to", side_effect=OSError("no symlinks")):
            op._replace(dest)

        formatter.error.assert_called_once()
        error_msg = formatter.error.call_args[0][0]
        assert "inconsistent" in error_msg.lower() or "Failed to create symlink" in error_msg

    def test_symlink_failure_source_is_gone(self, tmp_path: Path) -> None:
        """Source has already been removed when symlink creation fails.

        This confirms the inconsistent-state scenario described in Requirement 5.5:
        the original was deleted but the symlink was not created.

        Requirements: 5.5
        """
        source = tmp_path / "source.txt"
        source.write_text("data")
        dest_root = tmp_path / "managed"
        dest_root.mkdir()
        dest = dest_root / "source.txt"

        op, _ = _make_operation(source, dest_root)

        with patch.object(Path, "symlink_to", side_effect=OSError("no symlinks")):
            op._replace(dest)

        # Source was removed before symlink_to was attempted
        assert not source.exists(), "source should have been removed before symlink_to failed"
