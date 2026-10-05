"""Catch-up is idle tick and named hub→replica seed on LiveSync."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from beyond_local_file.config import Config
from beyond_local_file.daemon.catchup import catch_up_live, run_catch_up
from beyond_local_file.daemon.live import LiveSync
from beyond_local_file.daemon.runtime import _catch_up_unit
from beyond_local_file.daemon.store import get_generation, save_baseline, save_snapshot
from beyond_local_file.daemon.workers import WorkerUnit
from beyond_local_file.held import list_held_copies
from beyond_local_file.model.config import ConfigProject, Mapping


def _write_lab_workspace(tmp_path: Path, items: tuple[str, ...] = ()) -> tuple[Path, Path, Path, Path]:
    """Managed project lab-app with selective replicas alpha and example."""
    hub = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    example = tmp_path / "example"
    for path in (hub, alpha, example):
        path.mkdir()
    for item in items:
        (hub / item).write_text("v0")
        (alpha / item).write_text("v0")
        (example / item).write_text("v0")
    listed = "".join(f"      - {item}\n" for item in items)
    subpath_block = f"    subpath:\n{listed}" if items else "    subpath: []\n"
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"lab-app:\n  - target: {alpha}\n{subpath_block}  - target: {example}\n{subpath_block}")
    return config_path, hub.resolve(), alpha.resolve(), example.resolve()


def _with_items(projects: dict[str, ConfigProject], items: list[str]) -> dict[str, ConfigProject]:
    """Return a copy of *projects* whose selective mappings declare *items*."""
    updated: dict[str, ConfigProject] = {}
    for key, project in projects.items():
        mappings = [Mapping(targets=list(mapping.targets), subpaths=list(items)) for mapping in project.mappings]
        updated[key] = ConfigProject(
            managed_project_name=project.managed_project_name,
            managed_project_path=project.managed_project_path,
            mappings=mappings,
        )
    return updated


def _projects(config_path: Path) -> dict[str, ConfigProject]:
    cfg = Config(config_path)
    cfg.load()
    return cfg.get_config_projects()


def _live_sync(config_path: Path) -> LiveSync:
    """Catch-up mappings and return a live observer for the committed trees."""
    projects = _projects(config_path)
    baseline = run_catch_up(projects, config_path.parent, None)
    return LiveSync(projects, baseline)


def _committed_live(config_path: Path) -> LiveSync:
    """Catch-up mappings, persist snapshot/baseline, and return a live observer."""
    projects = _projects(config_path)
    baseline = run_catch_up(projects, config_path.parent, None)
    save_snapshot(config_path, projects)
    save_baseline(config_path, baseline, projects)
    return LiveSync(projects, baseline)


def _worker_unit(live: LiveSync, config_path: Path) -> WorkerUnit:
    """Return an unstarted worker unit wrapping *live*."""
    return WorkerUnit(
        name=next(iter(live.projects.values())).managed_project_name,
        live=live,
        config_path=config_path,
        shutdown=threading.Event(),
        offset=0.0,
    )


def _make_git_repo(directory: Path) -> Path:
    """Create a fake Git repository root and return its exclude file path."""
    exclude = directory / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True)
    exclude.write_text("# preserved\n")
    return exclude


def test_seed_item_copies_hub_onto_replica_and_records_gen_0(tmp_path: Path) -> None:
    """Install-from-hub copies lab-app onto alpha only and records generation 0."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path)
    (hub / "notes.md").write_text("canonical")
    live = _live_sync(config_path)
    live.replace_projects(_with_items(live.projects, ["notes.md"]))

    live.seed_item(alpha, "notes.md")

    assert (alpha / "notes.md").read_text() == "canonical"
    assert not (example / "notes.md").exists()
    assert (hub / "notes.md").read_text() == "canonical"
    assert get_generation(live.baseline, hub, "notes.md") == 0
    assert get_generation(live.baseline, alpha, "notes.md") == 0
    live.seed_item(example, "notes.md")
    live.tick()
    assert get_generation(live.baseline, hub, "notes.md") == 0
    (alpha / "notes.md").write_text("edited")
    live.tick()
    assert (hub / "notes.md").read_text() == "edited"
    assert (example / "notes.md").read_text() == "edited"
    assert get_generation(live.baseline, hub, "notes.md") == 1


def test_seed_item_holds_colliding_replica_then_overwrites(tmp_path: Path) -> None:
    """Different bytes on alpha are held create-overwrite, then overwritten from the hub."""
    config_path, hub, alpha, _example = _write_lab_workspace(tmp_path)
    (hub / "notes.md").write_text("canonical")
    (alpha / "notes.md").write_text("alpha-draft")
    live = _live_sync(config_path)
    live.replace_projects(_with_items(live.projects, ["notes.md"]))

    live.seed_item(alpha, "notes.md")

    assert (alpha / "notes.md").read_text() == "canonical"
    copies = list_held_copies(hub)
    assert len(copies) == 1
    assert copies[0].reason == "create-overwrite"
    assert (copies[0].slot / "content").read_text() == "alpha-draft"


def test_seed_item_leaves_equal_replica_bytes(tmp_path: Path) -> None:
    """Equal bytes on alpha stay in place and are not held."""
    config_path, hub, alpha, _example = _write_lab_workspace(tmp_path)
    (hub / "notes.md").write_text("canonical")
    (alpha / "notes.md").write_text("canonical")
    live = _live_sync(config_path)
    live.replace_projects(_with_items(live.projects, ["notes.md"]))

    live.seed_item(alpha, "notes.md")

    assert (alpha / "notes.md").read_text() == "canonical"
    assert list_held_copies(hub) == ()
    assert get_generation(live.baseline, alpha, "notes.md") == 0


def test_seed_item_copies_missing_file_without_hold(tmp_path: Path) -> None:
    """A missing projection is copied from the hub with no hold."""
    config_path, hub, alpha, _example = _write_lab_workspace(tmp_path)
    (hub / "notes.md").write_text("canonical")
    live = _live_sync(config_path)
    live.replace_projects(_with_items(live.projects, ["notes.md"]))

    live.seed_item(alpha, "notes.md")

    assert (alpha / "notes.md").read_text() == "canonical"
    assert list_held_copies(hub) == ()


def test_seed_item_writes_git_exclude_on_that_replica(tmp_path: Path) -> None:
    """Git exclude is added on the replica that starts projecting the item."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path)
    alpha_exclude = _make_git_repo(alpha)
    example_exclude = _make_git_repo(example)
    (hub / "notes.md").write_text("canonical")
    live = _live_sync(config_path)
    live.replace_projects(_with_items(live.projects, ["notes.md"]))

    live.seed_item(alpha, "notes.md")

    assert "notes.md" in alpha_exclude.read_text()
    assert "notes.md" not in example_exclude.read_text()
    assert "# preserved" in example_exclude.read_text()


def test_seed_item_does_not_drain_mailbox(tmp_path: Path) -> None:
    """Install-from-hub leaves a queued path change for later apply."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path, items=("shared.txt",))
    live = _live_sync(config_path)
    (alpha / "shared.txt").write_text("queued")
    live.observe()
    (hub / "notes.md").write_text("canonical")
    live.replace_projects(_with_items(live.projects, ["shared.txt", "notes.md"]))

    live.seed_item(alpha, "notes.md")

    assert (hub / "shared.txt").read_text() == "v0"
    assert (example / "shared.txt").read_text() == "v0"
    assert (alpha / "notes.md").read_text() == "canonical"
    live.apply()
    assert (hub / "shared.txt").read_text() == "queued"
    assert (example / "shared.txt").read_text() == "queued"
    assert get_generation(live.baseline, hub, "notes.md") == 0
    assert get_generation(live.baseline, hub, "shared.txt") == 1


def test_seed_item_does_not_increment_generation(tmp_path: Path) -> None:
    """Seed records first observation at gen 0 and does not bump an existing hub generation."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path, items=("shared.txt",))
    live = _live_sync(config_path)
    (alpha / "shared.txt").write_text("from-alpha")
    live.tick()
    assert get_generation(live.baseline, hub, "shared.txt") == 1
    (hub / "notes.md").write_text("canonical")
    live.replace_projects(_with_items(live.projects, ["shared.txt", "notes.md"]))

    live.seed_item(example, "notes.md")

    assert (example / "notes.md").read_text() == "canonical"
    assert get_generation(live.baseline, hub, "notes.md") == 0
    assert get_generation(live.baseline, example, "notes.md") == 0
    assert get_generation(live.baseline, hub, "shared.txt") == 1


def test_seed_item_copies_from_the_replica_owning_hub(tmp_path: Path) -> None:
    """Two managed projects with the same item name seed from that replica's hub."""
    hub_a = tmp_path / "proj-a"
    hub_b = tmp_path / "proj-b"
    alpha = tmp_path / "alpha"
    example = tmp_path / "example"
    for path in (hub_a, hub_b, alpha, example):
        path.mkdir()
    (hub_a / "notes.md").write_text("from-a")
    (hub_b / "notes.md").write_text("from-b")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "\n".join(
            [
                "proj-a:",
                f"  target: {alpha}",
                "  subpath:",
                "    - notes.md",
                "proj-b:",
                f"  target: {example}",
                "  subpath:",
                "    - notes.md",
                "",
            ]
        )
    )
    live = LiveSync(_projects(config_path), {}, last_seen_from_baseline=True)

    live.seed_item(example, "notes.md")

    assert (example / "notes.md").read_text() == "from-b"
    assert not (alpha / "notes.md").exists()
    assert (hub_a / "notes.md").read_text() == "from-a"
    assert (hub_b / "notes.md").read_text() == "from-b"


def test_fresh_catch_up_seeds_each_replica_and_does_not_tick(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No baseline means named hub→replica seed jobs, not idle tick."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path)
    (hub / "notes.md").write_text("canonical")
    config_path.write_text(
        f"lab-app:\n  - target: {alpha}\n    subpath:\n      - notes.md\n"
        f"  - target: {example}\n    subpath:\n      - notes.md\n"
    )
    projects = _projects(config_path)
    seeds: list[tuple[str, str]] = []
    ticks: list[str] = []
    real_seed = LiveSync.seed_item
    real_tick = LiveSync.tick

    def spy_seed(self: LiveSync, replica: Path, rel: str) -> None:
        seeds.append((Path(replica).name, rel))
        real_seed(self, replica, rel)

    def spy_tick(self: LiveSync, reason: str = "idle") -> bool:
        ticks.append(reason)
        return real_tick(self, reason)

    monkeypatch.setattr(LiveSync, "seed_item", spy_seed)
    monkeypatch.setattr(LiveSync, "tick", spy_tick)
    monkeypatch.setattr(
        "beyond_local_file.daemon.catchup.record_baseline",
        lambda *args, **kwargs: pytest.fail("record_baseline"),
    )

    trees = run_catch_up(projects, tmp_path, None)

    assert sorted(seeds) == [("alpha", "notes.md"), ("example", "notes.md")]
    assert ticks == []
    assert (alpha / "notes.md").read_text() == "canonical"
    assert (example / "notes.md").read_text() == "canonical"
    assert get_generation(trees, hub, "notes.md") == 0
    assert get_generation(trees, alpha, "notes.md") == 0
    assert get_generation(trees, example, "notes.md") == 0


def test_update_catch_up_ticks_and_seeds_only_a_new_replica(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A replica missing from the baseline is seeded; recorded replicas tick."""
    hub = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    example = tmp_path / "example"
    for path in (hub, alpha, example):
        path.mkdir()
    (hub / "notes.md").write_text("canonical")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"lab-app:\n  - target: {alpha}\n    subpath:\n      - notes.md\n")
    projects = _projects(config_path)
    baseline = run_catch_up(projects, tmp_path, None)
    (alpha / "notes.md").write_text("alpha-edit")
    (example / "notes.md").write_text("example-draft")
    config_path.write_text(
        f"lab-app:\n  - target: {alpha}\n    subpath:\n      - notes.md\n"
        f"  - target: {example}\n    subpath:\n      - notes.md\n"
    )
    projects = _projects(config_path)
    seeds: list[tuple[str, str]] = []
    ticks: list[str] = []
    real_seed = LiveSync.seed_item
    real_tick = LiveSync.tick

    def spy_seed(self: LiveSync, replica: Path, rel: str) -> None:
        seeds.append((Path(replica).name, rel))
        real_seed(self, replica, rel)

    def spy_tick(self: LiveSync, reason: str = "idle") -> bool:
        ticks.append(reason)
        return real_tick(self, reason)

    monkeypatch.setattr(LiveSync, "seed_item", spy_seed)
    monkeypatch.setattr(LiveSync, "tick", spy_tick)
    monkeypatch.setattr(
        "beyond_local_file.daemon.catchup.record_baseline",
        lambda *args, **kwargs: pytest.fail("record_baseline"),
    )

    trees = run_catch_up(projects, tmp_path, baseline)

    assert seeds == [("example", "notes.md")]
    assert ticks == ["catch-up"]
    assert (alpha / "notes.md").read_text() == "alpha-edit"
    assert (hub / "notes.md").read_text() == "alpha-edit"
    assert (example / "notes.md").read_text() == "alpha-edit"
    copies = list_held_copies(hub)
    assert len(copies) == 1
    assert copies[0].reason == "create-overwrite"
    assert (copies[0].slot / "content").read_text() == "example-draft"
    assert get_generation(trees, hub, "notes.md") == 1


def test_run_catch_up_on_existing_live_does_not_construct_another(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch-up of a worker unit ticks that LiveSync; it does not build a throwaway."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path, items=("shared.txt",))
    live = _committed_live(config_path)
    (alpha / "shared.txt").write_text("from-alpha")
    monkeypatch.setattr(LiveSync, "__init__", lambda *_args, **_kwargs: pytest.fail("throwaway LiveSync"))
    monkeypatch.setattr(
        "beyond_local_file.daemon.catchup.record_baseline",
        lambda *args, **kwargs: pytest.fail("record_baseline"),
    )

    trees = catch_up_live(live, started_with_baseline=True)

    assert trees is live.baseline
    assert (hub / "shared.txt").read_text() == "from-alpha"
    assert (example / "shared.txt").read_text() == "from-alpha"
    assert get_generation(live.baseline, hub, "shared.txt") == 1


def test_catch_up_unit_uses_the_unit_live_and_does_not_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload catch-up of an existing unit ticks that live and does not reload()."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path, items=("shared.txt",))
    live = _committed_live(config_path)
    unit = _worker_unit(live, config_path)
    (alpha / "shared.txt").write_text("from-alpha")
    monkeypatch.setattr(LiveSync, "reload", lambda *_args, **_kwargs: pytest.fail("reload"))
    monkeypatch.setattr(LiveSync, "__init__", lambda *_args, **_kwargs: pytest.fail("throwaway LiveSync"))

    _catch_up_unit(config_path, unit, None)

    assert unit.live is live
    assert (hub / "shared.txt").read_text() == "from-alpha"
    assert (example / "shared.txt").read_text() == "from-alpha"
    assert get_generation(live.baseline, hub, "shared.txt") == 1
