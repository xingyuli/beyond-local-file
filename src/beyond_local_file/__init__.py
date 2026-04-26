"""Beyond Local File - A CLI tool for managing symlinks across projects.

This package provides a command-line interface for synchronizing files and
directories from managed projects to target locations using symlinks, with
automatic git exclude management.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("beyond-local-file")
except PackageNotFoundError:
    # Package is not installed, fallback for development
    __version__ = "0.0.0.dev0"

__all__ = ["__version__"]
