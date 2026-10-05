"""Unit tests for CreateOperation failure modes.

Covers:
- Copy I/O failure is OSError; source is untouched
- Copy-only create leaves the target path as a regular file
- ChecksumVerifier is gone
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from beyond_local_file.operations import revlink
from beyond_local_file.operations.revlink import CreateFormatter, CreateOperation

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


def test_checksum_verifier_is_gone() -> None:
    """ChecksumVerifier (whole-tree MD5) is retired."""
    assert not hasattr(revlink, "ChecksumVerifier")


# ---------------------------------------------------------------------------
# Copy I/O failure is OSError
# ---------------------------------------------------------------------------


class TestCreateCopyIoFailure:
    """Create trusts copy_projection; I/O failure is OSError."""

    def test_copy_oserror_propagates_and_leaves_source(self, tmp_path: Path) -> None:
        """copy_projection OSError propagates; source bytes are unchanged."""
        source = tmp_path / "source.txt"
        source.write_text("original content")
        dest_root = tmp_path / "managed"
        dest_root.mkdir()
        op, _formatter = _make_operation(source, dest_root)

        with (
            patch("beyond_local_file.operations.revlink.copy_projection", side_effect=OSError("disk full")),
            pytest.raises(OSError, match="disk full"),
        ):
            op.run()

        assert source.exists()
        assert source.read_text() == "original content"
        assert not (dest_root / "source.txt").exists()

    def test_successful_copy_does_not_emit_checksum_steps(self, tmp_path: Path) -> None:
        """Create does not MD5-verify after copy."""
        source = tmp_path / "source.txt"
        source.write_text("data")
        dest_root = tmp_path / "managed"
        dest_root.mkdir()
        op, formatter = _make_operation(source, dest_root)

        result = op.run()

        assert result == 0
        names = [call[0] for call in formatter.method_calls]
        assert "computing_checksum" not in names
        assert "checksum_ok" not in names
        formatter.copying.assert_called()
        formatter.target_left_in_place.assert_called_once_with(source)


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
