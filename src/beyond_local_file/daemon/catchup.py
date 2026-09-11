"""Fresh and update catch-up of copy projections."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from beyond_local_file.copy_manager import CopyManager
from beyond_local_file.held import HELD_DIR
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
        _update_catch_up(projects, config_dir, baseline)
    return record_baseline(projects, previous=baseline)


def record_baseline(
    projects: dict[str, ConfigProject],
    previous: BaselineTrees | None = None,
) -> BaselineTrees:
    """Scan hub and replica item trees and record hashes and presence.

    Args:
        projects: Committed mappings whose trees should be recorded.
        previous: Baseline whose per-path generations should be kept.

    Returns:
        Baseline trees keyed by absolute root path.
    """
    trees: BaselineTrees = {}
    for unit in translate_config_to_processing(projects):
        item_names = [item.name for item in unit.items]
        _merge_tree(trees, unit.managed_project_path, scan_items(unit.managed_project_path, item_names))
        _merge_tree(trees, unit.target_project_path, scan_items(unit.target_project_path, item_names))
    _preserve_generations(trees, previous)
    return trees


def _preserve_generations(trees: BaselineTrees, previous: BaselineTrees | None) -> None:
    previous = previous or {}
    for root, paths in trees.items():
        prev_paths = previous.get(root, {})
        for rel, state in paths.items():
            prev = prev_paths.get(rel) or {}
            try:
                state["gen"] = int(prev.get("gen") or 0)
            except (TypeError, ValueError):
                state["gen"] = 0
            if prev.get("oos"):
                state["oos"] = True
    for root, prev_paths in previous.items():
        slot = trees.setdefault(root, {})
        for rel, prev in prev_paths.items():
            if rel in slot:
                continue
            oos = bool(prev.get("oos"))
            if prev.get("present") and not oos:
                continue
            try:
                gen = int(prev.get("gen") or 0)
            except (TypeError, ValueError):
                gen = 0
            slot[rel] = path_state(False, None, gen, oos=oos)


def _fresh_catch_up(projects: dict[str, ConfigProject], config_dir: Path) -> None:
    for unit in translate_config_to_processing(projects):
        _fresh_catch_up_unit(unit, config_dir)


def _update_catch_up(projects: dict[str, ConfigProject], config_dir: Path, baseline: BaselineTrees) -> None:
    for unit in translate_config_to_processing(projects):
        if str(unit.target_project_path) not in baseline:
            print(f"catch-up: fresh replica {unit.target_project_path}", flush=True)
            _fresh_catch_up_unit(unit, config_dir)
        else:
            _apply_update_unit(unit, baseline)


def _fresh_catch_up_unit(unit: ProcessingUnit, config_dir: Path) -> None:
    if not unit.managed_project_path.exists():
        print(f"Project directory does not exist: {unit.managed_project_path}", flush=True)
        return
    if not unit.target_project_path.exists():
        print(f"Target directory does not exist: {unit.target_project_path}", flush=True)
        return
    copy_mgr = CopyManager(list(unit.items), unit.target_project_path, config_dir)
    for item in unit.items:
        destination = unit.target_project_path / item.name
        replace_with_copy(item.path, destination)
        copy_mgr.sync_state.update_record(item.path, destination)
        print(f"catch-up: copied {item.name} -> {destination}", flush=True)
    copy_mgr.sync_state.save()
    copy_mgr.add_git_excludes()


def _apply_update_unit(unit: ProcessingUnit, baseline: BaselineTrees) -> None:
    hub = unit.managed_project_path
    replica = unit.target_project_path
    item_names = [item.name for item in unit.items]
    hub_now = scan_items(hub, item_names)
    replica_now = scan_items(replica, item_names)
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
        remove_path(replica / rel)
        print(f"catch-up: removed {rel} from {replica}", flush=True)
    for rel, hub_state in sorted(writes, key=lambda item: _path_depth(item[0])):
        _apply_hub_state(hub / rel, replica / rel, hub_state)
        print(f"catch-up: applied {rel} -> {replica / rel}", flush=True)


def _apply_hub_state(source: Path, destination: Path, hub_state: PathState) -> None:
    if hub_state.get("hash") is None:
        destination.mkdir(parents=True, exist_ok=True)
        return
    replace_with_copy(source, destination)


def replace_with_copy(source: Path, destination: Path) -> None:
    """Replace *destination* with a copy of *source*.

    Args:
        source: File or directory to copy.
        destination: Path that should become the copy.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or destination.is_file():
        destination.unlink()
    elif destination.is_dir():
        shutil.rmtree(destination)
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)


def remove_path(path: Path) -> None:
    """Remove a file or directory if it exists.

    Args:
        path: Path to unlink or rmtree.
    """
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def scan_items(root: Path, item_names: list[str]) -> dict[str, PathState]:
    """Scan named items under *root* into a relative-path tree.

    Args:
        root: Hub or replica directory.
        item_names: Item names relative to *root*.

    Returns:
        Present paths mapped to hash/presence state.
    """
    scanned: dict[str, PathState] = {}
    for name in item_names:
        _scan_path(root, root / name, scanned)
    return scanned


def scan_path_state(root: Path, rel: str) -> PathState:
    """Return the current on-disk state of one path under *root*.

    Args:
        root: Hub or replica directory.
        rel: Path relative to *root*.

    Returns:
        Presence and hash for *rel*, or absent when it does not exist.
    """
    scanned: dict[str, PathState] = {}
    _scan_path(root, root / rel, scanned)
    return scanned.get(rel) or path_state(False, None)


def _scan_path(root: Path, path: Path, scanned: dict[str, PathState]) -> None:
    if not path.exists() and not path.is_symlink():
        return
    rel = path.relative_to(root).as_posix()
    if rel == HELD_DIR or rel.startswith(f"{HELD_DIR}/"):
        return
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
    return {rel for rel in stored if rel_in_items(rel, item_names)}


def rel_in_items(rel: str, item_names: list[str] | tuple[str, ...]) -> bool:
    """Return whether *rel* is one of *item_names* or a path under one.

    Args:
        rel: Path relative to a replica root.
        item_names: Watched item names.

    Returns:
        True when *rel* belongs to a watched item.
    """
    return any(rel == name or rel.startswith(f"{name}/") for name in item_names)


def _path_depth(rel: str) -> int:
    return rel.count("/")


def _merge_tree(trees: BaselineTrees, root: Path, scanned: dict[str, PathState]) -> None:
    slot = trees.setdefault(str(root), {})
    slot.update(scanned)
