"""Binary/text detection for the resolve UI.

The resolve UI's merge editor is a sequential, client-driven two-way diff (ADR 0025);
the daemon's only remaining job for it is telling text apart from binary.
"""

from __future__ import annotations


def is_binary(data: bytes) -> bool:
    """Return whether *data* is binary (NUL or not UTF-8 text).

    Args:
        data: File bytes.

    Returns:
        True when the bytes should not be opened in the merge editor.
    """
    if b"\x00" in data:
        return True
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False
