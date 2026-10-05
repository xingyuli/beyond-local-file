"""Write a projection as a physical copy, preserving nested symlink nodes."""

import os
import shutil
from pathlib import Path


def copy_projection(source: Path, destination: Path) -> None:
    """Replace *destination* with a copy of *source*, preserving symlink nodes.

    Nested symlinks inside a directory stay links (venv interpreters, relative
    ``python`` → ``python3.14``). A symlink at *source* is copied as a symlink,
    not followed. The projection path itself remains a real file or directory.

    Args:
        source: File, directory, or symlink to copy.
        destination: Path that should become the copy.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or destination.is_file():
        destination.unlink()
    elif destination.is_dir():
        shutil.rmtree(destination)
    if source.is_symlink():
        os.symlink(os.readlink(source), destination)
    elif source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination, follow_symlinks=False)
