"""Mapping snapshot and per-path baseline persisted next to the config."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from beyond_local_file.model.config import ConfigProject, Mapping

from .process import state_dir

SNAPSHOT_NAME = "mapping-snapshot.yml"
BASELINE_NAME = "baseline.yml"

type SnapshotData = dict[str, Any]
type PathState = dict[str, Any]
type BaselineTrees = dict[str, dict[str, PathState]]


def snapshot_path(config_path: Path) -> Path:
    """Return the mapping-snapshot path next to the loaded config.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        Path to ``mapping-snapshot.yml``.
    """
    return state_dir(config_path) / SNAPSHOT_NAME


def baseline_path(config_path: Path) -> Path:
    """Return the baseline path next to the loaded config.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        Path to ``baseline.yml``.
    """
    return state_dir(config_path) / BASELINE_NAME


def snapshot_from_projects(projects: dict[str, ConfigProject]) -> SnapshotData:
    """Serialize committed mappings to a comparable snapshot document.

    Args:
        projects: Loaded or restored config projects.

    Returns:
        Canonical snapshot mapping.
    """
    data: SnapshotData = {}
    for name in sorted(projects):
        project = projects[name]
        data[name] = {
            "managed_project_path": str(project.managed_project_path),
            "mappings": [
                {
                    "targets": [str(target) for target in mapping.targets],
                    "subpaths": mapping.subpaths,
                }
                for mapping in project.mappings
            ],
        }
    return data


def projects_from_snapshot(data: SnapshotData) -> dict[str, ConfigProject]:
    """Restore config projects from a snapshot document.

    Args:
        data: Canonical snapshot mapping.

    Returns:
        Config projects keyed by managed project name.
    """
    projects: dict[str, ConfigProject] = {}
    for name, raw in data.items():
        mappings = [
            Mapping(
                targets=[Path(target) for target in mapping.get("targets") or []],
                subpaths=mapping.get("subpaths"),
            )
            for mapping in raw.get("mappings") or []
        ]
        projects[name] = ConfigProject(
            managed_project_name=name,
            managed_project_path=Path(raw["managed_project_path"]),
            mappings=mappings,
        )
    return projects


def load_snapshot(config_path: Path) -> dict[str, ConfigProject] | None:
    """Load the mapping snapshot if it exists.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        Restored projects, or None when no snapshot is on disk.
    """
    path = snapshot_path(config_path)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        return None
    return projects_from_snapshot(data)


def save_snapshot(config_path: Path, projects: dict[str, ConfigProject]) -> None:
    """Write the mapping snapshot for the committed projects.

    Args:
        config_path: Path to the loaded config file.
        projects: Mappings that catch-up used.
    """
    path = snapshot_path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(snapshot_from_projects(projects), handle, default_flow_style=False, sort_keys=True)


def mappings_equal(left: dict[str, ConfigProject], right: dict[str, ConfigProject]) -> bool:
    """Return whether two project maps encode the same committed mappings.

    Args:
        left: First project map.
        right: Second project map.

    Returns:
        True when the canonical snapshots match.
    """
    return snapshot_from_projects(left) == snapshot_from_projects(right)


def load_baseline(config_path: Path) -> BaselineTrees | None:
    """Load the per-path baseline if it exists.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        Baseline trees keyed by replica root, or None when missing.
    """
    path = baseline_path(config_path)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    trees = data.get("trees") if isinstance(data, dict) else None
    if not isinstance(trees, dict) or not trees:
        return None
    return trees


def save_baseline(config_path: Path, trees: BaselineTrees) -> None:
    """Persist the per-path baseline.

    Args:
        config_path: Path to the loaded config file.
        trees: Baseline trees keyed by replica root.
    """
    path = baseline_path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump({"trees": trees}, handle, default_flow_style=False, sort_keys=True)


def path_state(present: bool, digest: str | None) -> PathState:
    """Build a baseline entry for one path.

    Args:
        present: Whether the path exists.
        digest: File hash, or None for a directory or an absent path.

    Returns:
        Serialisable path state.
    """
    return {"present": present, "hash": digest}


def state_equal(left: PathState | None, right: PathState | None) -> bool:
    """Return whether two path states match.

    Args:
        left: First state, or None for absent.
        right: Second state, or None for absent.

    Returns:
        True when presence and hash match.
    """
    return _normalize_state(left) == _normalize_state(right)


def get_state(trees: BaselineTrees, root: Path, rel: str) -> PathState:
    """Look up a path in a baseline, treating a missing key as absent.

    Args:
        trees: Baseline trees.
        root: Hub or replica root.
        rel: Path relative to *root*.

    Returns:
        Stored or absent path state.
    """
    return trees.get(str(root), {}).get(rel) or path_state(False, None)


def _normalize_state(state: PathState | None) -> tuple[bool, str | None]:
    if not state:
        return (False, None)
    return (bool(state.get("present")), state.get("hash"))
