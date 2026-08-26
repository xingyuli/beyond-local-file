"""Shared Hypothesis path-component filters for cross-platform property tests.

Windows reserves several device names (``NUL``, ``COM1``, ``CON``, …).  When
Hypothesis generates those as directory or file names, ``mkdir`` / ``open``
fail with ``NotADirectoryError`` / ``FileNotFoundError``.  Filtering them on
all platforms keeps the generators portable without platform-specific skips.
"""

from __future__ import annotations

import re

# Matches CON, PRN, AUX, NUL, COM1-COM9, LPT1-LPT9, optionally with an extension
# (e.g. COM1.txt).  See Microsoft docs on reserved file names.
_WINDOWS_RESERVED_NAME = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$",
    re.IGNORECASE,
)


def is_safe_fs_name(name: str) -> bool:
    """Return True when *name* is safe to use as a single path component on all OSes.

    Args:
        name: A single path component (no separators).

    Returns:
        False for ``.`` / ``..`` and Windows reserved device names; True otherwise.
    """
    if name in (".", "..") or not name:
        return False
    return _WINDOWS_RESERVED_NAME.match(name) is None


def is_safe_relative_path(path: str) -> bool:
    """Return True when *path* is a relative path whose components are all FS-safe.

    Args:
        path: A relative path that may contain ``/`` separators.

    Returns:
        False when empty, absolute, contains ``..``, or any component is reserved.
    """
    if not path or path.startswith("/") or ".." in path.split("/"):
        return False
    parts = [part for part in path.split("/") if part]
    return bool(parts) and all(is_safe_fs_name(part) for part in parts)
