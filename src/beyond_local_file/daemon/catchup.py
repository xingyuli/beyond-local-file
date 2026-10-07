"""Fresh and update catch-up of copy projections."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from beyond_local_file.model.config import ConfigProject
from beyond_local_file.model.processing import MappingUnit
from beyond_local_file.model.translator import translate_config_to_mapping_units

from .live import LiveSync, ScanStats, rel_in_items, scan_items
from .log import log_duration
from .store import BaselineTrees, PathState, path_state

type ProgressFn = Callable[[int, int, str], None]
type LineFn = Callable[[str], None]


def run_catch_up(
    projects: dict[str, ConfigProject],
    config_dir: Path,
    baseline: BaselineTrees | None,
    on_progress: ProgressFn | None = None,
    on_line: LineFn | None = None,
) -> BaselineTrees:
    """Apply fresh or update catch-up and return LiveSync's baseline trees.

    Args:
        projects: Committed mappings to catch up.
        config_dir: Set run directory (unused by copy; kept for call-site compatibility).
        baseline: Previous baseline, or None for a first catch-up.
        on_progress: Optional callback of ``(unit_index, unit_count, item_name)``.
        on_line: Optional shell-screen line, one per worker-unit transition.

    Returns:
        LiveSync baseline trees after seed and, when a baseline existed, tick.
    """
    del config_dir
    live = LiveSync(projects, baseline or {}, last_seen_from_baseline=True)
    return catch_up_live(
        live,
        started_with_baseline=baseline is not None,
        on_progress=on_progress,
        on_line=on_line,
    )


def catch_up_live(
    live: LiveSync,
    *,
    started_with_baseline: bool,
    on_progress: ProgressFn | None = None,
    on_line: LineFn | None = None,
) -> BaselineTrees:
    """Seed unrecorded replicas on *live*, then tick when a baseline existed.

    Args:
        live: Observer whose mappings and last-seen to use.
        started_with_baseline: False for fresh catch-up (seed only). True for
            update catch-up or an existing worker unit (seed then tick).
        on_progress: Optional callback of ``(unit_index, unit_count, item_name)``.
        on_line: Optional shell-screen line, one per worker-unit transition.

    Returns:
        *live*'s baseline trees after seed and optional tick.
    """
    _mark_catchup_started(live.projects)
    units = translate_config_to_mapping_units(live.projects)
    _announce_waiting(units, on_line)
    if started_with_baseline:
        print("catch-up: update", flush=True)
    else:
        print("catch-up: fresh", flush=True)
    _seed_unrecorded(live, units, on_progress, on_line, started_with_baseline=started_with_baseline)
    if started_with_baseline:
        live.tick(reason="catch-up")
        live.apply_frozen_mismatches()
        for index in range(1, len(units) + 1):
            _mark_unit_done(units, index, on_line)
    return live.baseline


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


def _seed_unrecorded(
    live: LiveSync,
    units: list[MappingUnit],
    on_progress: ProgressFn | None,
    on_line: LineFn | None,
    *,
    started_with_baseline: bool,
) -> None:
    """Seed replicas and items this LiveSync has never recorded.

    Args:
        live: Observer whose baseline decides what is still unrecorded.
        units: Mapping units to seed.
        on_progress: Optional callback of ``(unit_index, unit_count, item_name)``.
        on_line: Optional shell-screen line.
        started_with_baseline: True when this is update catch-up (or an existing
            worker unit). Fresh replicas then log as such.
    """
    total = len(units)
    for index, unit in enumerate(units, start=1):
        emit = _item_progress(unit, on_progress, on_line)
        if not unit.managed_project_path.exists():
            print(f"Project directory does not exist: {unit.managed_project_path}", flush=True)
            if not started_with_baseline:
                _mark_unit_done(units, index, on_line)
            continue
        if not unit.target_project_path.exists():
            print(f"Target directory does not exist: {unit.target_project_path}", flush=True)
            if not started_with_baseline:
                _mark_unit_done(units, index, on_line)
            continue
        replica_key = str(unit.target_project_path)
        replica_tree = live.baseline.get(replica_key, {})
        if started_with_baseline and replica_key not in live.baseline:
            print(f"catch-up: fresh replica {unit.target_project_path}", flush=True)
        _emit_unit_items(unit, index, total, emit)
        for item in unit.items:
            if _item_recorded(replica_tree, item.name):
                continue
            live.seed_item(unit.target_project_path, item.name)
            destination = unit.target_project_path / item.name
            print(f"catch-up: copied {item.name} -> {destination}", flush=True)
            replica_tree = live.baseline.get(replica_key, {})
        if not started_with_baseline:
            _mark_unit_done(units, index, on_line)


def _item_recorded(tree: dict[str, PathState], item_name: str) -> bool:
    return any(rel_in_items(rel, [item_name]) for rel in tree)


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


def _mark_catchup_started(projects: dict[str, ConfigProject]) -> None:
    raw = os.environ.get("BLF_TEST_CATCHUP_STARTED")
    if not raw:
        return
    root = Path(raw)
    root.mkdir(parents=True, exist_ok=True)
    for project in projects.values():
        (root / project.managed_project_name).write_text("1", encoding="utf-8")


def _merge_tree(trees: BaselineTrees, root: Path, scanned: dict[str, PathState]) -> None:
    slot = trees.setdefault(str(root), {})
    slot.update(scanned)
