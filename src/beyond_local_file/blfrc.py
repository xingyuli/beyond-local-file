"""Runtime home directory (``~/.blf``)."""

import os
from pathlib import Path


def get_home_directory() -> Path:
    """Get home directory, respecting BLF_HOME env var for testing.

    Returns:
        Path to home directory.
    """
    if "BLF_HOME" in os.environ:
        return Path(os.environ["BLF_HOME"])
    return Path.home()


def runtime_home() -> Path:
    """Return the runtime home directory.

    ``BLF_HOME`` relocates the home used for ``~/.blf``.

    Returns:
        ``<home>/.blf``.
    """
    return get_home_directory() / ".blf"
