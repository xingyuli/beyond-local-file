"""Property-based tests for ConfigUpdater.remove_subpath_entry idempotence.

This module verifies that calling ``ConfigUpdater.remove_subpath_entry`` twice
with the same arguments produces the same config file content as calling it
once — the second call is always a no-op.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from beyond_local_file.config import ConfigUpdater
from tests.path_strategies import is_safe_fs_name

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Safe entry names: ASCII alphanumeric plus hyphens, underscores, and dots.
# ASCII-only avoids locale/encoding issues when writing YAML on non-UTF-8 Windows.
# Also excludes Windows reserved device names (NUL, COM1, …).
_entry_name = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.",
    min_size=1,
    max_size=40,
).filter(is_safe_fs_name)

# A list of subpath entries (plain strings) for the config YAML.
_subpath_entries = st.lists(
    _entry_name,
    min_size=0,
    max_size=8,
    unique=True,
)


def _build_config_yaml(target: str, subpath_entries: list[str]) -> str:
    """Build a minimal config YAML string with a subpath list.

    Produces a YAML document with a single project ``test-project`` that has
    one dict-mapping with the given target and subpath list.

    Args:
        target: The target path string to embed in the mapping.
        subpath_entries: List of plain-string subpath entries. If empty, the
            ``subpath`` key is still present with an empty list so that the
            mapping is in selective-sync mode.

    Returns:
        A YAML string suitable for writing to a config file.
    """
    lines = [
        "test-project:",
        f"  target: {target}",
        "  subpath:",
    ]
    for entry in subpath_entries:
        lines.append(f"    - {entry}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Property 2: remove_subpath_entry is idempotent
# ---------------------------------------------------------------------------


# Feature: revlink-subcommands, Property 2: remove_subpath_entry is idempotent
@settings(max_examples=100)
@given(
    subpath_entries=_subpath_entries,
    entry_name=_entry_name,
)
def test_remove_subpath_entry_is_idempotent(
    subpath_entries: list[str],
    entry_name: str,
) -> None:
    """Verify that remove_subpath_entry is idempotent.

    **Validates: Requirements 6.3, 6.4, 6.5**

    For any config file with a subpath list and any entry name, calling
    ``ConfigUpdater.remove_subpath_entry`` twice with the same arguments must
    produce the same config file content as calling it once — the second call
    is a no-op regardless of whether the entry was present or absent.

    This covers two cases:
    - Entry present: first call removes it, second call finds it absent and
      returns ``False`` without modifying the file.
    - Entry absent: both calls find it absent and return ``False`` without
      modifying the file.

    A fresh ``tempfile.TemporaryDirectory`` is used inside the test body so
    each Hypothesis example gets a fully isolated directory.

    Args:
        subpath_entries: List of plain-string subpath entries to populate the
            config with. The entry under test may or may not be in this list.
        entry_name: The entry name to pass to ``remove_subpath_entry`` on both
            calls.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        config_file = tmp_path / "config.yaml"
        cwd = tmp_path / "target"
        cwd.mkdir()

        # Write the initial config YAML (UTF-8; as_posix avoids YAML/Windows issues).
        config_file.write_text(_build_config_yaml(cwd.as_posix(), subpath_entries), encoding="utf-8")

        updater = ConfigUpdater(config_file)

        # First call — may or may not remove the entry.
        updater.remove_subpath_entry("test-project", cwd, entry_name)
        content_after_first = config_file.read_text(encoding="utf-8")

        # Second call — must be a no-op; file content must not change.
        updater.remove_subpath_entry("test-project", cwd, entry_name)
        content_after_second = config_file.read_text(encoding="utf-8")

        assert content_after_first == content_after_second, (
            f"remove_subpath_entry is not idempotent.\n"
            f"subpath_entries={subpath_entries!r}, entry_name={entry_name!r}\n"
            f"Content after first call:\n{content_after_first}\n"
            f"Content after second call:\n{content_after_second}"
        )
