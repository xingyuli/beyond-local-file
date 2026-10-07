"""Unit tests for RestoreOperation failure modes.

Covers:
- Leftover-symlink copy I/O failure is OSError; managed copy preserved
- Permission error on symlink unlink: error message, no copy attempted, exit code 1
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from beyond_local_file.operations.revlink import RestoreOperation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_operation(
    source: Path,
    dest_root: Path,
) -> RestoreOperation:
    """Build a RestoreOperation.

    Args:
        source: Source path (the symlink in CWD) for the operation.
        dest_root: Destination root (managed project path) for the operation.
    """
    return RestoreOperation(
        source=source,
        dest_root=dest_root,
        rel_path=Path(source.name),
        dry_run=False,
    )


def _make_symlink(link: Path, target: Path) -> None:
    """Create a symlink at *link* pointing to *target*.

    Args:
        link: Path where the symlink will be created.
        target: Path the symlink will point to.
    """
    link.symlink_to(target)


# ---------------------------------------------------------------------------
# Leftover-symlink copy I/O failure is OSError
# ---------------------------------------------------------------------------


class TestRestoreCopyIoFailure:
    """Leftover-symlink restore trusts copy_projection; I/O failure is OSError."""

    def test_copy_oserror_propagates_and_preserves_managed(self, tmp_path: Path) -> None:
        """copy_projection OSError propagates; managed copy is unchanged."""
        managed_root = tmp_path / "managed"
        managed_root.mkdir()
        managed = managed_root / "data.txt"
        managed.write_text("managed content")
        source = tmp_path / "data.txt"
        _make_symlink(source, managed)
        op = _make_operation(source, managed_root)

        with (
            patch("beyond_local_file.operations.revlink.copy_projection", side_effect=OSError("disk full")),
            pytest.raises(OSError, match="disk full"),
        ):
            op.run()

        assert managed.exists()
        assert managed.read_text() == "managed content"

    def test_leftover_symlink_restore_does_not_emit_checksum_steps(self, tmp_path: Path) -> None:
        """Leftover-symlink restore materializes the file without checksum fields."""
        managed_root = tmp_path / "managed"
        managed_root.mkdir()
        managed = managed_root / "data.txt"
        managed.write_text("managed content")
        source = tmp_path / "data.txt"
        _make_symlink(source, managed)
        result = _make_operation(source, managed_root).run()

        assert result.exit_code == 0
        assert result.leftover_symlink is True
        assert result.errors == ()
        assert result.source == source.as_posix()
        assert result.managed == managed.as_posix()
        assert source.is_file()
        assert not source.is_symlink()
        assert source.read_text() == "managed content"


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

        op = _make_operation(source, tmp_path / "managed")

        with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
            result = op._replace(managed)

        assert result is not None
        assert result.exit_code == 1

    def test_permission_error_emits_error_message(self, tmp_path: Path) -> None:
        """Permission-denied unlink is an error body on the result.

        Requirements: 4.2
        """
        managed = tmp_path / "managed" / "data.txt"
        managed.parent.mkdir()
        managed.write_text("content")

        source = tmp_path / "data.txt"
        _make_symlink(source, managed)

        op = _make_operation(source, tmp_path / "managed")

        with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
            result = op._replace(managed)

        assert result is not None
        assert result.leftover_symlink is True
        assert result.errors == (f"Permission denied removing symlink at {source}",)

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

        op = _make_operation(source, tmp_path / "managed")

        with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
            result = op._replace(managed)

        assert result is not None
        assert result.errors == (f"Permission denied removing symlink at {source}",)
        assert source.is_symlink()
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

        op = _make_operation(source, managed_root)

        with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
            result = op.run()

        assert result.exit_code == 1
        assert result.leftover_symlink is True
        assert result.errors == (f"Permission denied removing symlink at {source}",)
