"""Live observe: mailbox, hub apply, generation, and fan-out."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from beyond_local_file.held import REASON_DELETE_GAP, reason_clause, store_held_copy
from beyond_local_file.model.config import ConfigProject
from beyond_local_file.model.translator import translate_config_to_mapping_units

from .catchup import (
    ScanStats,
    rel_in_items,
    remove_path,
    replace_with_copy,
    scan_items,
    scan_path_state,
)
from .log import duration_ms, log_duration, worker_print
from .store import (
    REASON_FAN_OUT_MISMATCH,
    REASON_STALE_BASE,
    BaselineTrees,
    PathState,
    get_generation,
    get_state,
    is_out_of_sync,
    oos_reason_clause,
    path_state,
    state_equal,
)

DELETE_WINDOW = 3
"""Deletes win on the live path when hub_gen - base_gen is at most this value."""

_IDLE_LOG_MS = 100
"""Idle ticks faster than this are omitted from the daemon log."""

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
    item_names: tuple[str, ...]
    is_hub: bool
    item_hubs: dict[str, Path]


class LiveSync:
    """Observe item trees, coalesce per (path, replica), apply at the hub, fan out."""

    def __init__(self, projects: dict[str, ConfigProject], baseline: BaselineTrees) -> None:
        """Start observing committed mappings from an existing baseline.

        Args:
            projects: Committed mappings to watch.
            baseline: Last applied hashes, presence, and generations.
        """
        self._projects = projects
        self._baseline = baseline
        self._mailbox: dict[tuple[str, str], PathChange] = {}
        self._oos: set[tuple[str, str]] = _oos_from_baseline(baseline)
        self._last_source: dict[tuple[str, str], Path] = {}
        self._watch_roots = _build_watch_roots(projects)
        self._last_seen = self._scan_all(reason="init")

    @property
    def baseline(self) -> BaselineTrees:
        """Return the in-memory baseline trees."""
        return self._baseline

    @property
    def projects(self) -> dict[str, ConfigProject]:
        """Return the committed mappings this observer is watching."""
        return self._projects

    @property
    def out_of_sync(self) -> tuple[tuple[Path, str], ...]:
        """Return replica/path pairs isolated after a lost update CAS."""
        return tuple((Path(root), rel) for root, rel in sorted(self._oos))

    def tick(self, reason: str = "idle") -> bool:
        """Observe current trees into the mailbox, then apply pending changes.

        Args:
            reason: Why this tick ran (``idle`` or another caller-supplied label).
                Idle ticks faster than 100ms with no apply are not logged.

        Returns:
            True if any mailbox entry was applied or attempted, or isolation
            state changed (out-of-sync marked or cleared).
        """
        started = time.perf_counter()
        stats = ScanStats()
        before_oos = set(self._oos)
        self.observe(stats)
        applied = False
        if self._mailbox:
            self.apply()
            applied = True
        changed = applied or before_oos != self._oos
        elapsed = duration_ms(started)
        if reason != "idle" or changed or elapsed >= _IDLE_LOG_MS:
            worker_print(
                "live: tick "
                f"reason={reason} roots={len(self._watch_roots)} "
                f"paths={stats.paths} files={stats.files} hashed_bytes={stats.hashed_bytes} "
                f"duration_ms={elapsed} applied={str(changed).lower()}"
            )
        return changed

    def observe(self, stats: ScanStats | None = None) -> None:
        """Queue create/update/delete for paths that differ from the last scan.

        Args:
            stats: Optional accumulator for this scan's path/file/byte counts.
        """
        collected = stats if stats is not None else ScanStats()
        for watch in self._watch_roots:
            scanned = scan_items(watch.root, list(watch.item_names), collected)
            last = self._last_seen.get(str(watch.root), {})
            for rel in set(scanned) | set(last):
                new = scanned.get(rel) or path_state(False, None)
                old = last.get(rel) or path_state(False, None)
                if state_equal(old, new):
                    continue
                kind = _classify(old, new)
                owner = _owner_hub(watch, rel)
                if self._is_oos(watch.root, rel):
                    hub_now = scan_path_state(owner, rel)
                    if state_equal(new, hub_now):
                        self._clear_oos(watch.root, rel, owner)
                        continue
                    if kind != "delete":
                        continue
                self._mailbox[(rel, str(watch.root))] = PathChange(
                    rel=rel,
                    replica=watch.root,
                    hub=owner,
                    kind=kind,
                    base_present=bool(old.get("present")),
                    base_hash=old.get("hash") if old.get("present") else None,
                    base_gen=get_generation(self._baseline, watch.root, rel),
                )
            self._last_seen[str(watch.root)] = scanned

    def apply(self) -> tuple[str, ...]:
        """Apply pending mailbox entries one at a time, first-apply-wins per path.

        Returns:
            Relative paths that were applied, in apply order (duplicates kept
            when several replicas queued the same path).
        """
        applied: list[str] = []
        while self._mailbox:
            key = min(self._mailbox, key=lambda item: _apply_sort_key(self._mailbox[item]))
            change = self._mailbox.pop(key)
            self._apply_one(change)
            applied.append(change.rel)
        return tuple(applied)

    def resolve(self, rel: str, content: bytes) -> None:
        """Write the confirmed fact as a new hub generation and overwrite every replica of that path.

        Resolve is the exception to live fan-out: out-of-sync replicas of *rel* are
        overwritten too, then out-of-sync is cleared for that path only. Isolated
        replica bytes that did not enter the confirmed fact are not held.

        Args:
            rel: Path relative to the managed project.
            content: Confirmed-fact bytes to write.
        """
        hub = self._hub_for(rel)
        if hub is None:
            raise ValueError(f"no managed project owns {rel}")
        old_hub_gen = get_generation(self._baseline, hub, rel)
        self._write_file(hub / rel, content)
        new_gen = old_hub_gen + 1
        new_hub = scan_path_state(hub, rel)
        self._record(hub, rel, new_hub, new_gen)
        self._last_source[(str(hub), rel)] = hub
        print(f"live: resolve {rel} gen {new_gen}", flush=True)
        self._overwrite_replicas(hub, rel, new_gen)
        self._drop_mailbox(rel)

    def reload(self, projects: dict[str, ConfigProject], baseline: BaselineTrees) -> None:
        """Replace mappings and treat current disks as already seen.

        Args:
            projects: Newly committed mappings.
            baseline: Baseline recorded after the mapping mutation.
        """
        self._projects = projects
        self._baseline = baseline
        self._oos = _oos_from_baseline(baseline)
        self._last_source = {}
        self._watch_roots = _build_watch_roots(projects)
        self._last_seen = _last_seen_from_baseline(baseline)
        self._mailbox.clear()

    def _scan_all(self, reason: str) -> BaselineTrees:
        stats = ScanStats()
        trees: BaselineTrees = {}
        with log_duration("live: scan", reason=reason, roots=len(self._watch_roots)) as fields:
            for watch in self._watch_roots:
                trees[str(watch.root)] = scan_items(watch.root, list(watch.item_names), stats)
            fields["paths"] = stats.paths
            fields["files"] = stats.files
            fields["hashed_bytes"] = stats.hashed_bytes
        return trees

    def _apply_one(self, change: PathChange) -> None:
        if change.replica == change.hub:
            self._commit_hub_source(change)
            return
        if self._is_oos(change.replica, change.rel) and change.kind != "delete":
            return
        old_hub = scan_path_state(change.hub, change.rel)
        old_hub_gen = get_generation(self._baseline, change.hub, change.rel)
        if change.kind == "delete":
            if not _delete_allowed(change, old_hub, old_hub_gen):
                self._hold_delete_gap(change)
            remove_path(change.hub / change.rel)
        else:
            if not state_equal(old_hub, path_state(change.base_present, change.base_hash)):
                winner = self._winning_replica(change.hub, change.rel)
                self._mark_oos(
                    change.replica,
                    change.rel,
                    reason=REASON_STALE_BASE,
                    clause=oos_reason_clause(
                        REASON_STALE_BASE,
                        replica=change.replica.as_posix(),
                        path=change.rel,
                        gen=old_hub_gen,
                        winner=winner.as_posix(),
                    ),
                )
                return
            source = change.replica / change.rel
            if not source.exists() and not source.is_symlink():
                return
            replace_with_copy(source, change.hub / change.rel)
        new_gen = old_hub_gen + 1
        new_hub = scan_path_state(change.hub, change.rel)
        self._record(change.hub, change.rel, new_hub, new_gen)
        self._record(change.replica, change.rel, scan_path_state(change.replica, change.rel), new_gen)
        self._oos.discard((str(change.replica), change.rel))
        self._last_source[(str(change.hub), change.rel)] = change.replica
        print(f"live: {change.kind} {change.rel} gen {new_gen}", flush=True)
        self._fan_out(change, old_hub, new_hub, new_gen)
        self._rejoin_equal_replicas(change.hub, change.rel, new_hub)

    def _commit_hub_source(self, change: PathChange) -> None:
        previous = get_state(self._baseline, change.hub, change.rel)
        old_hub = path_state(bool(previous.get("present")), previous.get("hash") if previous.get("present") else None)
        new_gen = get_generation(self._baseline, change.hub, change.rel) + 1
        new_hub = scan_path_state(change.hub, change.rel)
        self._record(change.hub, change.rel, new_hub, new_gen)
        self._last_source[(str(change.hub), change.rel)] = change.replica
        print(f"live: {change.kind} {change.rel} gen {new_gen}", flush=True)
        self._fan_out(change, old_hub, new_hub, new_gen)
        self._rejoin_equal_replicas(change.hub, change.rel, new_hub)

    def _fan_out(
        self,
        change: PathChange,
        old_hub: PathState,
        new_hub: PathState,
        new_gen: int,
    ) -> None:
        for watch in self._watch_roots:
            if watch.is_hub or watch.root == change.replica:
                continue
            if not rel_in_items(change.rel, watch.item_names):
                continue
            if _owner_hub(watch, change.rel) != change.hub:
                continue
            if self._is_oos(watch.root, change.rel):
                continue
            if (change.rel, str(watch.root)) in self._mailbox:
                continue
            disk = scan_path_state(watch.root, change.rel)
            if not state_equal(disk, old_hub):
                self._mark_oos(
                    watch.root,
                    change.rel,
                    reason=REASON_FAN_OUT_MISMATCH,
                    clause=oos_reason_clause(
                        REASON_FAN_OUT_MISMATCH,
                        replica=watch.root.as_posix(),
                        path=change.rel,
                        gen=new_gen,
                    ),
                )
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

    def _hub_for(self, rel: str) -> Path | None:
        for watch in self._watch_roots:
            if watch.is_hub and rel_in_items(rel, watch.item_names):
                return watch.root
        return None

    def _overwrite_replicas(self, hub: Path, rel: str, new_gen: int) -> None:
        source = hub / rel
        for watch in self._watch_roots:
            if watch.is_hub or watch.root == hub:
                continue
            if not rel_in_items(rel, watch.item_names):
                continue
            if _owner_hub(watch, rel) != hub:
                continue
            destination = watch.root / rel
            if source.exists() or source.is_symlink():
                replace_with_copy(source, destination)
            else:
                remove_path(destination)
            self._oos.discard((str(watch.root), rel))
            self._record(watch.root, rel, scan_path_state(watch.root, rel), new_gen)
        for replica_str, oos_rel in list(self._oos):
            if oos_rel == rel:
                self._clear_oos(Path(replica_str), rel, hub)

    def _drop_mailbox(self, rel: str) -> None:
        for key in [item for item in self._mailbox if item[0] == rel]:
            del self._mailbox[key]

    def _write_file(self, path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not path.is_file() and not path.is_symlink():
            remove_path(path)
        path.write_bytes(content)

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

    def _is_oos(self, replica: Path, rel: str) -> bool:
        return (str(replica), rel) in self._oos

    def _mark_oos(
        self,
        replica: Path,
        rel: str,
        *,
        reason: str,
        clause: str,
    ) -> None:
        self._oos.add((str(replica), rel))
        current = get_state(self._baseline, replica, rel)
        present = bool(current.get("present"))
        state = path_state(
            present,
            current.get("hash") if present else None,
            get_generation(self._baseline, replica, rel),
            oos=True,
        )
        state["reason"] = reason
        state["clause"] = clause
        self._baseline.setdefault(str(replica), {})[rel] = state

    def _winning_replica(self, hub: Path, rel: str) -> Path:
        return self._last_source.get((str(hub), rel), hub)

    def _clear_oos(self, replica: Path, rel: str, hub: Path) -> None:
        self._oos.discard((str(replica), rel))
        self._record(replica, rel, scan_path_state(replica, rel), get_generation(self._baseline, hub, rel))

    def _rejoin_equal_replicas(self, hub: Path, rel: str, new_hub: PathState) -> None:
        for replica_str, oos_rel in list(self._oos):
            if oos_rel != rel:
                continue
            replica = Path(replica_str)
            if state_equal(scan_path_state(replica, rel), new_hub):
                self._clear_oos(replica, rel, hub)

    def _hold_delete_gap(self, change: PathChange) -> None:
        hub_path = change.hub / change.rel
        if not hub_path.exists() and not hub_path.is_symlink():
            return
        clause = reason_clause(REASON_DELETE_GAP, path=change.rel, replica=str(change.replica))
        slot = store_held_copy(
            change.hub,
            rel_path=Path(change.rel),
            source=hub_path,
            replica=change.replica,
            reason=REASON_DELETE_GAP,
        )
        print(f"WARNING: {clause}", flush=True)
        print(f"Held at {slot.as_posix()}", flush=True)


def _owner_hub(watch: _WatchRoot, rel: str) -> Path:
    """Return the managed project that owns *rel* on this watch root.

    Args:
        watch: Hub or replica watch.
        rel: Path relative to the watch root.

    Returns:
        Hub directory for the unique item that covers *rel*.
    """
    for name in watch.item_names:
        if rel == name or rel.startswith(f"{name}/"):
            return watch.item_hubs[name]
    return watch.root


def _merge_watch(
    current: _WatchRoot | None,
    root: Path,
    names: tuple[str, ...],
    is_hub: bool,
    item_hubs: dict[str, Path],
) -> _WatchRoot:
    """Union item names and owners onto one watch root.

    Args:
        current: Existing watch, or None.
        root: Directory being watched.
        names: Item names from one mapping unit.
        is_hub: True when *root* is a managed project.
        item_hubs: Item name to hub directory.

    Returns:
        Combined watch root.
    """
    if current is None:
        return _WatchRoot(root, names, is_hub, dict(item_hubs))
    merged_names = tuple(sorted(set(current.item_names) | set(names)))
    merged_hubs = dict(current.item_hubs)
    merged_hubs.update(item_hubs)
    return _WatchRoot(root, merged_names, is_hub, merged_hubs)


def _build_watch_roots(projects: dict[str, ConfigProject]) -> list[_WatchRoot]:
    hubs: dict[str, _WatchRoot] = {}
    replicas: dict[str, _WatchRoot] = {}
    for unit in translate_config_to_mapping_units(projects):
        names = tuple(item.name for item in unit.items)
        item_hubs = dict.fromkeys(names, unit.managed_project_path)
        hub_key = str(unit.managed_project_path)
        hubs[hub_key] = _merge_watch(hubs.get(hub_key), unit.managed_project_path, names, True, item_hubs)
        replica_key = str(unit.target_project_path)
        replicas[replica_key] = _merge_watch(
            replicas.get(replica_key), unit.target_project_path, names, False, item_hubs
        )
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


def _last_seen_from_baseline(baseline: BaselineTrees) -> BaselineTrees:
    seen: BaselineTrees = {}
    for root, paths in baseline.items():
        slot: dict[str, PathState] = {}
        for rel, state in paths.items():
            if state.get("present"):
                slot[rel] = path_state(True, state.get("hash"))
        seen[root] = slot
    return seen


def _oos_from_baseline(baseline: BaselineTrees) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for root, paths in baseline.items():
        for rel, state in paths.items():
            if is_out_of_sync(state):
                found.add((root, rel))
    return found
