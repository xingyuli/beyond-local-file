"""Property-based tests for RestoreOperation dry-run filesystem invariant.

This module verifies that invoking ``RestoreOperation`` with ``dry_run=True``
never modifies the filesystem, regardless of the symlink setup or its contents.
"""

# Feature: revlink-subcommands, Property 1: restore dry-run never modifies filesystem

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from beyond_local_file.operations.revlink import RestoreFormatter, RestoreOperation
from tests.path_strategies import is_safe_fs_name

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Safe ASCII filename characters: alphanumeric plus hyphens and underscores.
# Also excludes Windows reserved device names (NUL, COM1, …).
_filename = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="-_",
    ),
    min_size=1,
    max_size=30,
).filter(is_safe_fs_name)


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------


def _snapshot(root: Path) -> dict[str, bytes]:
    """Capture a snapshot of all files under *root*.

    Walks the entire directory tree rooted at *root* and records every file's
    contents keyed by its path relative to *root* (as a POSIX string).
    Symlinks are recorded as their link target string rather than the bytes
    of the pointed-to file, so that the presence or absence of a symlink is
    captured faithfully.

    Args:
        root: Directory to snapshot. Must exist.

    Returns:
        Dictionary mapping relative POSIX path strings to file bytes (or the
        symlink target encoded as UTF-8 for symlinks).
    """
    snapshot: dict[str, bytes] = {}
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            # Record the symlink target so creation/deletion of symlinks is detected.
            snapshot[rel] = str(path.readlink()).encode()
        elif path.is_file():
            snapshot[rel] = path.read_bytes()
        else:
            # Directories: record their presence with empty bytes.
            snapshot[rel] = b""
    return snapshot


# ---------------------------------------------------------------------------
# Property 1: restore dry-run never modifies the filesystem
# ---------------------------------------------------------------------------


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    filename=_filename,
    content=st.binary(),
)
def test_restore_dryrun_does_not_modify_filesystem_with_valid_symlink(
    filename: str,
    content: bytes,
) -> None:
    """Verify that restore dry-run leaves the filesystem unchanged for a valid symlink setup.

    **Validates: Requirements 3.4**

    For any valid symlink at ``source`` pointing to a real managed copy in
    ``managed_dir``, invoking ``RestoreOperation`` with ``dry_run=True`` must
    leave the entire directory tree in exactly the same state as before the
    call — no files created, moved, or deleted.

    A fresh ``tempfile.TemporaryDirectory`` is used inside the test body so
    each Hypothesis example gets a fully isolated directory.

    Args:
        filename: Name of the managed file and the symlink to create.
        content: Raw bytes to write into the managed copy.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()
        managed_dir = tmp_path / "managed"
        managed_dir.mkdir()

        # Create the managed copy (the real file in the managed project).
        managed_copy = managed_dir / filename
        managed_copy.write_bytes(content)

        # Create a symlink at source pointing to the managed copy.
        source = cwd_dir / filename
        source.symlink_to(managed_copy)

        before = _snapshot(tmp_path)

        RestoreOperation(
            source=source,
            dest_root=managed_dir,
            rel_path=Path(filename),
            dry_run=True,
            formatter=RestoreFormatter(dry_run=True),
        ).run()

        after = _snapshot(tmp_path)

        assert before == after, (
            f"Restore dry-run modified the filesystem.\n"
            f"Keys only in before: {set(before) - set(after)}\n"
            f"Keys only in after:  {set(after) - set(before)}\n"
            f"Changed values: {[k for k in before if k in after and before[k] != after[k]]}"
        )


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    filename=_filename,
    content=st.binary(),
)
def test_restore_dryrun_does_not_modify_filesystem_when_source_missing(
    filename: str,
    content: bytes,
) -> None:
    """Verify that restore dry-run leaves the filesystem unchanged when source does not exist.

    **Validates: Requirements 3.4**

    Even when validation fails because the source path does not exist,
    invoking ``RestoreOperation`` with ``dry_run=True`` must not modify the
    filesystem. This exercises the validation-failure path of the dry-run
    invariant.

    A fresh ``tempfile.TemporaryDirectory`` is used inside the test body so
    each Hypothesis example gets a fully isolated directory.

    Args:
        filename: Name used for the non-existent source path under ``cwd/``.
        content: Unused bytes parameter kept for strategy symmetry with the
            sibling tests; ensures Hypothesis exercises the same filename space.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()
        managed_dir = tmp_path / "managed"
        managed_dir.mkdir()

        # Deliberately do NOT create the source — validation must fail.
        source = cwd_dir / filename

        before = _snapshot(tmp_path)

        RestoreOperation(
            source=source,
            dest_root=managed_dir,
            rel_path=Path(filename),
            dry_run=True,
            formatter=RestoreFormatter(dry_run=True),
        ).run()

        after = _snapshot(tmp_path)

        assert before == after, (
            f"Restore dry-run modified the filesystem even when source is missing.\n"
            f"Keys only in before: {set(before) - set(after)}\n"
            f"Keys only in after:  {set(after) - set(before)}\n"
            f"Changed values: {[k for k in before if k in after and before[k] != after[k]]}"
        )


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    filename=_filename,
    content=st.binary(),
)
def test_restore_dryrun_does_not_modify_filesystem_when_source_is_not_symlink(
    filename: str,
    content: bytes,
) -> None:
    """Verify that restore dry-run leaves the filesystem unchanged when source is a real file.

    **Validates: Requirements 3.4**

    When the source path exists but is not a symlink, ``RestoreOperation``
    validation must fail and the filesystem must remain untouched even with
    ``dry_run=True``.

    A fresh ``tempfile.TemporaryDirectory`` is used inside the test body so
    each Hypothesis example gets a fully isolated directory.

    Args:
        filename: Name of the real file to create under ``cwd/``.
        content: Raw bytes to write into the real file.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()
        managed_dir = tmp_path / "managed"
        managed_dir.mkdir()

        # Create a real file (not a symlink) — validation must fail.
        source = cwd_dir / filename
        source.write_bytes(content)

        before = _snapshot(tmp_path)

        RestoreOperation(
            source=source,
            dest_root=managed_dir,
            rel_path=Path(filename),
            dry_run=True,
            formatter=RestoreFormatter(dry_run=True),
        ).run()

        after = _snapshot(tmp_path)

        assert before == after, (
            f"Restore dry-run modified the filesystem when source is not a symlink.\n"
            f"Keys only in before: {set(before) - set(after)}\n"
            f"Keys only in after:  {set(after) - set(before)}\n"
            f"Changed values: {[k for k in before if k in after and before[k] != after[k]]}"
        )
