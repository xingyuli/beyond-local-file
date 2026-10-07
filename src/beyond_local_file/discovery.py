"""Item discovery: declared vs present names, and path membership.

Selective mappings contribute declared subpaths (on the hub or still missing).
Sync-all contributes present top-level hub entries. Distinct from mapping expansion.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from beyond_local_file.held import is_held_item_name


def item_names(hub: Path, subpaths: Sequence[str] | None) -> list[str]:
    """Return the names a mapping contributes.

    Args:
        hub: Managed-project directory.
        subpaths: Declared selective names, or ``None`` for sync-all.

    Returns:
        Selective: declared names in mapping order, held and empty dropped.
        Sync-all: present top-level hub entries, held-copy directory skipped,
        sorted. Missing hub yields an empty list.
    """
    if subpaths is not None:
        names: list[str] = []
        for subpath in subpaths:
            if not subpath or is_held_item_name(Path(subpath).parts[0]):
                continue
            names.append(subpath)
        return names
    if not hub.is_dir():
        return []
    return sorted(path.name for path in hub.iterdir() if not is_held_item_name(path.name))


def item_covers_rel(item_name: str, rel: str) -> bool:
    """Return whether *rel* is *item_name* or a path under it.

    ``CONTEXT.md`` does not cover ``CONTEXT-MAP.md``: the prefix must be a
    full path component.

    Args:
        item_name: Declared or discovered item name (relative path).
        rel: Path relative to a replica or hub root.

    Returns:
        True when *rel* belongs to *item_name*.
    """
    return rel == item_name or rel.startswith(f"{item_name}/")


def rel_in_items(rel: str, names: Sequence[str]) -> bool:
    """Return whether *rel* is one of *names* or a path under one.

    Args:
        rel: Path relative to a replica or hub root.
        names: Item names that mapping contributes.

    Returns:
        True when *rel* belongs to a contributed item.
    """
    return any(item_covers_rel(name, rel) for name in names)
