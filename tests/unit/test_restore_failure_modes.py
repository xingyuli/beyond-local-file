"""Unit tests for RestoreOperation failure modes.

Covers task 8.2:
- MD5 mismatch: restored copy deleted, managed copy preserved, exit code 1
- Permission error on symlink unlink: error message, no copy attempted, exit code 1
- Permission error deleting managed copy: warning emitted, exit code 0

Requirements: 4.2, 4.6, 5.2
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from beyond_local_file.operations.revlink import ChecksumVerifier, RestoreFormatter, RestoreOperation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_operation(
    source: Path,
    dest_root: Path,
) -> tuple[RestoreOperation, MagicMock]:
    """Build a RestoreOperation with a mock formatter.

    Args:
        source: Source path (the symlink in CWD) for the operation.
        dest_root: Destination root (managed project path) for the operation.

    Returns:
        Tuple of (RestoreOperation, mock formatter).
    """
    formatter = MagicMock(spec=RestoreFormatter)
    op = RestoreOperation(
        source=source,
        dest_root=dest_root,
        dry_run=False,
        formatter=formatter,
    )
    return op, formatter


def _make_symlink(link: Path, target: Path) -> None:
    """Create a symlink at *link* pointing to *target*.

    Args:
        link: Path where the symlink will be created.
        target: Path the symlink will point to.
    """
    link.symlink_to(target)


# ---------------------------------------------------------------------------
# Requirement 4.6 — MD5 mismatch recovery
# ---------------------------------------------------------------------------


class TestMd5MismatchRecovery:
    """Tests for _verify() when checksums do not match after restore."""

    def test_mismatch_deletes_restored_copy_and_returns_1(self, tmp_path: Path) -> None:
        """Restored copy is deleted and exit code 1 is returned on checksum mismatch.

        Requirements: 4.6
        """
        managed = tmp_path / "managed" / "data.txt"
        managed.parent.mkdir()
        managed.write_text("managed content")

        # source is the restored copy location (not a symlink at this point —
        # _verify is called after _replace has already written the file back)
        source = tmp_path / "data.txt"
        source.write_text("restored content")

        op, _formatter = _make_operation(source, tmp_path / "managed")

        with patch.object(ChecksumVerifier, "compute", side_effect=["aaa", "bbb"]):
            result = op._verify(managed)

        assert result == 1
        assert not source.exists(), "restored copy must be deleted on mismatch"

    def test_mismatch_preserves_managed_copy(self, tmp_path: Path) -> None:
        """Managed copy is left untouched when checksum mismatch is detected.

        Requirements: 4.6
        """
        managed = tmp_path / "managed" / "data.txt"
        managed.parent.mkdir()
        managed.write_text("managed content")

        source = tmp_path / "data.txt"
        source.write_text("restored content")

        op, _ = _make_operation(source, tmp_path / "managed")

        with patch.object(ChecksumVerifier, "compute", side_effect=["aaa", "bbb"]):
            op._verify(managed)

        assert managed.exists(), "managed copy must still exist after mismatch"
        assert managed.read_text() == "managed content", "managed copy content must be unchanged"

    def test_mismatch_emits_error_message(self, tmp_path: Path) -> None:
        """formatter.error is called with a checksum-mismatch message.

        Requirements: 4.6
        """
        managed = tmp_path / "managed" / "data.txt"
        managed.parent.mkdir()
        managed.write_text("managed content")

        source = tmp_path / "data.txt"
        source.write_text("restored content")

        op, formatter = _make_operation(source, tmp_path / "managed")

        with patch.object(ChecksumVerifier, "compute", side_effect=["aaa", "bbb"]):
            op._verify(managed)

        formatter.error.assert_called_once()
        error_msg = formatter.error.call_args[0][0]
        assert "mismatch" in error_msg.lower() or "checksum" in error_msg.lower()

    def test_mismatch_on_directory_deletes_restored_tree(self, tmp_path: Path) -> None:
        """A restored directory tree is removed on checksum mismatch.

        Requirements: 4.6
        """
        managed = tmp_path / "managed" / "srcdir"
        managed.parent.mkdir()
        managed.mkdir()
        (managed / "file.txt").write_text("data")

        source = tmp_path / "srcdir"
        source.mkdir()
        (source / "file.txt").write_text("data")

        op, _ = _make_operation(source, tmp_path / "managed")

        with patch.object(ChecksumVerifier, "compute", side_effect=["aaa", "bbb"]):
            result = op._verify(managed)

        assert result == 1
        assert not source.exists(), "restored directory must be deleted on mismatch"

    def test_mismatch_via_run_leaves_managed_copy_intact(self, tmp_path: Path) -> None:
        """Full run() with MD5 mismatch: managed copy preserved, exit code 1.

        Requirements: 4.6
        """
        managed_root = tmp_path / "managed"
        managed_root.mkdir()
        managed = managed_root / "data.txt"
        managed.write_text("managed content")

        # Create a symlink at source pointing to managed
        source = tmp_path / "data.txt"
        _make_symlink(source, managed)

        op, _ = _make_operation(source, managed_root)

        with patch.object(ChecksumVerifier, "compute", side_effect=["aaa", "bbb"]):
            result = op.run()

        assert result == 1
        assert managed.exists(), "managed copy must be preserved on mismatch"


# ---------------------------------------------------------------------------
# Requirement 4.2 — Permission error on symlink unlink
# ---------------------------------------------------------------------------


class TestPermissionErrorOnUnlink:
    """Tests for _replace() when unlinking the symlink raises PermissionError."""

    def test_permission_error_returns_1(self, tmp_path: Path) -> None:
        """Exit code 1 is returned when symlink unlink raises PermissionError.

        Requirements: 4.2
        """
        managed = tmp_path / "managed" / "data.txt"
        managed.parent.mkdir()
        managed.write_text("content")

        source = tmp_path / "data.txt"
        _make_symlink(source, managed)

        op, _ = _make_operation(source, tmp_path / "managed")

        with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
            result = op._replace(managed)

        assert result == 1

    def test_permission_error_emits_error_message(self, tmp_path: Path) -> None:
        """formatter.error is called with a permission-denied message.

        Requirements: 4.2
        """
        managed = tmp_path / "managed" / "data.txt"
        managed.parent.mkdir()
        managed.write_text("content")

        source = tmp_path / "data.txt"
        _make_symlink(source, managed)

        op, formatter = _make_operation(source, tmp_path / "managed")

        with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
            op._replace(managed)

        formatter.error.assert_called_once()
        assert "Permission denied" in formatter.error.call_args[0][0]

    def test_permission_error_no_copy_attempted(self, tmp_path: Path) -> None:
        """No copy is attempted when symlink unlink fails with PermissionError.

        The managed copy must remain untouched and no file is written to source.

        Requirements: 4.2
        """
        managed = tmp_path / "managed" / "data.txt"
        managed.parent.mkdir()
        managed.write_text("managed content")

        source = tmp_path / "data.txt"
        _make_symlink(source, managed)

        op, formatter = _make_operation(source, tmp_path / "managed")

        with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
            op._replace(managed)

        # copying_back must never be called — no copy was attempted
        formatter.copying_back.assert_not_called()
        # managed copy must be untouched
        assert managed.exists()
        assert managed.read_text() == "managed content"

    def test_permission_error_via_run_returns_1(self, tmp_path: Path) -> None:
        """Full run() with permission error on unlink returns exit code 1.

        Requirements: 4.2
        """
        managed_root = tmp_path / "managed"
        managed_root.mkdir()
        managed = managed_root / "data.txt"
        managed.write_text("content")

        source = tmp_path / "data.txt"
        _make_symlink(source, managed)

        op, _ = _make_operation(source, managed_root)

        with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
            result = op.run()

        assert result == 1


# ---------------------------------------------------------------------------
# Requirement 5.2 — Permission error deleting managed copy (non-fatal)
# ---------------------------------------------------------------------------


class TestPermissionErrorDeletingManagedCopy:
    """Tests for _delete_managed() when deleting the managed copy raises OSError."""

    def test_delete_failure_emits_warning(self, tmp_path: Path) -> None:
        """formatter.managed_copy_delete_failed is called when delete raises OSError.

        Requirements: 5.2
        """
        managed = tmp_path / "managed" / "data.txt"
        managed.parent.mkdir()
        managed.write_text("content")

        source = tmp_path / "data.txt"
        source.write_text("content")

        op, formatter = _make_operation(source, tmp_path / "managed")

        with patch.object(Path, "unlink", side_effect=OSError("permission denied")):
            op._delete_managed(managed)

        formatter.managed_copy_delete_failed.assert_called_once_with(managed)

    def test_delete_failure_does_not_call_deleted_success(self, tmp_path: Path) -> None:
        """formatter.managed_copy_deleted is NOT called when delete raises OSError.

        Requirements: 5.2
        """
        managed = tmp_path / "managed" / "data.txt"
        managed.parent.mkdir()
        managed.write_text("content")

        source = tmp_path / "data.txt"
        source.write_text("content")

        op, formatter = _make_operation(source, tmp_path / "managed")

        with patch.object(Path, "unlink", side_effect=OSError("permission denied")):
            op._delete_managed(managed)

        formatter.managed_copy_deleted.assert_not_called()

    def test_delete_failure_via_run_returns_0(self, tmp_path: Path) -> None:
        """Full run() returns exit code 0 even when managed copy deletion fails.

        The restore to CWD has already succeeded and been verified; the
        deletion failure is non-fatal.

        Requirements: 5.2
        """
        managed_root = tmp_path / "managed"
        managed_root.mkdir()
        managed = managed_root / "data.txt"
        managed.write_text("hello world")

        source = tmp_path / "data.txt"
        _make_symlink(source, managed)

        op, _ = _make_operation(source, managed_root)

        # Patch managed.unlink to raise OSError inside _delete_managed so the
        # non-fatal warning path is exercised while run() still returns 0.
        original_unlink = Path.unlink

        def _selective_unlink(self_path: Path, missing_ok: bool = False) -> None:
            if self_path == managed:
                raise OSError("permission denied")
            original_unlink(self_path, missing_ok=missing_ok)

        with patch.object(Path, "unlink", _selective_unlink):
            result = op.run()

        assert result == 0

    def test_delete_failure_via_run_emits_warning(self, tmp_path: Path) -> None:
        """Full run() emits a warning when managed copy deletion fails.

        Requirements: 5.2
        """
        managed_root = tmp_path / "managed"
        managed_root.mkdir()
        managed = managed_root / "data.txt"
        managed.write_text("hello world")

        source = tmp_path / "data.txt"
        _make_symlink(source, managed)

        op, formatter = _make_operation(source, managed_root)

        # Simulate OSError during _delete_managed by patching managed.unlink
        def _failing_delete(self_inner: RestoreOperation, managed_path: Path) -> None:
            formatter.managed_copy_delete_failed(managed_path)

        with patch.object(RestoreOperation, "_delete_managed", _failing_delete):
            result = op.run()

        assert result == 0
        formatter.managed_copy_delete_failed.assert_called_once()
