"""Fresh and update catch-up of copy projections."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from beyond_local_file.copy_manager import CopyManager
from beyond_local_file.model.config import ConfigProject
from beyond_local_file.model.processing import ProcessingUnit
from beyond_local_file.model.translator import translate_config_to_processing
from beyond_local_file.sync_state import compute_file_hash

from .store import (
    BaselineTrees,
    PathState,
    get_state,
    path_state,
    state_equal,
)


def run_catch_up(
    projects: dict[str, ConfigProject],
    config_dir: Path,
    baseline: BaselineTrees | None,
) -> BaselineTrees:
    """Apply fresh or update catch-up and return the new baseline trees.

    Args:
        projects: Committed mappings to catch up.
        config_dir: Directory containing the config file.
        baseline: Previous baseline, or None for a first catch-up.

    Returns:
        Newly recorded per-path baseline trees.
    """
    if baseline is None:
        print("catch-up: fresh", flush=True)
        _fresh_catch_up(projects, config_dir)
    else:
        print("catch-up: update", flush=True)
        _update_catch_up(projects, baseline)
    return record_baseline(projects)


def record_baseline(projects: dict[str, ConfigProject]) -> BaselineTrees:
    """Scan hub and replica item trees and record hashes and presence.

    Args:
        projects: Committed mappings whose trees should be recorded.

    Returns:
        Baseline trees keyed by absolute root path.
    """
    trees: BaselineTrees = {}
    for unit in translate_config_to_processing(projects):
        item_names = [item.name for item in unit.items]
        _merge_tree(trees, unit.managed_project_path, _scan_items(unit.managed_project_path, item_names))
        _merge_tree(trees, unit.target_project_path, _scan_items(unit.target_project_path, item_names))
    return trees


def _fresh_catch_up(projects: dict[str, ConfigProject], config_dir: Path) -> None:
    for unit in translate_config_to_processing(projects):
        if not unit.managed_project_path.exists():
            print(f"Project directory does not exist: {unit.managed_project_path}", flush=True)
            continue
        if not unit.target_project_path.exists():
            print(f"Target directory does not exist: {unit.target_project_path}", flush=True)
            continue
        copy_mgr = CopyManager(list(unit.items), unit.target_project_path, config_dir)
        for item in unit.items:
            destination = unit.target_project_path / item.name
            _replace_with_copy(item.path, destination)
            copy_mgr.sync_state.update_record(item.path, destination)
            print(f"catch-up: copied {item.name} -> {destination}", flush=True)
        copy_mgr.sync_state.save()
        copy_mgr.add_git_excludes()


def _update_catch_up(projects: dict[str, ConfigProject], baseline: BaselineTrees) -> None:
    for unit in translate_config_to_processing(projects):
        _apply_update_unit(unit, baseline)


def _apply_update_unit(unit: ProcessingUnit, baseline: BaselineTrees) -> None:
    hub = unit.managed_project_path
    replica = unit.target_project_path
    item_names = [item.name for item in unit.items]
    hub_now = _scan_items(hub, item_names)
    replica_now = _scan_items(replica, item_names)
    paths = set(hub_now) | set(replica_now)
    paths |= _baseline_paths_for_items(baseline, hub, item_names)
    paths |= _baseline_paths_for_items(baseline, replica, item_names)

    deletes: list[str] = []
    writes: list[tuple[str, PathState]] = []
    for rel in paths:
        hub_state = hub_now.get(rel) or path_state(False, None)
        replica_state = replica_now.get(rel) or path_state(False, None)
        hub_changed = not state_equal(hub_state, get_state(baseline, hub, rel))
        replica_at_baseline = state_equal(replica_state, get_state(baseline, replica, rel))
        if not (hub_changed and replica_at_baseline):
            continue
        if hub_state.get("present"):
            writes.append((rel, hub_state))
        else:
            deletes.append(rel)

    for rel in sorted(deletes, key=_path_depth, reverse=True):
        _remove_path(replica / rel)
        print(f"catch-up: removed {rel} from {replica}", flush=True)
    for rel, hub_state in sorted(writes, key=lambda item: _path_depth(item[0])):
        _apply_hub_state(hub / rel, replica / rel, hub_state)
        print(f"catch-up: applied {rel} -> {replica / rel}", flush=True)


def _apply_hub_state(source: Path, destination: Path, hub_state: PathState) -> None:
    if hub_state.get("hash") is None:
        destination.mkdir(parents=True, exist_ok=True)
        return
    _replace_with_copy(source, destination)


def _replace_with_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or destination.is_file():
        destination.unlink()
    elif destination.is_dir():
        shutil.rmtree(destination)
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _scan_items(root: Path, item_names: list[str]) -> dict[str, PathState]:
    scanned: dict[str, PathState] = {}
    for name in item_names:
        _scan_path(root, root / name, scanned)
    return scanned


def _scan_path(root: Path, path: Path, scanned: dict[str, PathState]) -> None:
    if not path.exists() and not path.is_symlink():
        return
    rel = path.relative_to(root).as_posix()
    if path.is_symlink():
        scanned[rel] = path_state(True, "symlink:" + os.fsdecode(os.readlink(path)))
        return
    if path.is_file():
        scanned[rel] = path_state(True, compute_file_hash(path))
        return
    if path.is_dir():
        scanned[rel] = path_state(True, None)
        for child in sorted(path.iterdir()):
            _scan_path(root, child, scanned)


def _baseline_paths_for_items(baseline: BaselineTrees, root: Path, item_names: list[str]) -> set[str]:
    stored = baseline.get(str(root), {})
    return {rel for rel in stored if _rel_in_items(rel, item_names)}


def _rel_in_items(rel: str, item_names: list[str]) -> bool:
    return any(rel == name or rel.startswith(f"{name}/") for name in item_names)


def _path_depth(rel: str) -> int:
    return rel.count("/")


def _merge_tree(trees: BaselineTrees, root: Path, scanned: dict[str, PathState]) -> None:
    slot = trees.setdefault(str(root), {})
    slot.update(scanned)
