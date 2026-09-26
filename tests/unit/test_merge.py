"""Binary/text detection used by the resolve UI (ADR 0025)."""

from __future__ import annotations

from beyond_local_file.daemon.merge import is_binary


def test_is_binary_nul_or_non_utf8() -> None:
    """NUL bytes or non-UTF-8 data are binary; ordinary text is not."""
    assert is_binary(b"from-a\x00")
    assert is_binary(b"\xff\xfe")
    assert not is_binary(b"from-a")
    assert not is_binary(b"# Heading\n\n**bold**\n")
