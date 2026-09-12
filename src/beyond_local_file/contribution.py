"""Runtime contribution source: which managed project owns an item on a target.

Derived from committed mappings after item discovery. Not persisted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import click

from beyond_local_file.held import is_held_item_name
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


def item_covers_rel(item_name: str, rel: str) -> bool:
    """Return whether *rel* is *item_name* or a path under it.

    ``CONTEXT.md`` does not cover ``CONTEXT-MAP.md``: the prefix must be a
    full path component.

    Args:
        item_name: Declared or discovered item name (relative path).
        rel: Path relative to the target root.

    Returns:
        True when *rel* belongs to *item_name*.
    """
    return rel == item_name or rel.startswith(f"{item_name}/")


def item_paths_overlap(left: str, right: str) -> bool:
    """Return whether two item names are equal or one is a path prefix of the other.

    Args:
        left: First item name (relative path).
        right: Second item name (relative path).

    Returns:
        True when the names collide on a target tree.
    """
    return item_covers_rel(left, right) or item_covers_rel(right, left)


def projects_targeting(projects: dict[str, ConfigProject], cwd: Path) -> list[ConfigProject]:
    """Return managed projects whose mappings include *cwd*, sorted by name.

    Args:
        projects: Loaded configuration projects.
        cwd: Target directory to match.

    Returns:
        Unique matching projects in stable name order.
    """
    matches: list[ConfigProject] = []
    seen: set[str] = set()
    for project in projects.values():
        if not any(cwd in mapping.targets for mapping in project.mappings):
            continue
        name = project.managed_project_name
        if name in seen:
            continue
        seen.add(name)
        matches.append(project)
    matches.sort(key=lambda project: project.managed_project_name)
    return matches


def mapping_item_names(project: ConfigProject, cwd: Path) -> list[str]:
    """Item names *project* contributes to *cwd*.

    Selective mappings use declared subpaths. Sync-all mappings use top-level
    hub entries after skipping the held-copy directory.

    Args:
        project: One managed project.
        cwd: Target directory whose mapping is inspected.

    Returns:
        Item names that mapping contributes, in mapping order.
    """
    names: list[str] = []
    for mapping in project.mappings:
        if cwd not in mapping.targets:
            continue
        if mapping.subpaths is not None:
            for subpath in mapping.subpaths:
                if not subpath or is_held_item_name(Path(subpath).parts[0]):
                    continue
                names.append(subpath)
            continue
        hub = project.managed_project_path
        if not hub.is_dir():
            continue
        names.extend(path.name for path in hub.iterdir() if not is_held_item_name(path.name))
    return names


def contribution_owner(
    projects: dict[str, ConfigProject],
    cwd: Path,
    rel: str,
) -> ConfigProject | None:
    """Return the unique managed project whose item covers *rel* on *cwd*.

    Args:
        projects: Loaded configuration projects.
        cwd: Target directory.
        rel: Path relative to *cwd* (posix).

    Returns:
        The unique owner, or ``None`` when no contributor or more than one
        contributor covers *rel*.
    """
    owners = [
        project
        for project in projects_targeting(projects, cwd)
        if any(item_covers_rel(name, rel) for name in mapping_item_names(project, cwd))
    ]
    if len(owners) == 1:
        return owners[0]
    return None


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
