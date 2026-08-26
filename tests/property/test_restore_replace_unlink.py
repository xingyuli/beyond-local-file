"""Property-based tests for RestoreOperation._replace unlink-not-rmtree invariant.

This module verifies that invoking ``RestoreOperation._replace`` on a symlink
whose target is a directory never deletes the target directory — proving that
``shutil.rmtree`` is not called on the symlink path (which would follow the
link and destroy the managed copy).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings
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

# File content for files placed inside the managed directory.
_file_content = st.binary(min_size=0, max_size=256)


# ---------------------------------------------------------------------------
# Property 3: _replace uses unlink not rmtree on symlinks
# ---------------------------------------------------------------------------


# Feature: revlink-subcommands, Property 3: _replace uses unlink not rmtree on symlinks
@settings(max_examples=100)
@given(
    dir_name=_filename,
    file_name=_filename,
    file_content=_file_content,
)
def test_replace_does_not_rmtree_symlink_target(
    dir_name: str,
    file_name: str,
    file_content: bytes,
) -> None:
    """Verify that _replace removes the symlink with unlink, not rmtree.

    **Validates: Requirements 4.1**

    For any symlink at ``source`` whose target is a real directory, invoking
    ``RestoreOperation._replace`` must leave the target directory intact after
    the call completes.  If ``shutil.rmtree`` were called on the symlink path
    it would follow the link and delete the target directory; using
    ``source.unlink()`` removes only the symlink inode, leaving the target
    untouched.

    The assertion is: after ``_replace`` returns, the managed directory that
    was the symlink target still exists on disk.

    A fresh ``tempfile.TemporaryDirectory`` is used inside the test body so
    each Hypothesis example gets a fully isolated directory.

    Args:
        dir_name: Name of the managed directory (the symlink target).
        file_name: Name of a file to place inside the managed directory so
            the directory is non-empty and its existence is unambiguous.
        file_content: Raw bytes to write into the file inside the managed
            directory.
    """
    # Hypothesis may generate the same name for dir_name and file_name.
    # Ensure they are distinct to avoid a collision when creating the file
    # inside the directory.
    if dir_name == file_name:
        file_name = file_name + "_file"

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # managed_dir is the real directory that the symlink will point to.
        managed_dir = tmp_path / "managed" / dir_name
        managed_dir.mkdir(parents=True)
        (managed_dir / file_name).write_bytes(file_content)

        # cwd_dir is the directory where the symlink lives.
        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()

        # Create the symlink: cwd_dir/dir_name -> managed_dir
        symlink_path = cwd_dir / dir_name
        symlink_path.symlink_to(managed_dir)

        assert symlink_path.is_symlink(), "Pre-condition: symlink must exist before _replace"
        assert managed_dir.is_dir(), "Pre-condition: managed directory must exist before _replace"

        # Invoke _replace directly.  dest_root is set so that
        # dest_root / source.name == managed_dir.
        dest_root = tmp_path / "managed"
        operation = RestoreOperation(
            source=symlink_path,
            dest_root=dest_root,
            rel_path=Path(dir_name),
            dry_run=False,
            formatter=RestoreFormatter(dry_run=False),
        )
        operation._replace(managed_dir)

        # The managed directory must still exist — rmtree was NOT called.
        assert managed_dir.exists(), (
            f"_replace deleted the symlink target directory at {managed_dir}. "
            f"This indicates shutil.rmtree was called on the symlink path "
            f"instead of source.unlink()."
        )
        assert managed_dir.is_dir(), f"Managed directory at {managed_dir} is no longer a directory after _replace."
