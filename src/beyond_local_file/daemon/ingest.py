"""Classify external mapping edits against the mapping snapshot."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import click

from beyond_local_file.config import Config
from beyond_local_file.held import is_held_item_name
from beyond_local_file.model.config import ConfigProject

from .catchup import remove_path, run_catch_up
from .store import BaselineTrees, load_baseline, load_snapshot, mappings_equal, save_baseline, save_snapshot

type Subpaths = frozenset[str] | None


@dataclass(frozen=True)
class MappingChange:
    """One classified mapping change from a snapshot-vs-file diff."""

    kind: str
    project: str
    target: Path | None = None
    item: str | None = None


@dataclass(frozen=True)
class MappingDiff:
    """Removals (coarse-to-fine, inner diffs subsumed) and automatic adds."""

    removals: tuple[MappingChange, ...]
    additions: tuple[MappingChange, ...]


@dataclass(frozen=True)
class _ProjectIndex:
    hub: Path
    targets: dict[Path, Subpaths]


def stdin_is_tty() -> bool:
    """Return whether stdin can confirm mapping removals.

    Returns:
        True when stdin is a terminal.
    """
    try:
        return sys.stdin.isatty()
    except ValueError:
        return False


def classify(old: dict[str, ConfigProject], new: dict[str, ConfigProject]) -> MappingDiff:
    """Diff committed mappings against the config file.

    Removals are ordered project-remove, target-remove, item-remove, with
    inner diffs dropped when a coarser removal already implies them. Adds
    are ordered project-add, target-add, item-add the same way.

    Args:
        old: Mapping snapshot.
        new: Config file projects.

    Returns:
        Classified removals and additions.
    """
    old_index = _index_projects(old)
    new_index = _index_projects(new)
    removals: list[MappingChange] = []
    additions: list[MappingChange] = []

    for name in sorted(set(old_index) - set(new_index)):
        removals.append(MappingChange("project-remove", name))
    for name in sorted(set(new_index) - set(old_index)):
        additions.append(MappingChange("project-add", name))

    for name in sorted(set(old_index) & set(new_index)):
        old_targets = old_index[name].targets
        new_targets = new_index[name].targets
        for target in sorted(set(old_targets) - set(new_targets), key=str):
            removals.append(MappingChange("target-remove", name, target))
        for target in sorted(set(new_targets) - set(old_targets), key=str):
            additions.append(MappingChange("target-add", name, target))
        hub = new_index[name].hub
        old_hub = old_index[name].hub
        for target in sorted(set(old_targets) & set(new_targets), key=str):
            for item in _item_removes(old_targets[target], new_targets[target], old_hub):
                removals.append(MappingChange("item-remove", name, target, item))
            for item in _item_adds(old_targets[target], new_targets[target], hub):
                additions.append(MappingChange("item-add", name, target, item))

    return MappingDiff(tuple(removals), tuple(additions))


def format_removal_plan(removals: tuple[MappingChange, ...]) -> str:
    """Render removals as one coarse-to-fine plan.

    Args:
        removals: Classified removals already in classifier order.

    Returns:
        Multi-line plan text.
    """
    lines = ["Mapping removals:"]
    for change in removals:
        if change.kind == "project-remove":
            lines.append(f"  project-remove: {change.project}")
        elif change.kind == "target-remove":
            lines.append(f"  target-remove: {change.project} -> {change.target}")
        elif change.kind == "item-remove":
            lines.append(f"  item-remove: {change.project} -> {change.target} : {change.item}")
    return "\n".join(lines)


def prepare_ingest(
    config_path: Path,
) -> tuple[int, dict[str, ConfigProject] | None, dict[str, ConfigProject] | None, MappingDiff | None]:
    """Classify the config file against the snapshot and confirm removals.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        Exit code, file projects, snapshot projects, and the diff when ingest
        should commit. A ``None`` diff means there is nothing to apply.
    """
    file_projects, snapshot_projects = _load_file_and_snapshot(config_path)
    if snapshot_projects is None or mappings_equal(file_projects, snapshot_projects):
        return 0, file_projects, snapshot_projects, None
    diff = classify(snapshot_projects, file_projects)
    missing = missing_hub_item_adds(file_projects, diff)
    if missing:
        for path in missing:
            click.echo(f"Error: hub file does not exist: {path}")
        return 1, None, None, None
    if diff.removals:
        click.echo(format_removal_plan(diff.removals))
        if not confirm_removals():
            click.echo("Mapping changes were not applied")
            return 1, None, None, None
    return 0, file_projects, snapshot_projects, diff


def ingest_before_start(config_path: Path) -> int:
    """Classify a differing config file in the start foreground.

    Matching snapshot (or first start) is a no-op. Removals print one plan
    and require yes; decline or a non-TTY leaves the snapshot unchanged.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        0 when start may background, 1 when ingest aborted.
    """
    code, file_projects, snapshot_projects, diff = prepare_ingest(config_path)
    if code != 0:
        return code
    if diff is None or file_projects is None or snapshot_projects is None:
        return 0
    apply_removals(snapshot_projects, diff.removals)
    save_snapshot(config_path, file_projects)
    _persist_pruned_baseline(config_path, snapshot_projects, diff.removals)
    return 0


def commit_reload(config_path: Path, *, confirmed: bool) -> int:
    """Apply the config file as the new snapshot inside the running daemon.

    Args:
        config_path: Path to the loaded config file.
        confirmed: True when the shell already confirmed removals.

    Returns:
        0 after commit and catch-up, 1 when ingest cannot proceed.
    """
    file_projects, snapshot_projects = _load_file_and_snapshot(config_path)
    if snapshot_projects is None:
        click.echo("Error: mapping snapshot is missing")
        return 1
    if mappings_equal(file_projects, snapshot_projects):
        return 0
    diff = classify(snapshot_projects, file_projects)
    missing = missing_hub_item_adds(file_projects, diff)
    if missing:
        for path in missing:
            click.echo(f"Error: hub file does not exist: {path}")
        return 1
    if diff.removals and not confirmed:
        click.echo("Error: mapping removals require interactive confirmation")
        return 1
    apply_removals(snapshot_projects, diff.removals)
    save_snapshot(config_path, file_projects)
    baseline = prune_removed_replicas(load_baseline(config_path), snapshot_projects, diff.removals)
    trees = run_catch_up(file_projects, config_path.parent, baseline)
    save_baseline(config_path, trees)
    return 0


def missing_hub_item_adds(new: dict[str, ConfigProject], diff: MappingDiff) -> list[Path]:
    """Return hub paths for item-adds that do not exist on disk.

    Args:
        new: Config file projects.
        diff: Classified mapping changes.

    Returns:
        Missing hub paths in classifier order.
    """
    index = _index_projects(new)
    missing: list[Path] = []
    for change in diff.additions:
        if change.kind != "item-add" or change.item is None:
            continue
        path = index[change.project].hub / change.item
        if not path.exists() and not path.is_symlink():
            missing.append(path)
    return missing


def prune_removed_replicas(
    baseline: BaselineTrees | None,
    old: dict[str, ConfigProject],
    removals: tuple[MappingChange, ...],
) -> BaselineTrees | None:
    """Drop baseline trees for replicas removed from mappings.

    Args:
        baseline: Current baseline, or None.
        old: Mapping snapshot before the commit.
        removals: Classified removals.

    Returns:
        Baseline without removed replica roots, or None when *baseline* is None.
    """
    if baseline is None:
        return None
    index = _index_projects(old)
    drop: set[str] = set()
    for change in removals:
        if change.kind == "project-remove":
            drop.update(str(target) for target in index[change.project].targets)
        elif change.kind == "target-remove" and change.target is not None:
            drop.add(str(change.target))
    if not drop:
        return baseline
    return {root: tree for root, tree in baseline.items() if root not in drop}


def apply_removals(old: dict[str, ConfigProject], removals: tuple[MappingChange, ...]) -> None:
    """Delete target copies for confirmed removals. Hub content is kept.

    Args:
        old: Mapping snapshot before the commit.
        removals: Classified removals to apply.
    """
    index = _index_projects(old)
    for change in removals:
        project = index[change.project]
        if change.kind == "project-remove":
            for target, subpaths in project.targets.items():
                _delete_projected_items(project.hub, target, subpaths)
        elif change.kind == "target-remove" and change.target is not None:
            _delete_projected_items(project.hub, change.target, project.targets[change.target])
        elif change.kind == "item-remove" and change.target is not None and change.item is not None:
            remove_path(change.target / change.item)


def confirm_removals() -> bool:
    """Prompt once for the printed removal plan.

    Returns:
        True when the user confirmed on a TTY.
    """
    if not stdin_is_tty():
        click.echo("Error: mapping removals require interactive confirmation")
        return False
    return click.confirm("Apply these mapping removals?", default=False)


def _persist_pruned_baseline(
    config_path: Path,
    old: dict[str, ConfigProject],
    removals: tuple[MappingChange, ...],
) -> None:
    pruned = prune_removed_replicas(load_baseline(config_path), old, removals)
    if pruned is not None:
        save_baseline(config_path, pruned)


def _load_file_and_snapshot(
    config_path: Path,
) -> tuple[dict[str, ConfigProject], dict[str, ConfigProject] | None]:
    cfg = Config(config_path)
    cfg.load()
    return cfg.get_config_projects(), load_snapshot(config_path)


def _index_projects(projects: dict[str, ConfigProject]) -> dict[str, _ProjectIndex]:
    indexed: dict[str, _ProjectIndex] = {}
    for name, project in projects.items():
        targets: dict[Path, Subpaths] = {}
        for mapping in project.mappings:
            incoming: Subpaths = None if mapping.subpaths is None else frozenset(mapping.subpaths)
            for target in mapping.targets:
                key = target.resolve()
                if key not in targets:
                    targets[key] = incoming
                    continue
                current = targets[key]
                if current is None or incoming is None:
                    targets[key] = None
                else:
                    targets[key] = current | incoming
        indexed[name] = _ProjectIndex(hub=project.managed_project_path, targets=targets)
    return indexed


def _item_removes(old: Subpaths, new: Subpaths, hub: Path) -> list[str]:
    if new is None or old == new:
        return []
    old_set = _hub_items(hub) if old is None else old
    return sorted(old_set - new)


def _item_adds(old: Subpaths, new: Subpaths, hub: Path) -> list[str]:
    if old is None or old == new:
        return []
    if new is None:
        return sorted(_hub_items(hub) - old)
    return sorted(new - old)


def _delete_projected_items(hub: Path, target: Path, subpaths: Subpaths) -> None:
    names = _hub_items(hub) if subpaths is None else subpaths
    for name in names:
        remove_path(target / name)


def _hub_items(hub: Path) -> frozenset[str]:
    if not hub.is_dir():
        return frozenset()
    return frozenset(path.name for path in hub.iterdir() if not is_held_item_name(path.name))
