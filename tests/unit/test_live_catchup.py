"""Catch-up is idle tick and named hub→replica seed on LiveSync."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
import yaml

from beyond_local_file.config import Config
from beyond_local_file.configuration_set import ConfigurationSet
from beyond_local_file.daemon.catchup import catch_up_live, run_catch_up
from beyond_local_file.daemon.ingest import MappingChange, prune_removed_replicas
from beyond_local_file.daemon.live import LiveSync
from beyond_local_file.daemon.runtime import _catch_up_unit
from beyond_local_file.daemon.store import get_generation, get_state, is_out_of_sync, save_baseline, save_snapshot
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
    """Recorded replicas tick first. A new replica then receives that hub result."""
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

    assert seeds == []
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


def test_catch_up_seed_skips_declared_name_missing_from_hub(tmp_path: Path) -> None:
    """Seed does not copy a declared name whose hub path is absent, and leaves replica bytes."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path)
    (alpha / "notes.md").write_text("draft")
    live = LiveSync(_with_items(_projects(config_path), ["notes.md"]), {})

    catch_up_live(live, started_with_baseline=False)

    assert not (hub / "notes.md").exists()
    assert (alpha / "notes.md").read_text() == "draft"
    assert not (example / "notes.md").exists()


def test_update_catch_up_fans_hub_edit_to_new_target_and_holds_its_bytes(tmp_path: Path) -> None:
    """A new target receives the hub file after a hub edit; its bytes are held."""
    hub = tmp_path / "lab-app"
    beta = tmp_path / "beta"
    alpha = tmp_path / "alpha"
    for path in (hub, beta, alpha):
        path.mkdir()
    (hub / "shared.txt").write_text("aaa")
    (beta / "shared.txt").write_text("aaa")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"lab-app:\n  - target: {beta}\n    subpath:\n      - shared.txt\n")
    live = _committed_live(config_path)
    (hub / "shared.txt").write_text("bbb")
    (alpha / "shared.txt").write_text("ccc")
    project = next(iter(live.projects.values()))
    live.replace_projects(
        {
            next(iter(live.projects)): ConfigProject(
                managed_project_name=project.managed_project_name,
                managed_project_path=project.managed_project_path,
                mappings=[
                    *project.mappings,
                    Mapping(targets=[alpha], subpaths=["shared.txt"]),
                ],
            )
        }
    )

    catch_up_live(live, started_with_baseline=True)

    assert (hub / "shared.txt").read_text() == "bbb"
    assert (beta / "shared.txt").read_text() == "bbb"
    assert (alpha / "shared.txt").read_text() == "bbb"
    assert get_generation(live.baseline, hub, "shared.txt") == 1
    assert get_generation(live.baseline, beta, "shared.txt") == 1
    assert get_generation(live.baseline, alpha, "shared.txt") == 1
    assert not is_out_of_sync(get_state(live.baseline, alpha, "shared.txt"))
    copies = list_held_copies(hub)
    assert len(copies) == 1
    assert copies[0].reason == "create-overwrite"
    assert copies[0].path == "shared.txt"
    assert (copies[0].slot / "content").read_text() == "ccc"


def test_update_catch_up_deletes_missing_hub_file_and_holds_new_target_bytes(tmp_path: Path) -> None:
    """A missing hub file is a delete. The new target's different bytes are held."""
    hub = tmp_path / "lab-app"
    beta = tmp_path / "beta"
    alpha = tmp_path / "alpha"
    for path in (hub, beta, alpha):
        path.mkdir()
    (hub / "notes.md").write_text("aaa")
    (beta / "notes.md").write_text("aaa")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"lab-app:\n  - target: {beta}\n    subpath:\n      - notes.md\n")
    live = _committed_live(config_path)
    (hub / "notes.md").unlink()
    (alpha / "notes.md").write_text("ccc")
    project = next(iter(live.projects.values()))
    live.replace_projects(
        {
            next(iter(live.projects)): ConfigProject(
                managed_project_name=project.managed_project_name,
                managed_project_path=project.managed_project_path,
                mappings=[*project.mappings, Mapping(targets=[alpha], subpaths=["notes.md"])],
            )
        }
    )

    catch_up_live(live, started_with_baseline=True)

    assert not (hub / "notes.md").exists()
    assert not (beta / "notes.md").exists()
    assert not (alpha / "notes.md").exists()
    for root in (hub, beta, alpha):
        state = get_state(live.baseline, root, "notes.md")
        assert state.get("present") is False
        assert get_generation(live.baseline, root, "notes.md") == 1
    copies = list_held_copies(hub)
    assert len(copies) == 1
    assert copies[0].reason == "delete-overwrite"
    assert copies[0].path == "notes.md"
    assert (copies[0].slot / "content").read_text() == "ccc"


def test_update_catch_up_removes_matching_new_target_bytes_without_hold(tmp_path: Path) -> None:
    """A new target that still has the deleted hub bytes is removed with no hold."""
    hub = tmp_path / "lab-app"
    beta = tmp_path / "beta"
    alpha = tmp_path / "alpha"
    for path in (hub, beta, alpha):
        path.mkdir()
    (hub / "notes.md").write_text("aaa")
    (beta / "notes.md").write_text("aaa")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"lab-app:\n  - target: {beta}\n    subpath:\n      - notes.md\n")
    live = _committed_live(config_path)
    (hub / "notes.md").unlink()
    (alpha / "notes.md").write_text("aaa")
    project = next(iter(live.projects.values()))
    live.replace_projects(
        {
            next(iter(live.projects)): ConfigProject(
                managed_project_name=project.managed_project_name,
                managed_project_path=project.managed_project_path,
                mappings=[*project.mappings, Mapping(targets=[alpha], subpaths=["notes.md"])],
            )
        }
    )

    catch_up_live(live, started_with_baseline=True)

    assert not (alpha / "notes.md").exists()
    assert list_held_copies(hub) == ()
    assert get_state(live.baseline, alpha, "notes.md").get("present") is False


def test_absent_hub_item_keeps_git_exclude_on_the_new_target(tmp_path: Path) -> None:
    """The item stays declared, so git exclude on the new target stays."""
    hub = tmp_path / "lab-app"
    beta = tmp_path / "beta"
    alpha = tmp_path / "alpha"
    for path in (hub, beta, alpha):
        path.mkdir()
    (hub / "shared.txt").write_text("aaa")
    (beta / "shared.txt").write_text("aaa")
    exclude = _make_git_repo(alpha)
    exclude.write_text("shared.txt\n")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"lab-app:\n  - target: {beta}\n    subpath:\n      - shared.txt\n")
    live = _committed_live(config_path)
    (hub / "shared.txt").unlink()
    live.tick(reason="catch-up")
    (alpha / "shared.txt").write_text("ccc")
    project = next(iter(live.projects.values()))
    live.replace_projects(
        {
            next(iter(live.projects)): ConfigProject(
                managed_project_name=project.managed_project_name,
                managed_project_path=project.managed_project_path,
                mappings=[*project.mappings, Mapping(targets=[alpha], subpaths=["shared.txt"])],
            )
        }
    )

    catch_up_live(live, started_with_baseline=True)

    assert "shared.txt" in exclude.read_text()
    assert not (alpha / "shared.txt").exists()


def test_update_catch_up_keeps_absent_generation_and_holds_each_new_target(tmp_path: Path) -> None:
    """An already-absent hub row stays put. Each new target's bytes are held."""
    hub = tmp_path / "lab-app"
    beta = tmp_path / "beta"
    alpha = tmp_path / "alpha"
    example = tmp_path / "example"
    for path in (hub, beta, alpha, example):
        path.mkdir()
    (hub / "shared.txt").write_text("aaa")
    (beta / "shared.txt").write_text("aaa")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"lab-app:\n  - target: {beta}\n    subpath:\n      - shared.txt\n")
    live = _committed_live(config_path)
    (hub / "shared.txt").unlink()
    live.tick(reason="catch-up")
    assert get_generation(live.baseline, hub, "shared.txt") == 1
    assert get_state(live.baseline, hub, "shared.txt").get("present") is False
    (alpha / "shared.txt").write_text("ccc")
    (example / "shared.txt").write_text("ddd")
    project = next(iter(live.projects.values()))
    live.replace_projects(
        {
            next(iter(live.projects)): ConfigProject(
                managed_project_name=project.managed_project_name,
                managed_project_path=project.managed_project_path,
                mappings=[
                    *project.mappings,
                    Mapping(targets=[alpha], subpaths=["shared.txt"]),
                    Mapping(targets=[example], subpaths=["shared.txt"]),
                ],
            )
        }
    )

    catch_up_live(live, started_with_baseline=True)

    assert not (hub / "shared.txt").exists()
    assert not (alpha / "shared.txt").exists()
    assert not (example / "shared.txt").exists()
    assert get_generation(live.baseline, hub, "shared.txt") == 1
    assert get_state(live.baseline, alpha, "shared.txt").get("present") is False
    assert get_state(live.baseline, example, "shared.txt").get("present") is False
    reasons = sorted(copy.reason for copy in list_held_copies(hub))
    assert reasons == ["delete-overwrite", "delete-overwrite"]
    texts = sorted((copy.slot / "content").read_text() for copy in list_held_copies(hub))
    assert texts == ["ccc", "ddd"]


def test_update_catch_up_records_a_directory_child_at_its_hub_generation(tmp_path: Path) -> None:
    """A new target records each path at that path's hub generation.

    The directory node stays at generation 2. The edited child is generation 5
    on the hub, on the target that was already in sync, and on the new target.
    """
    hub = tmp_path / "lab-app"
    beta = tmp_path / "beta"
    alpha = tmp_path / "alpha"
    for path in (hub, beta, alpha):
        path.mkdir()
    (hub / "docs").mkdir()
    (hub / "docs" / "a.md").write_text("aaa")
    (beta / "docs").mkdir()
    (beta / "docs" / "a.md").write_text("aaa")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"lab-app:\n  - target: {beta}\n    subpath:\n      - docs\n")
    live = _committed_live(config_path)
    for root in (hub, beta):
        live.baseline[str(root)]["docs"]["gen"] = 2
        live.baseline[str(root)]["docs/a.md"]["gen"] = 4
    (hub / "docs" / "a.md").write_text("bbb")
    (alpha / "docs").mkdir()
    (alpha / "docs" / "a.md").write_text("ccc")
    project = next(iter(live.projects.values()))
    live.replace_projects(
        {
            next(iter(live.projects)): ConfigProject(
                managed_project_name=project.managed_project_name,
                managed_project_path=project.managed_project_path,
                mappings=[*project.mappings, Mapping(targets=[alpha], subpaths=["docs"])],
            )
        }
    )

    catch_up_live(live, started_with_baseline=True)

    directory_generation = 2
    child_generation = 5
    assert (hub / "docs" / "a.md").read_text() == "bbb"
    assert (beta / "docs" / "a.md").read_text() == "bbb"
    assert (alpha / "docs" / "a.md").read_text() == "bbb"
    child_hash = get_state(live.baseline, hub, "docs/a.md").get("hash")
    for root in (hub, beta, alpha):
        assert get_generation(live.baseline, root, "docs") == directory_generation
        assert get_state(live.baseline, root, "docs").get("hash") is None
        assert get_generation(live.baseline, root, "docs/a.md") == child_generation
        assert get_state(live.baseline, root, "docs/a.md").get("hash") == child_hash
        assert not is_out_of_sync(get_state(live.baseline, root, "docs/a.md"))
    copies = list_held_copies(hub)
    assert len(copies) == 1
    assert copies[0].reason == "create-overwrite"
    assert copies[0].path == "docs"
    assert (copies[0].slot / "content" / "a.md").read_text() == "ccc"


def test_update_catch_up_holds_a_directory_item_once(tmp_path: Path) -> None:
    """A differing directory on a new target is one held tree."""
    hub = tmp_path / "lab-app"
    beta = tmp_path / "beta"
    alpha = tmp_path / "alpha"
    for path in (hub, beta, alpha):
        path.mkdir()
    (hub / "docs").mkdir()
    (hub / "docs" / "a.md").write_text("hub-a")
    (beta / "docs").mkdir()
    (beta / "docs" / "a.md").write_text("hub-a")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"lab-app:\n  - target: {beta}\n    subpath:\n      - docs\n")
    live = _committed_live(config_path)
    (hub / "docs" / "a.md").unlink()
    (hub / "docs").rmdir()
    (alpha / "docs").mkdir()
    (alpha / "docs" / "a.md").write_text("alpha-a")
    project = next(iter(live.projects.values()))
    live.replace_projects(
        {
            next(iter(live.projects)): ConfigProject(
                managed_project_name=project.managed_project_name,
                managed_project_path=project.managed_project_path,
                mappings=[*project.mappings, Mapping(targets=[alpha], subpaths=["docs"])],
            )
        }
    )

    catch_up_live(live, started_with_baseline=True)

    assert not (hub / "docs").exists()
    assert not (beta / "docs").exists()
    assert not (alpha / "docs").exists()
    copies = list_held_copies(hub)
    assert len(copies) == 1
    assert copies[0].reason == "delete-overwrite"
    assert copies[0].path == "docs"
    assert (copies[0].slot / "content" / "a.md").read_text() == "alpha-a"
    assert "docs/a.md" in live.baseline[str(alpha)]
    for root in (hub, beta, alpha):
        assert get_state(live.baseline, root, "docs").get("present") is False
        assert get_state(live.baseline, root, "docs/a.md").get("present") is False
        assert get_generation(live.baseline, root, "docs") == get_generation(live.baseline, hub, "docs")
        assert get_generation(live.baseline, root, "docs/a.md") == get_generation(live.baseline, hub, "docs/a.md")


def test_update_catch_up_skips_an_out_of_sync_target_on_hub_delete(tmp_path: Path) -> None:
    """A hub delete does not hold or remove a target that is already out of sync."""
    hub = tmp_path / "lab-app"
    beta = tmp_path / "beta"
    for path in (hub, beta):
        path.mkdir()
    (hub / "notes.md").write_text("aaa")
    (beta / "notes.md").write_text("aaa")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"lab-app:\n  - target: {beta}\n    subpath:\n      - notes.md\n")
    live = _committed_live(config_path)
    (hub / "notes.md").write_text("bbb")
    (beta / "notes.md").write_text("ddd")
    live.tick(reason="idle")
    assert is_out_of_sync(get_state(live.baseline, beta, "notes.md"))
    (hub / "notes.md").unlink()

    catch_up_live(live, started_with_baseline=True)

    assert (beta / "notes.md").read_text() == "ddd"
    assert list_held_copies(hub) == ()
    assert is_out_of_sync(get_state(live.baseline, beta, "notes.md"))


def test_selective_new_target_files_document_lists_only_its_file_items(tmp_path: Path) -> None:
    """A selective target's files document omits file items it does not declare."""
    hub = tmp_path / "lab-app"
    beta = tmp_path / "beta"
    alpha = tmp_path / "alpha"
    for path in (hub, beta, alpha):
        path.mkdir()
    (hub / "shared.txt").write_text("aaa")
    (hub / "notes.md").write_text("note")
    (beta / "shared.txt").write_text("aaa")
    (beta / "notes.md").write_text("note")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "\n".join(
            [
                "lab-app:",
                f"  - target: {beta}",
                "    subpath:",
                "      - shared.txt",
                "      - notes.md",
                "",
            ]
        )
    )
    live = _committed_live(config_path)
    (alpha / "shared.txt").write_text("aaa")
    (alpha / "notes.md").write_text("local-note")
    project = next(iter(live.projects.values()))
    projects = {
        next(iter(live.projects)): ConfigProject(
            managed_project_name=project.managed_project_name,
            managed_project_path=project.managed_project_path,
            mappings=[*project.mappings, Mapping(targets=[alpha], subpaths=["shared.txt"])],
        )
    }
    live.replace_projects(projects)
    catch_up_live(live, started_with_baseline=True)
    save_baseline(config_path, live.baseline, projects)

    document = yaml.safe_load(
        (ConfigurationSet(config_path).run_directory / "baseline" / "lab-app" / "files").read_text(encoding="utf-8")
    )
    alpha_files = document["trees"][str(alpha.resolve())]
    assert "shared.txt" in alpha_files
    assert "notes.md" not in alpha_files
    assert (alpha / "notes.md").read_text() == "local-note"
    assert "notes.md" in document["trees"][str(hub.resolve())]


def test_item_remove_leaves_the_hub_file_and_strips_git_exclude(tmp_path: Path) -> None:
    """Item-remove drops the replica copy and its git exclude, and keeps the hub file."""
    hub = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    hub.mkdir()
    alpha.mkdir()
    (hub / "notes.md").write_text("aaa")
    (alpha / "notes.md").write_text("aaa")
    exclude = _make_git_repo(alpha)
    exclude.write_text("notes.md\n")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"lab-app:\n  - target: {alpha}\n    subpath:\n      - notes.md\n")
    live = _committed_live(config_path)
    live.drop_replica(alpha, "notes.md")
    project = next(iter(live.projects.values()))
    live.replace_projects(
        {
            next(iter(live.projects)): ConfigProject(
                managed_project_name=project.managed_project_name,
                managed_project_path=project.managed_project_path,
                mappings=[Mapping(targets=[alpha], subpaths=[])],
            )
        }
    )

    catch_up_live(live, started_with_baseline=True)

    assert (hub / "notes.md").read_text() == "aaa"
    assert not (alpha / "notes.md").exists()
    assert "notes.md" not in exclude.read_text()


def test_item_remove_drops_the_replica_baseline_row_before_start_catch_up(tmp_path: Path) -> None:
    """Start drops an item-remove row, including its out-of-sync mark, before catch-up."""
    hub = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    hub.mkdir()
    alpha.mkdir()
    (hub / "notes.md").write_text("aaa")
    (alpha / "notes.md").write_text("aaa")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"lab-app:\n  - target: {alpha}\n    subpath:\n      - notes.md\n")
    live = _committed_live(config_path)
    alpha_key = str(alpha.resolve())
    live.baseline[alpha_key]["notes.md"]["oos"] = True
    project_key = next(iter(live.projects))
    removal = MappingChange(kind="item-remove", project=project_key, target=alpha.resolve(), item="notes.md")

    pruned = prune_removed_replicas(live.baseline, live.projects, (removal,))

    assert "notes.md" not in pruned[alpha_key]
    assert (hub / "notes.md").read_text() == "aaa"


def test_renamed_target_is_not_observed_as_a_hub_delete(tmp_path: Path) -> None:
    """Dropping the old path before catch-up leaves the hub file in place."""
    hub = tmp_path / "lab-app"
    old = tmp_path / "alpha"
    renamed = tmp_path / "alpha-old"
    hub.mkdir()
    old.mkdir()
    (hub / "shared.txt").write_text("aaa")
    (old / "shared.txt").write_text("aaa")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"lab-app:\n  - target: {old}\n    subpath:\n      - shared.txt\n")
    live = _committed_live(config_path)
    old.rename(renamed)
    project = next(iter(live.projects.values()))
    live.replace_projects(
        {
            next(iter(live.projects)): ConfigProject(
                managed_project_name=project.managed_project_name,
                managed_project_path=project.managed_project_path,
                mappings=[Mapping(targets=[renamed], subpaths=["shared.txt"])],
            )
        }
    )

    catch_up_live(live, started_with_baseline=True)

    assert (hub / "shared.txt").read_text() == "aaa"
    assert (renamed / "shared.txt").read_text() == "aaa"
    assert str(old) not in live.baseline
    assert list_held_copies(hub) == ()


def test_run_catch_up_holds_new_target_bytes_when_the_hub_file_is_gone(tmp_path: Path) -> None:
    """Start's catch-up entry point follows the same hub delete rule."""
    hub = tmp_path / "lab-app"
    beta = tmp_path / "beta"
    alpha = tmp_path / "alpha"
    for path in (hub, beta, alpha):
        path.mkdir()
    (hub / "notes.md").write_text("aaa")
    (beta / "notes.md").write_text("aaa")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"lab-app:\n  - target: {beta}\n    subpath:\n      - notes.md\n")
    live = _committed_live(config_path)
    (hub / "notes.md").unlink()
    (alpha / "notes.md").write_text("ccc")
    project = next(iter(live.projects.values()))
    projects = {
        next(iter(live.projects)): ConfigProject(
            managed_project_name=project.managed_project_name,
            managed_project_path=project.managed_project_path,
            mappings=[*project.mappings, Mapping(targets=[alpha], subpaths=["notes.md"])],
        )
    }

    trees = run_catch_up(projects, config_path.parent, live.baseline)

    assert not (hub / "notes.md").exists()
    assert not (alpha / "notes.md").exists()
    assert get_state(trees, alpha.resolve(), "notes.md").get("present") is False
    assert list_held_copies(hub.resolve())[0].reason == "delete-overwrite"
