"""Beyond Local File - A CLI tool for projecting local files as copies.

This package provides a command-line interface for projecting files and
directories from managed projects into target locations as physical copies,
with automatic git exclude management and a live daemon runtime.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("beyond-local-file")
except PackageNotFoundError:
    # Package is not installed, fallback for development
    __version__ = "0.0.0.dev0"

__all__ = ["__version__"]
