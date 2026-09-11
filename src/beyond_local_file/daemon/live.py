"""Live observe: mailbox, hub apply, generation, and fan-out."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from beyond_local_file.model.config import ConfigProject
from beyond_local_file.model.translator import translate_config_to_processing

from .catchup import (
    rel_in_items,
    remove_path,
    replace_with_copy,
    scan_items,
    scan_path_state,
)
from .store import BaselineTrees, PathState, get_generation, get_state, path_state, state_equal

DELETE_WINDOW = 3
"""Deletes win on the live path when hub_gen - base_gen is at most this value."""

type ChangeKind = Literal["create", "update", "delete"]


@dataclass(frozen=True)
class PathChange:
    """One not-yet-applied path change from a single replica."""

    rel: str
    replica: Path
    hub: Path
    kind: ChangeKind
    base_present: bool
    base_hash: str | None
    base_gen: int


@dataclass(frozen=True)
class _WatchRoot:
    root: Path
    hub: Path
    item_names: tuple[str, ...]
    is_hub: bool


class LiveSync:
    """Observe item trees, coalesce per (path, replica), apply at the hub, fan out."""

    def __init__(self, projects: dict[str, ConfigProject], baseline: BaselineTrees) -> None:
        """Start observing committed mappings from an existing baseline.

        Args:
            projects: Committed mappings to watch.
            baseline: Last applied hashes, presence, and generations.
        """
        self._baseline = baseline
        self._mailbox: dict[tuple[str, str], PathChange] = {}
        self._watch_roots = _build_watch_roots(projects)
        self._last_seen = self._scan_all()

    @property
    def baseline(self) -> BaselineTrees:
        """Return the in-memory baseline trees."""
        return self._baseline

    def tick(self) -> bool:
        """Observe current trees into the mailbox, then apply pending changes.

        Returns:
            True if any mailbox entry was applied or attempted.
        """
        self.observe()
        if not self._mailbox:
            return False
        self.apply()
        return True

    def observe(self) -> None:
        """Queue create/update/delete for paths that differ from the last scan."""
        for watch in self._watch_roots:
            scanned = scan_items(watch.root, list(watch.item_names))
            last = self._last_seen.get(str(watch.root), {})
            for rel in set(scanned) | set(last):
                new = scanned.get(rel) or path_state(False, None)
                old = last.get(rel) or path_state(False, None)
                if state_equal(old, new):
                    continue
                self._mailbox[(rel, str(watch.root))] = PathChange(
                    rel=rel,
                    replica=watch.root,
                    hub=watch.hub,
                    kind=_classify(old, new),
                    base_present=bool(old.get("present")),
                    base_hash=old.get("hash") if old.get("present") else None,
                    base_gen=get_generation(self._baseline, watch.root, rel),
                )
            self._last_seen[str(watch.root)] = scanned

    def apply(self) -> None:
        """Apply pending mailbox entries one at a time, first-apply-wins per path."""
        while self._mailbox:
            key = min(self._mailbox, key=lambda item: _apply_sort_key(self._mailbox[item]))
            change = self._mailbox.pop(key)
            self._apply_one(change)

    def reload(self, projects: dict[str, ConfigProject], baseline: BaselineTrees) -> None:
        """Replace mappings and treat current disks as already seen.

        Args:
            projects: Newly committed mappings.
            baseline: Baseline recorded after the mapping mutation.
        """
        self._baseline = baseline
        self._watch_roots = _build_watch_roots(projects)
        self._last_seen = self._scan_all()
        self._mailbox.clear()

    def _scan_all(self) -> BaselineTrees:
        trees: BaselineTrees = {}
        for watch in self._watch_roots:
            trees[str(watch.root)] = scan_items(watch.root, list(watch.item_names))
        return trees

    def _apply_one(self, change: PathChange) -> None:
        if change.replica == change.hub:
            self._commit_hub_source(change)
            return
        old_hub = scan_path_state(change.hub, change.rel)
        old_hub_gen = get_generation(self._baseline, change.hub, change.rel)
        if change.kind == "delete":
            if not _delete_allowed(change, old_hub, old_hub_gen):
                return
            remove_path(change.hub / change.rel)
        else:
            if not state_equal(old_hub, path_state(change.base_present, change.base_hash)):
                return
            source = change.replica / change.rel
            if not source.exists() and not source.is_symlink():
                return
            replace_with_copy(source, change.hub / change.rel)
        new_gen = old_hub_gen + 1
        new_hub = scan_path_state(change.hub, change.rel)
        self._record(change.hub, change.rel, new_hub, new_gen)
        self._record(change.replica, change.rel, scan_path_state(change.replica, change.rel), new_gen)
        print(f"live: {change.kind} {change.rel} gen {new_gen}", flush=True)
        self._fan_out(change, old_hub, new_hub, new_gen)

    def _commit_hub_source(self, change: PathChange) -> None:
        previous = get_state(self._baseline, change.hub, change.rel)
        old_hub = path_state(bool(previous.get("present")), previous.get("hash") if previous.get("present") else None)
        new_gen = get_generation(self._baseline, change.hub, change.rel) + 1
        new_hub = scan_path_state(change.hub, change.rel)
        self._record(change.hub, change.rel, new_hub, new_gen)
        print(f"live: {change.kind} {change.rel} gen {new_gen}", flush=True)
        self._fan_out(change, old_hub, new_hub, new_gen)

    def _fan_out(self, change: PathChange, old_hub: PathState, new_hub: PathState, new_gen: int) -> None:
        for watch in self._watch_roots:
            if watch.is_hub or watch.root == change.replica:
                continue
            if not rel_in_items(change.rel, watch.item_names):
                continue
            if (change.rel, str(watch.root)) in self._mailbox:
                continue
            disk = scan_path_state(watch.root, change.rel)
            if not state_equal(disk, old_hub):
                continue
            destination = watch.root / change.rel
            if new_hub.get("present"):
                source = change.hub / change.rel
                if source.exists() or source.is_symlink():
                    replace_with_copy(source, destination)
                else:
                    destination.mkdir(parents=True, exist_ok=True)
            else:
                remove_path(destination)
            self._record(watch.root, change.rel, scan_path_state(watch.root, change.rel), new_gen)

    def _record(self, root: Path, rel: str, state: PathState, gen: int) -> None:
        present = bool(state.get("present"))
        digest = state.get("hash") if present else None
        recorded = path_state(present, digest, gen)
        self._baseline.setdefault(str(root), {})[rel] = recorded
        seen = self._last_seen.setdefault(str(root), {})
        if present:
            seen[rel] = path_state(True, digest)
        else:
            seen.pop(rel, None)


def _build_watch_roots(projects: dict[str, ConfigProject]) -> list[_WatchRoot]:
    hubs: dict[str, _WatchRoot] = {}
    replicas: dict[str, _WatchRoot] = {}
    for unit in translate_config_to_processing(projects):
        names = tuple(item.name for item in unit.items)
        hub_key = str(unit.managed_project_path)
        hub = hubs.get(hub_key)
        if hub is None:
            hubs[hub_key] = _WatchRoot(unit.managed_project_path, unit.managed_project_path, names, True)
        else:
            merged = tuple(sorted(set(hub.item_names) | set(names)))
            hubs[hub_key] = _WatchRoot(hub.root, hub.hub, merged, True)
        replica_key = str(unit.target_project_path)
        replica = replicas.get(replica_key)
        if replica is None:
            replicas[replica_key] = _WatchRoot(unit.target_project_path, unit.managed_project_path, names, False)
        else:
            merged = tuple(sorted(set(replica.item_names) | set(names)))
            replicas[replica_key] = _WatchRoot(replica.root, replica.hub, merged, False)
    return sorted([*hubs.values(), *replicas.values()], key=lambda watch: str(watch.root))


def _classify(old: PathState, new: PathState) -> ChangeKind:
    old_present = bool(old.get("present"))
    new_present = bool(new.get("present"))
    if new_present and not old_present:
        return "create"
    if old_present and not new_present:
        return "delete"
    return "update"


def _apply_sort_key(change: PathChange) -> tuple[int, int, str, str]:
    depth = change.rel.count("/")
    kind_rank = 0 if change.kind == "delete" else 1
    depth_rank = -depth if change.kind == "delete" else depth
    return (kind_rank, depth_rank, change.rel, str(change.replica))


def _delete_allowed(change: PathChange, hub: PathState, hub_gen: int) -> bool:
    if state_equal(hub, path_state(change.base_present, change.base_hash)):
        return True
    return hub_gen - change.base_gen <= DELETE_WINDOW
