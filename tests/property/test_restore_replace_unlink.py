"""Property test: restore_item unlinks a leftover symlink instead of rmtree.

``shutil.rmtree`` on the symlink would follow it and destroy the hub copy
before the bytes are copied back. ``restore_item`` must leave those bytes on
the requesting path.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from beyond_local_file.daemon.live import LiveSync
from beyond_local_file.model.config import ConfigProject, Mapping
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
    """restore_item unlinks the symlink, then copies hub bytes onto PATH.

    If ``shutil.rmtree`` followed the symlink, the hub bytes would be gone
    before the copy and the requesting path would not contain *file_content*.

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

        assert symlink_path.is_symlink(), "Pre-condition: symlink must exist before restore"
        assert managed_dir.is_dir(), "Pre-condition: managed directory must exist before restore"

        dest_root = tmp_path / "managed"
        project = ConfigProject(
            managed_project_name="lab-app",
            managed_project_path=dest_root,
            mappings=[Mapping(targets=[cwd_dir], subpaths=[dir_name])],
        )
        LiveSync({"lab-app": project}, {}).restore_item(cwd_dir, dir_name)

        assert symlink_path.is_dir()
        assert not symlink_path.is_symlink()
        assert (symlink_path / file_name).read_bytes() == file_content
