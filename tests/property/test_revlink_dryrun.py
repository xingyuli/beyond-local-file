"""Property-based tests for CreateOperation dry-run filesystem invariant.

This module verifies that invoking ``CreateOperation`` with ``dry_run=True``
never modifies the filesystem, regardless of the source path or its contents.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from beyond_local_file.operations.revlink import CreateFormatter, CreateOperation

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Safe ASCII filename characters: alphanumeric plus hyphens and underscores.
# Filter out empty strings and the special names "." and "..".
_filename = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="-_",
    ),
    min_size=1,
    max_size=30,
).filter(lambda s: s not in (".", ".."))


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
# Property 6: Dry-run never modifies the filesystem
# ---------------------------------------------------------------------------


# Feature: revlink, Property 6: Dry-run never modifies the filesystem
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    filename=_filename,
    content=st.binary(),
)
def test_dryrun_does_not_modify_filesystem_with_existing_source(
    filename: str,
    content: bytes,
) -> None:
    """Verify that dry-run leaves the filesystem unchanged when source exists.

    **Validates: Requirements 3.4, 6.4**

    For any valid source file in ``tmp_path/target/`` and any ``dest_root``
    in ``tmp_path/managed/``, invoking ``CreateOperation`` with
    ``dry_run=True`` must leave the entire ``tmp_path`` tree in exactly the
    same state as before the call — no files created, moved, or deleted.

    A fresh ``tempfile.TemporaryDirectory`` is used inside the test body so
    each Hypothesis example gets a fully isolated directory.

    Args:
        filename: Name of the source file to create under ``target/``.
        content: Raw bytes to write into the source file.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        target_dir = tmp_path / "target"
        target_dir.mkdir()
        managed_dir = tmp_path / "managed"
        managed_dir.mkdir()

        source = target_dir / filename
        source.write_bytes(content)

        before = _snapshot(tmp_path)

        CreateOperation(
            source=source,
            dest_root=managed_dir,
            rel_path=Path(filename),
            dry_run=True,
            force=False,
            formatter=CreateFormatter(dry_run=True),
        ).run()

        after = _snapshot(tmp_path)

        assert before == after, (
            f"Dry-run modified the filesystem.\n"
            f"Keys only in before: {set(before) - set(after)}\n"
            f"Keys only in after:  {set(after) - set(before)}\n"
            f"Changed values: {[k for k in before if k in after and before[k] != after[k]]}"
        )


# Feature: revlink, Property 6: Dry-run never modifies the filesystem
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    filename=_filename,
    content=st.binary(),
)
def test_dryrun_does_not_modify_filesystem_with_nonexistent_source(
    filename: str,
    content: bytes,
) -> None:
    """Verify that dry-run leaves the filesystem unchanged when source does not exist.

    **Validates: Requirements 3.4, 6.4**

    Even when validation fails (source path does not exist), invoking
    ``CreateOperation`` with ``dry_run=True`` must not modify the filesystem.
    This exercises the validation-failure path of the dry-run invariant.

    A fresh ``tempfile.TemporaryDirectory`` is used inside the test body so
    each Hypothesis example gets a fully isolated directory.

    Args:
        filename: Name used for the non-existent source path under ``target/``.
        content: Unused bytes parameter kept for strategy symmetry with the
            sibling test; ensures Hypothesis exercises the same filename space.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        target_dir = tmp_path / "target"
        target_dir.mkdir()
        managed_dir = tmp_path / "managed"
        managed_dir.mkdir()

        # Deliberately do NOT create the source file — validation must fail.
        source = target_dir / filename

        before = _snapshot(tmp_path)

        CreateOperation(
            source=source,
            dest_root=managed_dir,
            rel_path=Path(filename),
            dry_run=True,
            force=False,
            formatter=CreateFormatter(dry_run=True),
        ).run()

        after = _snapshot(tmp_path)

        assert before == after, (
            f"Dry-run modified the filesystem even on validation failure.\n"
            f"Keys only in before: {set(before) - set(after)}\n"
            f"Keys only in after:  {set(after) - set(before)}\n"
            f"Changed values: {[k for k in before if k in after and before[k] != after[k]]}"
        )
