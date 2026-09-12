"""Runtime contribution source: which managed project owns an item on a target.

Derived from committed mappings after item discovery. Not persisted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import click

from beyond_local_file.model.config import ConfigProject
from beyond_local_file.model.translator import translate_config_to_processing


@dataclass(frozen=True)
class ItemOverlap:
    """Two items on one target whose paths are equal or nested."""

    target: Path
    project_a: str
    item_a: str
    project_b: str
    item_b: str


def item_paths_overlap(left: str, right: str) -> bool:
    """Return whether two item names are equal or one is a path prefix of the other.

    Args:
        left: First item name (relative path).
        right: Second item name (relative path).

    Returns:
        True when the names collide on a target tree.
    """
    if left == right:
        return True
    return left.startswith(f"{right}/") or right.startswith(f"{left}/")


def find_item_path_overlaps(projects: dict[str, ConfigProject]) -> list[ItemOverlap]:
    """Find item path overlaps across all contributors to each target.

    Args:
        projects: Committed mappings.

    Returns:
        One overlap per colliding pair, sorted by target then item names.
    """
    grouped: dict[Path, list[tuple[str, str]]] = {}
    for unit in translate_config_to_processing(projects):
        target = unit.target_project_path.resolve()
        slot = grouped.setdefault(target, [])
        for item in unit.items:
            slot.append((unit.managed_project_name, item.name))

    overlaps: list[ItemOverlap] = []
    for target, entries in grouped.items():
        for index, (project_a, item_a) in enumerate(entries):
            for project_b, item_b in entries[index + 1 :]:
                if item_paths_overlap(item_a, item_b):
                    overlaps.append(
                        ItemOverlap(
                            target=target,
                            project_a=project_a,
                            item_a=item_a,
                            project_b=project_b,
                            item_b=item_b,
                        )
                    )
    overlaps.sort(key=lambda row: (str(row.target), row.item_a, row.item_b, row.project_a, row.project_b))
    return overlaps


def format_item_overlap(overlap: ItemOverlap) -> str:
    """Render one overlap as an error clause.

    Args:
        overlap: A colliding pair on one target.

    Returns:
        Text after ``Error:``.
    """
    return (
        f"overlapping items on {overlap.target}: "
        f"{overlap.project_a} '{overlap.item_a}' and "
        f"{overlap.project_b} '{overlap.item_b}'"
    )


def echo_item_path_overlaps(projects: dict[str, ConfigProject]) -> bool:
    """Print overlap errors. Return True when any overlap exists.

    Args:
        projects: Committed mappings to check.

    Returns:
        True when start/reload must abort.
    """
    overlaps = find_item_path_overlaps(projects)
    for overlap in overlaps:
        click.echo(f"Error: {format_item_overlap(overlap)}")
    return bool(overlaps)
