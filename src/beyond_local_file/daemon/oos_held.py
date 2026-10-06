"""Shared read of out-of-sync rows and held copies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from beyond_local_file.held import HeldCopy, list_held_copies
from beyond_local_file.model.config import ConfigProject

from .store import BaselineTrees, get_state, iter_out_of_sync


@dataclass(frozen=True)
class OosRow:
    """One replica/path that is out-of-sync."""

    replica: Path
    rel: str
    reason: str
    clause: str


@dataclass(frozen=True)
class OosAndHeld:
    """Out-of-sync rows and held copies observed together."""

    oos: tuple[OosRow, ...]
    held: tuple[HeldCopy, ...]

    def __bool__(self) -> bool:
        return bool(self.oos or self.held)


def list_oos_and_held(
    trees: BaselineTrees,
    projects: dict[str, ConfigProject],
) -> OosAndHeld:
    """Return out-of-sync rows from *trees* and held copies for *projects*.

    Args:
        trees: Baseline trees, in memory or loaded from disk.
        projects: Committed mappings whose managed-project attics are listed.

    Returns:
        Both collections intact. Held copies are listed once per managed root.
    """
    oos_rows: list[OosRow] = []
    for replica, rel in iter_out_of_sync(trees):
        state = get_state(trees, replica, rel)
        oos_rows.append(
            OosRow(
                replica=replica,
                rel=rel,
                reason=str(state.get("reason") or ""),
                clause=str(state.get("clause") or ""),
            )
        )
    held: list[HeldCopy] = []
    seen: set[str] = set()
    for project in projects.values():
        hub = str(project.managed_project_path)
        if hub in seen:
            continue
        seen.add(hub)
        held.extend(list_held_copies(project.managed_project_path))
    return OosAndHeld(oos=tuple(oos_rows), held=tuple(held))


def new_rels(before: OosAndHeld, after: OosAndHeld) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return newly appeared relative paths, out-of-sync then held.

    Args:
        before: Listing from before persist.
        after: Listing from after persist.

    Returns:
        Unique new out-of-sync rels and unique new held rels, each sorted.
        A second replica of an already-listed path still counts as new.
    """
    before_oos = {(str(row.replica), row.rel) for row in before.oos}
    oos_rels = {rel for replica, rel in {(str(row.replica), row.rel) for row in after.oos} - before_oos}
    before_held = {(str(copy.slot), copy.path) for copy in before.held}
    held_rels = {rel for slot, rel in {(str(copy.slot), copy.path) for copy in after.held} - before_held}
    return tuple(sorted(oos_rels)), tuple(sorted(held_rels))
