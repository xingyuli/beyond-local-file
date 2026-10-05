"""Fresh and update catch-up of copy projections."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from beyond_local_file.git_manager import GitExcludeManager
from beyond_local_file.held import HELD_DIR, REASON_CREATE_OVERWRITE, reason_clause, store_held_copy
from beyond_local_file.model.config import ConfigProject
from beyond_local_file.model.processing import ManagedProjectItem, MappingUnit
from beyond_local_file.model.translator import translate_config_to_mapping_units
from beyond_local_file.projection import copy_projection
from beyond_local_file.sync_state import compute_file_hash

from .log import log_duration
from .store import (
    BaselineTrees,
    PathState,
    path_state,
    state_equal,
)

type ProgressFn = Callable[[int, int, str], None]
type LineFn = Callable[[str], None]


@dataclass
class ScanStats:
    """Size of one item-tree scan: paths visited, files hashed, bytes read."""

    paths: int = 0
    files: int = 0
    hashed_bytes: int = 0


def run_catch_up(
    projects: dict[str, ConfigProject],
    config_dir: Path,
    baseline: BaselineTrees | None,
    on_progress: ProgressFn | None = None,
    on_line: LineFn | None = None,
) -> BaselineTrees:
    """Apply fresh or update catch-up and return the new baseline trees.

    Args:
        projects: Committed mappings to catch up.
        config_dir: Set run directory (unused by copy; kept for call-site compatibility).
        baseline: Previous baseline, or None for a first catch-up.
        on_progress: Optional callback of ``(unit_index, unit_count, item_name)``.
        on_line: Optional shell-screen line, one per worker-unit transition.

    Returns:
        Newly recorded per-path baseline trees.
    """
    del config_dir
    _mark_catchup_started(projects)
    units = translate_config_to_mapping_units(projects)
    _announce_waiting(units, on_line)
    if baseline is None:
        print("catch-up: fresh", flush=True)
        _fresh_catch_up(on_progress, on_line, units)
        return record_baseline(projects, previous=None)
    print("catch-up: update", flush=True)
    applied = _update_catch_up(baseline, on_progress, on_line, units, projects)
    return record_baseline(projects, previous=applied)


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
    stats = ScanStats()
    with log_duration("baseline: record") as fields:
        for unit in translate_config_to_mapping_units(projects):
            item_names = [item.name for item in unit.items]
            _merge_tree(trees, unit.managed_project_path, scan_items(unit.managed_project_path, item_names, stats))
            _merge_tree(trees, unit.target_project_path, scan_items(unit.target_project_path, item_names, stats))
        _preserve_generations(trees, previous)
        fields["paths"] = stats.paths
        fields["files"] = stats.files
        fields["hashed_bytes"] = stats.hashed_bytes
    return trees


def record_item_baseline(
    projects: dict[str, ConfigProject],
    previous: BaselineTrees | None,
    item_name: str,
) -> BaselineTrees:
    """Rescan one item on each hub and target that declares it.

    Args:
        projects: Committed mappings whose trees should be updated.
        previous: Baseline whose other paths and generations should be kept.
        item_name: Declared item name relative to the managed project.

    Returns:
        Baseline trees with *item_name* replaced from disk.
    """
    trees: BaselineTrees = {root: dict(paths) for root, paths in (previous or {}).items()}
    stats = ScanStats()
    with log_duration("baseline: record") as fields:
        seen_hubs: set[str] = set()
        seen_targets: set[str] = set()
        for unit in translate_config_to_mapping_units(projects):
            if not any(item.name == item_name for item in unit.items):
                continue
            hub_key = str(unit.managed_project_path)
            if hub_key not in seen_hubs:
                _replace_item_tree(
                    trees,
                    unit.managed_project_path,
                    item_name,
                    scan_items(unit.managed_project_path, [item_name], stats),
                )
                seen_hubs.add(hub_key)
            target_key = str(unit.target_project_path)
            if target_key not in seen_targets:
                _replace_item_tree(
                    trees,
                    unit.target_project_path,
                    item_name,
                    scan_items(unit.target_project_path, [item_name], stats),
                )
                seen_targets.add(target_key)
        if not seen_hubs:
            for slot in trees.values():
                _drop_item_paths(slot, item_name)
        _preserve_generations(trees, previous)
        fields["paths"] = stats.paths
        fields["files"] = stats.files
        fields["hashed_bytes"] = stats.hashed_bytes
    return trees


def _replace_item_tree(
    trees: BaselineTrees,
    root: Path,
    item_name: str,
    scanned: dict[str, PathState],
) -> None:
    slot = trees.setdefault(str(root), {})
    for rel in [path for path in slot if path == item_name or path.startswith(f"{item_name}/")]:
        del slot[rel]
    slot.update(scanned)


def _drop_item_paths(slot: dict[str, PathState], item_name: str) -> None:
    for rel in [path for path in slot if path == item_name or path.startswith(f"{item_name}/")]:
        del slot[rel]


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
            _copy_oos_metadata(state, prev)
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
            recorded = path_state(False, None, gen, oos=oos)
            _copy_oos_metadata(recorded, prev)
            slot[rel] = recorded


def _copy_oos_metadata(state: PathState, prev: PathState) -> None:
    """Copy out-of-sync reason and clause from a previous row."""
    if not prev.get("oos"):
        return
    state["oos"] = True
    for key in ("reason", "clause"):
        if key in prev:
            state[key] = prev[key]


def _announce_waiting(units: list[MappingUnit], on_line: LineFn | None) -> None:
    if on_line is None:
        return
    seen: list[str] = []
    for unit in units:
        name = unit.managed_project_name
        if name in seen:
            continue
        seen.append(name)
        on_line(f"Waiting · {name}")


def _mark_unit_done(units: list[MappingUnit], index: int, on_line: LineFn | None) -> None:
    if on_line is None or not units:
        return
    project = units[index - 1].managed_project_name
    if index == len(units) or units[index].managed_project_name != project:
        on_line(f"Done · {project}")


def _note_item(on_line: LineFn | None, unit: MappingUnit, item_name: str) -> None:
    if on_line is not None:
        on_line(f"Catching up {item_name} · {unit.managed_project_name}")


def _item_progress(
    unit: MappingUnit,
    on_progress: ProgressFn | None,
    on_line: LineFn | None,
) -> ProgressFn:
    def emit(index: int, total: int, item: str) -> None:
        if on_progress is not None:
            on_progress(index, total, item)
        _note_item(on_line, unit, item)

    return emit


def _fresh_catch_up(
    on_progress: ProgressFn | None,
    on_line: LineFn | None,
    units: list[MappingUnit],
) -> None:
    total = len(units)
    for index, unit in enumerate(units, start=1):
        _fresh_catch_up_unit(
            unit,
            index=index,
            total=total,
            on_progress=_item_progress(unit, on_progress, on_line),
        )
        _mark_unit_done(units, index, on_line)


def _update_catch_up(
    baseline: BaselineTrees,
    on_progress: ProgressFn | None,
    on_line: LineFn | None,
    units: list[MappingUnit],
    projects: dict[str, ConfigProject],
) -> BaselineTrees:
    from .live import LiveSync  # noqa: PLC0415 -- avoid import cycle with live observe

    working: BaselineTrees = {root: dict(paths) for root, paths in baseline.items()}
    total = len(units)
    for index, unit in enumerate(units, start=1):
        emit = _item_progress(unit, on_progress, on_line)
        replica_key = str(unit.target_project_path)
        if replica_key not in working:
            print(f"catch-up: fresh replica {unit.target_project_path}", flush=True)
            _fresh_catch_up_unit(unit, index=index, total=total, on_progress=emit)
            item_names = [item.name for item in unit.items]
            working[replica_key] = scan_items(unit.target_project_path, item_names)
        else:
            _emit_unit_items(unit, index, total, emit)
            if _install_unrecorded_items(unit, working):
                _add_git_excludes(unit)
    live = LiveSync(projects, working, last_seen_from_baseline=True)
    live.tick(reason="catch-up")
    live.apply_frozen_mismatches()
    for index in range(1, len(units) + 1):
        _mark_unit_done(units, index, on_line)
    return live.baseline


def _fresh_catch_up_unit(
    unit: MappingUnit,
    *,
    index: int = 1,
    total: int = 1,
    on_progress: ProgressFn | None = None,
) -> None:
    if not unit.managed_project_path.exists():
        print(f"Project directory does not exist: {unit.managed_project_path}", flush=True)
        return
    if not unit.target_project_path.exists():
        print(f"Target directory does not exist: {unit.target_project_path}", flush=True)
        return
    for item in unit.items:
        if on_progress is not None:
            on_progress(index, total, item.name)
        destination = unit.target_project_path / item.name
        _install_projection(unit, item)
        print(f"catch-up: copied {item.name} -> {destination}", flush=True)
    _add_git_excludes(unit)


def _install_projection(unit: MappingUnit, item: ManagedProjectItem) -> None:
    """Copy hub bytes onto the replica, holding different replica bytes first.

    Equal bytes are left in place. A missing projection is copied with no hold.
    """
    destination = unit.target_project_path / item.name
    source_ready = item.path.exists() or item.path.is_symlink()
    dest_ready = destination.exists() or destination.is_symlink()
    if dest_ready and source_ready and item_matches(unit.managed_project_path, unit.target_project_path, item.name):
        return
    if dest_ready and source_ready:
        replica = unit.target_project_path
        clause = reason_clause(
            REASON_CREATE_OVERWRITE,
            path=item.name,
            replica=replica.as_posix(),
        )
        slot = store_held_copy(
            unit.managed_project_path,
            rel_path=Path(item.name),
            source=destination,
            replica=replica,
            reason=REASON_CREATE_OVERWRITE,
        )
        print(f"WARNING: {clause}", flush=True)
        print(f"Held at {slot.as_posix()}", flush=True)
    copy_projection(item.path, destination)


def item_matches(hub_root: Path, replica_root: Path, item_name: str) -> bool:
    """Return whether *item_name* has the same per-file SHA-256 tree on both roots.

    Args:
        hub_root: Managed-project directory.
        replica_root: Target-project directory.
        item_name: Item path relative to each root.

    Returns:
        True when both trees contain the same relative paths with equal state.
    """
    hub_tree = scan_items(hub_root, [item_name])
    replica_tree = scan_items(replica_root, [item_name])
    if set(hub_tree) != set(replica_tree):
        return False
    return all(state_equal(hub_tree[rel], replica_tree[rel]) for rel in hub_tree)


def _item_recorded(tree: dict[str, PathState], item_name: str) -> bool:
    return any(rel_in_items(rel, [item_name]) for rel in tree)


def _install_unrecorded_items(unit: MappingUnit, working: BaselineTrees) -> list[str]:
    """Install items this replica has never recorded, holding colliding bytes.

    Returns:
        Item names installed onto the replica.
    """
    replica_key = str(unit.target_project_path)
    replica_tree = working.get(replica_key, {})
    names: list[str] = []
    for item in unit.items:
        if _item_recorded(replica_tree, item.name):
            continue
        destination = unit.target_project_path / item.name
        _install_projection(unit, item)
        names.append(item.name)
        print(f"catch-up: copied {item.name} -> {destination}", flush=True)
    if not names:
        return names
    hub_key = str(unit.managed_project_path)
    hub_new = [name for name in names if not _item_recorded(working.get(hub_key, {}), name)]
    if hub_new:
        _merge_tree(working, unit.managed_project_path, scan_items(unit.managed_project_path, hub_new))
    _merge_tree(working, unit.target_project_path, scan_items(unit.target_project_path, names))
    return names


def _emit_unit_items(
    unit: MappingUnit,
    index: int,
    total: int,
    on_progress: ProgressFn | None,
) -> None:
    if on_progress is None:
        return
    for item in unit.items:
        on_progress(index, total, item.name)


def _add_git_excludes(unit: MappingUnit) -> None:
    manager = GitExcludeManager(unit.target_project_path)
    if not manager.is_git_repo():
        return
    manager.write_entries({item.name for item in unit.items})


def remove_path(path: Path) -> None:
    """Remove a file or directory if it exists.

    Args:
        path: Path to unlink or rmtree.
    """
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def scan_items(
    root: Path,
    item_names: list[str],
    stats: ScanStats | None = None,
) -> dict[str, PathState]:
    """Scan named items under *root* into a relative-path tree.

    Args:
        root: Hub or replica directory.
        item_names: Item names relative to *root*.
        stats: Optional accumulator for path count, file count, and hashed bytes.

    Returns:
        Present paths mapped to hash/presence state.
    """
    scanned: dict[str, PathState] = {}
    for name in item_names:
        _scan_path(root, root / name, scanned, stats)
    return scanned


def _mark_catchup_started(projects: dict[str, ConfigProject]) -> None:
    raw = os.environ.get("BLF_TEST_CATCHUP_STARTED")
    if not raw:
        return
    root = Path(raw)
    root.mkdir(parents=True, exist_ok=True)
    for project in projects.values():
        (root / project.managed_project_name).write_text("1", encoding="utf-8")


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


def _scan_path(
    root: Path,
    path: Path,
    scanned: dict[str, PathState],
    stats: ScanStats | None = None,
) -> None:
    if not path.exists() and not path.is_symlink():
        return
    rel = path.relative_to(root).as_posix()
    if rel == HELD_DIR or rel.startswith(f"{HELD_DIR}/"):
        return
    if path.is_symlink():
        scanned[rel] = path_state(True, "symlink:" + os.fsdecode(os.readlink(path)))
        _count_path(stats)
        return
    if path.is_file():
        size = path.stat().st_size
        scanned[rel] = path_state(True, compute_file_hash(path))
        _count_path(stats, files=1, hashed_bytes=size)
        return
    if path.is_dir():
        scanned[rel] = path_state(True, None)
        _count_path(stats)
        for child in sorted(path.iterdir()):
            _scan_path(root, child, scanned, stats)


def rel_in_items(rel: str, item_names: list[str] | tuple[str, ...]) -> bool:
    """Return whether *rel* is one of *item_names* or a path under one.

    Args:
        rel: Path relative to a replica root.
        item_names: Watched item names.

    Returns:
        True when *rel* belongs to a watched item.
    """
    return any(rel == name or rel.startswith(f"{name}/") for name in item_names)


def _merge_tree(trees: BaselineTrees, root: Path, scanned: dict[str, PathState]) -> None:
    slot = trees.setdefault(str(root), {})
    slot.update(scanned)


def _count_path(stats: ScanStats | None, *, files: int = 0, hashed_bytes: int = 0) -> None:
    if stats is None:
        return
    stats.paths += 1
    stats.files += files
    stats.hashed_bytes += hashed_bytes
