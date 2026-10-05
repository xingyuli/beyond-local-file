"""Live observe: mailbox, hub apply, generation, and fan-out."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from beyond_local_file.held import REASON_DELETE_GAP, is_held_item_name, reason_clause, store_held_copy
from beyond_local_file.model.config import ConfigProject
from beyond_local_file.model.processing import ManagedProjectItem
from beyond_local_file.model.translator import translate_config_to_mapping_units
from beyond_local_file.projection import copy_projection

from .catchup import (
    ScanStats,
    add_git_exclude,
    copy_hub_onto_replica,
    rel_in_items,
    remove_git_exclude,
    remove_path,
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

    def __init__(
        self,
        projects: dict[str, ConfigProject],
        baseline: BaselineTrees,
        *,
        last_seen_from_baseline: bool = False,
    ) -> None:
        """Start observing committed mappings from an existing baseline.

        Args:
            projects: Committed mappings to watch.
            baseline: Last applied hashes, presence, and generations.
            last_seen_from_baseline: When True, treat *baseline* as the last
                scan so the first tick queues downtime diffs (update catch-up).
                When False, scan disks now and treat that as already seen.
        """
        self._projects = projects
        self._baseline = baseline
        self._mailbox: dict[tuple[str, str], PathChange] = {}
        self._oos: set[tuple[str, str]] = _oos_from_baseline(baseline)
        self._last_source: dict[tuple[str, str], Path] = {}
        self._watch_roots = _build_watch_roots(projects)
        if last_seen_from_baseline:
            self._last_seen = _last_seen_from_baseline(baseline)
        else:
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

    def install_item(self, replica: Path, rel: str) -> None:
        """Named item-add: copy *rel* from *replica* onto the hub, fan out, exclude, gen 0.

        Does not drain the mailbox. Colliding replica bytes are held
        ``create-overwrite`` then overwritten. Equal bytes stay. Generation 0
        is the first version observed.

        Args:
            replica: Adopting replica that already has the bytes.
            rel: Item path relative to the hub and replicas.
        """
        hub = self._hub_for_install(rel)
        source = replica / rel
        with log_duration("create: copy"):
            copy_projection(source, hub / rel)
        others = self._other_replica_roots(replica, rel)
        with log_duration("create: fan-out"):
            for other in others:
                copy_hub_onto_replica(hub, other, rel)
        with log_duration("create: git-exclude"):
            for root in (replica, *others):
                add_git_exclude(root, rel)
        self._record_item(hub, rel, gen=0)
        self._record_item(replica, rel, gen=0)
        for other in others:
            self._record_item(other, rel, gen=0)
        self._last_source[(str(hub), rel)] = replica
        self._watch_roots = _build_watch_roots(self._projects)
        print(f"live: install {rel} gen 0", flush=True)

    def restore_item(self, replica: Path, rel: str) -> None:
        """Named restore: delete hub and other replicas' copies; leave *replica*.

        Inverse of :meth:`install_item`. Does not drain the mailbox. Git exclude
        is stripped on every replica that stops projecting *rel*, including
        *replica*. Absence is recorded without incrementing generation.

        Args:
            replica: Requesting replica whose file stays as an unmanaged local file.
            rel: Item path relative to the hub and replicas.
        """
        hub = self._hub_for_install(rel)
        others = self._other_replica_roots(replica, rel)
        with log_duration("restore: delete-managed"):
            remove_path(hub / rel)
        with log_duration("restore: undo-fan-out"):
            for other in others:
                remove_path(other / rel)
        with log_duration("restore: git-exclude"):
            for root in (replica, *others):
                remove_git_exclude(root, rel)
        self._forget_item(hub, rel)
        for other in others:
            self._forget_item(other, rel)
        print(f"live: restore {rel}", flush=True)

    def remove_item(self, replica: Path, rel: str) -> None:
        """Named remove: delete hub and every projection, including *replica*.

        Does not drain the mailbox. Git exclude is stripped on every replica
        that stops projecting *rel*. Absence is recorded without incrementing
        generation.

        Args:
            replica: Requesting replica; used to identify sibling projections.
            rel: Item path relative to the hub and replicas.
        """
        hub = self._hub_for_install(rel)
        replicas = self._replica_roots(rel)
        if not any(root.resolve() == replica.resolve() for root in replicas):
            replicas = [replica, *replicas]
        with log_duration("remove: cleanup-targets"):
            for root in replicas:
                remove_path(root / rel)
        with log_duration("remove: delete-managed"):
            remove_path(hub / rel)
        with log_duration("remove: git-exclude"):
            for root in replicas:
                remove_git_exclude(root, rel)
        self._forget_item(hub, rel)
        for root in replicas:
            self._forget_item(root, rel)
        print(f"live: remove {rel}", flush=True)

    def drop_replica(self, replica: Path, rel: str) -> None:
        """Named ingest retract: delete *replica*'s copy of *rel*; keep the hub.

        Does not drain the mailbox. Git exclude is stripped on *replica* only.
        Absence is recorded on *replica* without incrementing generation.

        Args:
            replica: Target that stops projecting *rel*.
            rel: Item path relative to the replica.
        """
        with log_duration("ingest: retract"):
            remove_path(replica / rel)
            remove_git_exclude(replica, rel)
        self._forget_item(replica, rel)
        print(f"live: drop-replica {rel}", flush=True)

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

    def apply_frozen_mismatches(self) -> tuple[str, ...]:
        """Apply replica paths that match baseline yet differ from hub.

        Update catch-up records a new baseline after apply. A previous start
        that skipped replica-side diffs can leave hub and replica matching
        their own baseline rows while the live copies disagree. Those paths
        are invisible to a baseline-seeded tick. A replica-only create marked
        out-of-sync at hub generation 0 is applied (the create never landed).
        Out-of-sync content conflicts stay isolated until resolve.

        Returns:
            Relative paths applied from this pass, in apply order.
        """
        hub_scans: dict[str, dict[str, PathState]] = {}
        for watch in self._watch_roots:
            if watch.is_hub:
                hub_scans[str(watch.root)] = scan_items(watch.root, list(watch.item_names))
        for watch in self._watch_roots:
            if watch.is_hub:
                continue
            replica_now = scan_items(watch.root, list(watch.item_names))
            hub_rels = {
                rel
                for hub_key, tree in hub_scans.items()
                for rel in tree
                if rel_in_items(rel, watch.item_names) and _owner_hub(watch, rel) == Path(hub_key)
            }
            for rel in set(replica_now) | hub_rels:
                hub = _owner_hub(watch, rel)
                hub_now = hub_scans.get(str(hub), {}).get(rel) or path_state(False, None)
                replica_state = replica_now.get(rel) or path_state(False, None)
                if state_equal(hub_now, replica_state):
                    continue
                hub_present = bool(hub_now.get("present"))
                if self._is_oos(watch.root, rel) and hub_present:
                    continue
                if not state_equal(hub_now, get_state(self._baseline, hub, rel)):
                    continue
                if not state_equal(replica_state, get_state(self._baseline, watch.root, rel)):
                    continue
                if self._is_oos(watch.root, rel) and not hub_present:
                    self._oos.discard((str(watch.root), rel))
                self._mailbox[(rel, str(watch.root))] = PathChange(
                    rel=rel,
                    replica=watch.root,
                    hub=hub,
                    kind=_classify(hub_now, replica_state),
                    base_present=bool(hub_now.get("present")),
                    base_hash=hub_now.get("hash") if hub_now.get("present") else None,
                    base_gen=get_generation(self._baseline, hub, rel),
                )
        if not self._mailbox:
            return ()
        return self.apply()

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

    def replace_projects(self, projects: dict[str, ConfigProject]) -> None:
        """Rebuild watch roots from new mappings without forgetting last-seen.

        Mailbox, last-seen, last-source, and out-of-sync for paths still
        covered by the new mappings stay. Paths that are no longer watched
        are dropped so a later observe does not treat them as deletes.

        Args:
            projects: Newly committed mappings.
        """
        self._projects = projects
        self._watch_roots = _build_watch_roots(projects)
        allowed = {str(watch.root): watch.item_names for watch in self._watch_roots}
        self._prune_unwatched(allowed)

    def merge_item_from_trees(self, item_name: str, trees: BaselineTrees) -> None:
        """Fill last-seen and baseline gaps for *item_name* from *trees*.

        Existing live rows are kept. After a mutating shell that wrote disks
        outside LiveSync, persist may scan that item; this records those
        paths only when live does not already have them.

        Args:
            item_name: Declared item relative to the managed project.
            trees: Recorded trees that include a scan of *item_name*.
        """
        for root, paths in trees.items():
            seen = self._last_seen.setdefault(root, {})
            slot = self._baseline.setdefault(root, {})
            for rel, state in paths.items():
                if not rel_in_items(rel, (item_name,)):
                    continue
                if rel not in slot:
                    slot[rel] = dict(state)
                if rel not in seen and state.get("present"):
                    seen[rel] = path_state(True, state.get("hash"))

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
            copy_projection(source, change.hub / change.rel)
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
                    copy_projection(source, destination)
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

    def _hub_for_install(self, rel: str) -> Path:
        hub = self._hub_for(rel)
        if hub is not None:
            return hub
        return next(iter(self._projects.values())).managed_project_path

    def _replica_roots(self, rel: str) -> list[Path]:
        """Return mapping targets that declare *rel*.

        Args:
            rel: Item path relative to each replica.

        Returns:
            Unique target roots in first-seen order.
        """
        seen: set[Path] = set()
        roots: list[Path] = []
        for project in self._projects.values():
            for mapping in project.mappings:
                if mapping.subpaths is not None and rel not in mapping.subpaths:
                    continue
                for target in mapping.targets:
                    resolved = target.resolve()
                    if resolved in seen:
                        continue
                    seen.add(resolved)
                    roots.append(target)
        return roots

    def _other_replica_roots(self, source: Path, rel: str) -> list[Path]:
        """Return other mapping targets that declare *rel*.

        Args:
            source: Adopting replica to exclude.
            rel: Item path relative to each replica.

        Returns:
            Unique target roots in first-seen order.
        """
        source_resolved = source.resolve()
        return [root for root in self._replica_roots(rel) if root.resolve() != source_resolved]

    def _forget_item(self, root: Path, item_name: str) -> None:
        """Record absence of *item_name* and nested paths without incrementing generation.

        Args:
            root: Hub or replica whose copy of *item_name* is gone.
            item_name: Declared item relative to *root*.
        """
        slot = self._baseline.get(str(root), {})
        seen = self._last_seen.get(str(root), {})
        rels = [path for path in set(slot) | set(seen) if rel_in_items(path, (item_name,))]
        if item_name not in rels:
            rels.append(item_name)
        for rel in rels:
            gen = get_generation(self._baseline, root, rel)
            self._oos.discard((str(root), rel))
            self._record(root, rel, path_state(False, None), gen)

    def _record_item(self, root: Path, item_name: str, gen: int) -> None:
        scanned = scan_items(root, [item_name])
        if not scanned:
            self._record(root, item_name, path_state(False, None), gen)
            return
        for rel, state in scanned.items():
            self._record(root, rel, state, gen)

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
                copy_projection(source, destination)
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

    def _prune_unwatched(self, allowed: dict[str, tuple[str, ...]]) -> None:
        """Drop last-seen, baseline, mailbox, last-source, and out-of-sync for unwatched paths.

        Args:
            allowed: Item names still watched, keyed by replica root.
        """
        for store in (self._last_seen, self._baseline):
            for root in list(store):
                names = allowed.get(root)
                if names is None:
                    del store[root]
                    continue
                slot = store[root]
                for rel in [path for path in slot if not rel_in_items(path, names)]:
                    del slot[rel]
        for key in list(self._mailbox):
            rel, replica = key
            names = allowed.get(replica)
            if names is None or not rel_in_items(rel, names):
                del self._mailbox[key]
        for key in list(self._last_source):
            hub, rel = key
            names = allowed.get(hub)
            if names is None or not rel_in_items(rel, names):
                del self._last_source[key]
        for item in list(self._oos):
            replica, rel = item
            names = allowed.get(replica)
            if names is None or not rel_in_items(rel, names):
                self._oos.discard(item)

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


def _watch_item_loader(managed_project_path: Path, subpaths: list[str] | None) -> list[ManagedProjectItem]:
    """Load declared items, including selective subpaths not yet on the hub.

    Create splices yaml then replace_projects before the hub copy exists.
    Watch roots must still include that declared item.
    """
    if subpaths is None:
        items: list[ManagedProjectItem] = []
        if managed_project_path.exists() and managed_project_path.is_dir():
            for item_path in managed_project_path.iterdir():
                if is_held_item_name(item_path.name):
                    continue
                items.append(ManagedProjectItem(name=item_path.name, path=item_path))
        return items
    items_list: list[ManagedProjectItem] = []
    for subpath in subpaths:
        if is_held_item_name(Path(subpath).parts[0]):
            continue
        items_list.append(ManagedProjectItem(name=subpath, path=managed_project_path / subpath))
    return items_list


def _build_watch_roots(projects: dict[str, ConfigProject]) -> list[_WatchRoot]:
    hubs: dict[str, _WatchRoot] = {}
    replicas: dict[str, _WatchRoot] = {}
    for unit in translate_config_to_mapping_units(projects, item_loader=_watch_item_loader):
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
