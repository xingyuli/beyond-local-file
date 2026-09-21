"""Mapping snapshot and per-path baseline persisted in the set run directory."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

from beyond_local_file.model.config import ConfigProject, Mapping
from beyond_local_file.model.processing import ManagedProjectItem
from beyond_local_file.model.translator import translate_config_to_processing

from .log import log_duration
from .process import state_dir

SNAPSHOT_NAME = "mapping-snapshot.yml"
BASELINE_NAME = "baseline.yml"
BASELINE_DIR_NAME = "baseline"
FILES_DOCUMENT = "files"

type SnapshotData = dict[str, Any]
type PathState = dict[str, Any]
type BaselineTrees = dict[str, dict[str, PathState]]


def snapshot_path(config_path: Path) -> Path:
    """Return the mapping-snapshot path in the set run directory.

    Args:
        config_path: Path to the loaded mapping file.

    Returns:
        Path to ``mapping-snapshot.yml``.
    """
    return state_dir(config_path) / SNAPSHOT_NAME


def baseline_path(config_path: Path) -> Path:
    """Return the legacy baseline yaml path in the set run directory.

    Args:
        config_path: Path to the loaded mapping file.

    Returns:
        Path to ``baseline.yml``.
    """
    return state_dir(config_path) / BASELINE_NAME


def baseline_dir(config_path: Path) -> Path:
    """Return the item-document baseline directory in the set run directory.

    Args:
        config_path: Path to the loaded mapping file.

    Returns:
        Path to ``baseline/``.
    """
    return state_dir(config_path) / BASELINE_DIR_NAME


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
            "managed_project_name": project.managed_project_name,
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
            managed_project_name=str(raw.get("managed_project_name") or name),
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
    with log_duration("snapshot: write") as fields:
        with open(path, "w", encoding="utf-8") as handle:
            yaml.safe_dump(snapshot_from_projects(projects), handle, default_flow_style=False, sort_keys=True)
        fields["bytes"] = path.stat().st_size


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

    Prefers item documents under ``baseline/``. Falls back to ``baseline.yml``.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        Baseline trees keyed by replica root, or None when missing.
    """
    trees = _load_baseline_documents(baseline_dir(config_path))
    if trees:
        return trees
    return _load_baseline_yaml(baseline_path(config_path))


def save_baseline(
    config_path: Path,
    trees: BaselineTrees,
    projects: dict[str, ConfigProject] | None = None,
    *,
    changed_rels: Iterable[str] | None = None,
) -> None:
    """Persist the per-path baseline.

    With *projects*, write item documents under ``baseline/<managed-project>/``.
    Without *projects*, write the legacy ``baseline.yml``. *changed_rels* limits
    a document write to items covering those relative paths.

    Args:
        config_path: Path to the loaded config file.
        trees: Baseline trees keyed by replica root.
        projects: Committed mappings that group replica roots into documents.
        changed_rels: Relative paths whose documents should be rewritten. None
            rewrites every item document.
    """
    if projects is None:
        _save_baseline_yaml(config_path, trees)
        return
    _save_baseline_documents(config_path, trees, projects, changed_rels=changed_rels)
    baseline_path(config_path).unlink(missing_ok=True)


def path_state(present: bool, digest: str | None, gen: int = 0, oos: bool = False) -> PathState:
    """Build a baseline entry for one path.

    Args:
        present: Whether the path exists.
        digest: File hash, or None for a directory or an absent path.
        gen: Per-path hub generation last applied to this replica.
        oos: Whether this replica is out-of-sync for the path.

    Returns:
        Serialisable path state.
    """
    state: PathState = {"present": present, "hash": digest, "gen": gen}
    if oos:
        state["oos"] = True
    return state


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


def get_generation(trees: BaselineTrees, root: Path, rel: str) -> int:
    """Return the stored generation for a path, or 0 when missing.

    Args:
        trees: Baseline trees.
        root: Hub or replica root.
        rel: Path relative to *root*.

    Returns:
        Integer generation, defaulting to 0.
    """
    return _generation_of(get_state(trees, root, rel))


def is_out_of_sync(state: PathState | None) -> bool:
    """Return whether a path state is marked out-of-sync.

    Args:
        state: Baseline path state, or None.

    Returns:
        True when ``oos`` is set.
    """
    return bool(state and state.get("oos"))


def iter_out_of_sync(trees: BaselineTrees) -> tuple[tuple[Path, str], ...]:
    """Return replica/path pairs marked out-of-sync.

    Args:
        trees: Baseline trees.

    Returns:
        Sorted ``(replica_root, rel)`` pairs.
    """
    entries: list[tuple[Path, str]] = []
    for root, paths in trees.items():
        for rel, state in paths.items():
            if is_out_of_sync(state):
                entries.append((Path(root), rel))
    return tuple(sorted(entries, key=lambda item: (str(item[0]), item[1])))


def _generation_of(state: PathState | None) -> int:
    if not state:
        return 0
    try:
        return int(state.get("gen") or 0)
    except (TypeError, ValueError):
        return 0


def _normalize_state(state: PathState | None) -> tuple[bool, str | None]:
    if not state:
        return (False, None)
    return (bool(state.get("present")), state.get("hash"))


def _load_baseline_yaml(path: Path) -> BaselineTrees | None:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    trees = data.get("trees") if isinstance(data, dict) else None
    if not isinstance(trees, dict) or not trees:
        return None
    return trees


def _load_baseline_documents(root: Path) -> BaselineTrees | None:
    if not root.is_dir():
        return None
    trees: BaselineTrees = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        with open(path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        part = data.get("trees") if isinstance(data, dict) else None
        if not isinstance(part, dict):
            continue
        for replica, paths in part.items():
            if not isinstance(paths, dict):
                continue
            trees.setdefault(str(replica), {}).update(paths)
    return trees or None


def _save_baseline_yaml(config_path: Path, trees: BaselineTrees) -> None:
    path = baseline_path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with log_duration("baseline: write") as fields:
        with open(path, "w", encoding="utf-8") as handle:
            yaml.safe_dump({"trees": trees}, handle, default_flow_style=False, sort_keys=True)
        fields["bytes"] = path.stat().st_size


def _save_baseline_documents(
    config_path: Path,
    trees: BaselineTrees,
    projects: dict[str, ConfigProject],
    changed_rels: Iterable[str] | None = None,
) -> None:
    root = baseline_dir(config_path)
    root.mkdir(parents=True, exist_ok=True)
    documents = _item_documents(projects, trees)
    selected: dict[str, BaselineTrees]
    if changed_rels is None:
        selected = dict(documents)
    else:
        wanted = set(changed_rels)
        selected = {rel: doc_trees for rel, doc_trees in documents if _document_covers(doc_trees, wanted)}
        for item_name in wanted:
            selected.update(_documents_for_existing_item(root, projects, item_name, documents))
            _delete_stale_item_documents(root, projects, item_name, set(selected))
    with log_duration("baseline: write") as fields:
        total_bytes = 0
        for rel, doc_trees in selected.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                yaml.safe_dump({"trees": doc_trees}, handle, default_flow_style=False, sort_keys=True)
            total_bytes += path.stat().st_size
        fields["bytes"] = total_bytes


def _item_documents(
    projects: dict[str, ConfigProject],
    trees: BaselineTrees,
) -> list[tuple[str, BaselineTrees]]:
    items_by_project: dict[str, dict[str, ManagedProjectItem]] = {}
    for unit in translate_config_to_processing(projects):
        slot = items_by_project.setdefault(unit.managed_project_name, {})
        for item in unit.items:
            slot[item.name] = item
    documents: list[tuple[str, BaselineTrees]] = []
    for project in projects.values():
        items = items_by_project.get(project.managed_project_name) or {}
        roots = [str(project.managed_project_path)]
        roots.extend(str(target) for mapping in project.mappings for target in mapping.targets)
        buckets: dict[str, BaselineTrees] = {}
        for item in items.values():
            is_dir = _is_directory_item(item)
            for root in roots:
                for rel, state in (trees.get(root) or {}).items():
                    if not _rel_in_items(rel, {item.name}):
                        continue
                    doc_rel = _document_rel(item.name, is_dir, rel, trees, roots)
                    buckets.setdefault(doc_rel, {}).setdefault(root, {})[rel] = state
        for doc_rel, doc_trees in sorted(buckets.items()):
            documents.append((f"{project.managed_project_name}/{doc_rel}", doc_trees))
    return documents


def _document_rel(
    item_name: str,
    item_is_dir: bool,
    rel: str,
    trees: BaselineTrees,
    roots: list[str],
) -> str:
    if not item_is_dir:
        return FILES_DOCUMENT
    prefix = f"{item_name}/"
    if rel == item_name or not rel.startswith(prefix):
        return f"{item_name}/{FILES_DOCUMENT}"
    child = rel[len(prefix) :].split("/", 1)[0]
    child_rel = f"{item_name}/{child}"
    if _child_is_directory(trees, roots, child_rel):
        return child_rel
    return f"{item_name}/{FILES_DOCUMENT}"


def _child_is_directory(trees: BaselineTrees, roots: list[str], child_rel: str) -> bool:
    descendant = f"{child_rel}/"
    for root in roots:
        slot = trees.get(root) or {}
        state = slot.get(child_rel)
        if state and state.get("present") and state.get("hash") is None:
            return True
        if any(path.startswith(descendant) for path in slot):
            return True
    return False


def _documents_for_existing_item(
    root: Path,
    projects: dict[str, ConfigProject],
    item_name: str,
    documents: list[tuple[str, BaselineTrees]],
) -> dict[str, BaselineTrees]:
    new_docs = dict(documents)
    selected: dict[str, BaselineTrees] = {}
    for project in projects.values():
        name = project.managed_project_name
        item_dir = root / name / item_name
        files_rel = f"{name}/{FILES_DOCUMENT}"
        if item_dir.is_dir():
            for path in item_dir.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(root).as_posix()
                if rel in new_docs:
                    selected[rel] = new_docs[rel]
        elif files_rel in new_docs:
            selected[files_rel] = new_docs[files_rel]
    return selected


def _delete_stale_item_documents(
    root: Path,
    projects: dict[str, ConfigProject],
    item_name: str,
    written: set[str],
) -> None:
    for project in projects.values():
        item_dir = root / project.managed_project_name / item_name
        if not item_dir.is_dir():
            continue
        for path in list(item_dir.rglob("*")):
            if path.is_file() and path.relative_to(root).as_posix() not in written:
                path.unlink(missing_ok=True)
        for path in sorted((p for p in item_dir.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            if not any(path.iterdir()):
                path.rmdir()
        if item_dir.is_dir() and not any(item_dir.iterdir()):
            item_dir.rmdir()


def _document_covers(doc_trees: BaselineTrees, changed_rels: set[str]) -> bool:
    for replica in doc_trees.values():
        for path in replica:
            if path in changed_rels:
                return True
            if any(path.startswith(f"{rel}/") or rel.startswith(f"{path}/") for rel in changed_rels):
                return True
    return False


def _is_directory_item(item: ManagedProjectItem) -> bool:
    return item.path.is_dir() and not item.path.is_symlink()


def _rel_in_items(rel: str, item_names: set[str]) -> bool:
    return any(rel == name or rel.startswith(f"{name}/") for name in item_names)
