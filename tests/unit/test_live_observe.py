"""Live observe: mailbox, generation, hub apply, and fan-out at the public seams."""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from beyond_local_file.config import Config
from beyond_local_file.daemon.catchup import record_baseline, run_catch_up
from beyond_local_file.daemon.live import DELETE_WINDOW, LiveSync
from beyond_local_file.daemon.runtime import _execute_unit_request
from beyond_local_file.daemon.store import get_generation, save_baseline, save_snapshot
from beyond_local_file.daemon.workers import WorkerUnit
from beyond_local_file.model.config import ConfigProject, Mapping
from beyond_local_file.operations.revlink import CreateOperation
from tests.daemon_support import daemon_running

_READY_WAIT_S = 15.0
_POLL_S = 0.05


def _write_two_target_workspace(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Create one managed project with two target replicas and a shared file."""
    managed = tmp_path / "proj"
    target_a = tmp_path / "target-a"
    target_b = tmp_path / "target-b"
    managed.mkdir()
    target_a.mkdir()
    target_b.mkdir()
    (managed / "shared.txt").write_text("v0")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"proj:\n  - {target_a}\n  - {target_b}\n")
    return config_path, managed, target_a, target_b


def _live_sync(config_path: Path) -> LiveSync:
    """Catch-up mappings and return a live observer for the committed trees."""
    cfg = Config(config_path)
    cfg.load()
    projects = cfg.get_config_projects()
    baseline = run_catch_up(projects, config_path.parent, None)
    return LiveSync(projects, baseline)


def _wait_until(predicate: Callable[[], bool], *, timeout: float = _READY_WAIT_S) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(_POLL_S)
    raise TimeoutError("condition was not met")


def _expected_held_dir(managed: Path, home: Path) -> Path:
    """Return ``<home>/.blf/held/<sha256 of the resolved managed project path>``."""
    digest = hashlib.sha256(str(managed.resolve()).encode("utf-8")).hexdigest()
    return home / ".blf" / "held" / digest


@pytest.fixture
def live_workspace(tmp_path: Path, isolated_home: dict[str, str]) -> tuple[LiveSync, Path, Path, Path]:
    """In-process live observer after a fresh catch-up onto two targets."""
    config_path, managed, target_a, target_b = _write_two_target_workspace(tmp_path)
    live = _live_sync(config_path)
    return live, managed.resolve(), target_a.resolve(), target_b.resolve()


@pytest.fixture
def daemon_workspace(tmp_path: Path) -> Iterator[tuple[Path, Path, Path, Path]]:
    """Two-target workspace used with a spawned daemon."""
    config_path, managed, target_a, target_b = _write_two_target_workspace(tmp_path)
    yield config_path, managed.resolve(), target_a.resolve(), target_b.resolve()


def test_edit_in_one_target_appears_on_hub_and_other_targets_without_writing_source(
    live_workspace: tuple[LiveSync, Path, Path, Path],
) -> None:
    """An edit in one target is applied to the hub and other replicas, not the source."""
    live, managed, target_a, target_b = live_workspace
    source = target_a / "shared.txt"
    source.write_text("from-a")
    after_write = source.stat()

    live.tick()

    assert (managed / "shared.txt").read_text() == "from-a"
    assert (target_b / "shared.txt").read_text() == "from-a"
    assert source.read_text() == "from-a"
    after_tick = source.stat()
    assert after_tick.st_mtime_ns == after_write.st_mtime_ns
    assert after_tick.st_ino == after_write.st_ino


def test_running_daemon_fans_out_target_edit_without_writing_source(
    daemon_workspace: tuple[Path, Path, Path, Path],
    isolated_home: dict[str, str],
) -> None:
    """While the daemon is running, a target edit reaches the hub and the other replica."""
    config_path, managed, target_a, target_b = daemon_workspace
    env = {**isolated_home, "BLF_IDLE_OBSERVE_S": "0.2"}
    with daemon_running(config_path, env):
        source = target_a / "shared.txt"
        _wait_until(lambda: source.is_file() and source.read_text() == "v0")
        source.write_text("from-a")
        after_write = source.stat()
        _wait_until(lambda: (managed / "shared.txt").read_text() == "from-a")
        _wait_until(lambda: (target_b / "shared.txt").read_text() == "from-a")
        after_wait = source.stat()
        assert source.read_text() == "from-a"
        assert after_wait.st_mtime_ns == after_write.st_mtime_ns
        assert after_wait.st_ino == after_write.st_ino


def test_hub_edit_fans_out_to_all_targets_without_rewriting_hub(
    live_workspace: tuple[LiveSync, Path, Path, Path],
) -> None:
    """A hub edit is committed as a new generation and copied onto every target."""
    live, managed, target_a, target_b = live_workspace
    hub_file = managed / "shared.txt"
    hub_file.write_text("from-hub")
    after_write = hub_file.stat()

    live.tick()

    assert (target_a / "shared.txt").read_text() == "from-hub"
    assert (target_b / "shared.txt").read_text() == "from-hub"
    assert hub_file.read_text() == "from-hub"
    after_tick = hub_file.stat()
    assert after_tick.st_mtime_ns == after_write.st_mtime_ns
    assert after_tick.st_ino == after_write.st_ino


def test_create_under_directory_item_appears_on_hub_and_other_targets(tmp_path: Path) -> None:
    """A new path inside a directory item is queued per path, not as a tree hash."""
    managed = tmp_path / "proj"
    target_a = tmp_path / "target-a"
    target_b = tmp_path / "target-b"
    for directory in (managed, target_a, target_b):
        directory.mkdir()
    nested = managed / "nested"
    nested.mkdir()
    (nested / "keep.txt").write_text("keep")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"proj:\n  - {target_a}\n  - {target_b}\n")
    live = _live_sync(config_path)

    (target_a / "nested" / "new.txt").write_text("created")
    live.tick()

    assert (managed / "nested" / "new.txt").read_text() == "created"
    assert (target_b / "nested" / "new.txt").read_text() == "created"
    assert (target_a / "nested" / "keep.txt").read_text() == "keep"
    assert (managed / "nested" / "keep.txt").read_text() == "keep"


def test_update_catch_up_applies_target_create_under_directory_item(tmp_path: Path) -> None:
    """A target-only create while down is applied by update catch-up, as a live tick would."""
    managed = tmp_path / "proj"
    target_a = tmp_path / "target-a"
    target_b = tmp_path / "target-b"
    for directory in (managed, target_a, target_b):
        directory.mkdir()
    nested = managed / "nested"
    nested.mkdir()
    (nested / "keep.txt").write_text("keep")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"proj:\n  - {target_a}\n  - {target_b}\n")
    cfg = Config(config_path)
    cfg.load()
    projects = cfg.get_config_projects()
    baseline = run_catch_up(projects, tmp_path, None)

    (target_a / "nested" / "new-task.md").write_text("added-on-target")
    run_catch_up(projects, tmp_path, baseline)

    assert (managed / "nested" / "new-task.md").read_text() == "added-on-target"
    assert (target_b / "nested" / "new-task.md").read_text() == "added-on-target"


def test_update_catch_up_applies_target_create_already_recorded_in_baseline(
    tmp_path: Path,
) -> None:
    """A mismatch already snapshotted into the baseline is still applied on the next start."""
    managed = tmp_path / "proj"
    target = tmp_path / "target"
    for directory in (managed, target):
        directory.mkdir()
    nested = managed / "nested"
    nested.mkdir()
    (nested / "keep.txt").write_text("keep")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"proj: {target}\n")
    cfg = Config(config_path)
    cfg.load()
    projects = cfg.get_config_projects()
    baseline = run_catch_up(projects, tmp_path, None)

    (target / "nested" / "new-task.md").write_text("added-on-target")
    frozen = record_baseline(projects, previous=baseline)
    run_catch_up(projects, tmp_path, frozen)

    assert (managed / "nested" / "new-task.md").read_text() == "added-on-target"


def test_update_catch_up_applies_oos_create_that_never_landed_on_hub(tmp_path: Path) -> None:
    """A replica-only create marked out-of-sync at hub gen 0 is applied on the next start."""
    managed = tmp_path / "proj"
    target = tmp_path / "target"
    for directory in (managed, target):
        directory.mkdir()
    nested = managed / "nested"
    nested.mkdir()
    (nested / "keep.txt").write_text("keep")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"proj: {target}\n")
    cfg = Config(config_path)
    cfg.load()
    projects = cfg.get_config_projects()
    baseline = run_catch_up(projects, tmp_path, None)

    (target / "nested" / "new-task.md").write_text("added-on-target")
    frozen = record_baseline(projects, previous=baseline)
    rel = "nested/new-task.md"
    replica_key = next(key for key, paths in frozen.items() if rel in paths)
    frozen[replica_key][rel]["oos"] = True
    frozen[replica_key][rel]["reason"] = "stale-base"
    run_catch_up(projects, tmp_path, frozen)

    assert (managed / "nested" / "new-task.md").read_text() == "added-on-target"


def test_update_catch_up_does_not_overwrite_hub_for_oos_content_conflict(tmp_path: Path) -> None:
    """An out-of-sync content conflict stays on the replica until resolve."""
    managed = tmp_path / "proj"
    target = tmp_path / "target"
    for directory in (managed, target):
        directory.mkdir()
    (managed / "shared.txt").write_text("hub-now")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"proj: {target}\n")
    cfg = Config(config_path)
    cfg.load()
    projects = cfg.get_config_projects()
    baseline = run_catch_up(projects, tmp_path, None)

    (target / "shared.txt").write_text("from-target")
    frozen = record_baseline(projects, previous=baseline)
    rel = "shared.txt"
    hub_keys = {str(project.managed_project_path) for project in projects.values()}
    replica_key = next(key for key, paths in frozen.items() if rel in paths and key not in hub_keys)
    frozen[replica_key][rel]["oos"] = True
    frozen[replica_key][rel]["reason"] = "stale-base"
    run_catch_up(projects, tmp_path, frozen)

    assert (managed / "shared.txt").read_text() == "hub-now"
    assert (target / "shared.txt").read_text() == "from-target"


def test_update_catch_up_then_idle_tick_still_applies_target_create(tmp_path: Path) -> None:
    """If catch-up records the mismatch as baseline, a later idle tick still applies it."""
    managed = tmp_path / "proj"
    target = tmp_path / "target"
    for directory in (managed, target):
        directory.mkdir()
    nested = managed / "nested"
    nested.mkdir()
    (nested / "keep.txt").write_text("keep")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"proj: {target}\n")
    cfg = Config(config_path)
    cfg.load()
    projects = cfg.get_config_projects()
    baseline = run_catch_up(projects, tmp_path, None)

    (target / "nested" / "new-task.md").write_text("added-on-target")
    baseline = run_catch_up(projects, tmp_path, baseline)
    LiveSync(projects, baseline).tick()

    assert (managed / "nested" / "new-task.md").read_text() == "added-on-target"


def test_update_catch_up_applies_target_edit_of_existing_file(tmp_path: Path) -> None:
    """A target-only edit while down is applied by update catch-up, as a live tick would."""
    managed = tmp_path / "proj"
    target = tmp_path / "target"
    for directory in (managed, target):
        directory.mkdir()
    (managed / "shared.txt").write_text("v0")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"proj: {target}\n")
    cfg = Config(config_path)
    cfg.load()
    projects = cfg.get_config_projects()
    baseline = run_catch_up(projects, tmp_path, None)

    (target / "shared.txt").write_text("from-target")
    run_catch_up(projects, tmp_path, baseline)

    assert (managed / "shared.txt").read_text() == "from-target"


def test_five_quick_saves_become_one_hub_apply(
    live_workspace: tuple[LiveSync, Path, Path, Path],
) -> None:
    """Mailbox replacement coalesces five saves from one replica into one generation bump."""
    live, managed, target_a, _target_b = live_workspace
    rel = "shared.txt"
    assert get_generation(live.baseline, managed, rel) == 0

    source = target_a / rel
    source.write_text("save-1")
    source.write_text("save-2")
    source.write_text("save-3")
    source.write_text("save-4")
    source.write_text("save-5")
    live.tick()

    assert (managed / rel).read_text() == "save-5"
    assert get_generation(live.baseline, managed, rel) == 1


def test_two_replicas_editing_same_path_are_not_last_arrival_wins(
    live_workspace: tuple[LiveSync, Path, Path, Path],
) -> None:
    """Cross-replica mailbox slots stay separate; the first apply wins and the loser is kept."""
    live, managed, target_a, target_b = live_workspace
    (target_a / "shared.txt").write_text("from-a")
    (target_b / "shared.txt").write_text("from-b")

    live.tick()

    assert (managed / "shared.txt").read_text() == "from-a"
    assert (target_a / "shared.txt").read_text() == "from-a"
    assert (target_b / "shared.txt").read_text() == "from-b"
    assert get_generation(live.baseline, managed, "shared.txt") == 1


def test_delete_matching_base_removes_live_path_on_hub_and_other_replicas(
    live_workspace: tuple[LiveSync, Path, Path, Path],
) -> None:
    """A matching-base delete removes the live path on the hub and other in-sync replicas."""
    live, managed, target_a, target_b = live_workspace
    (target_a / "shared.txt").unlink()

    live.tick()

    assert not (managed / "shared.txt").exists()
    assert not (target_b / "shared.txt").exists()
    assert not (target_a / "shared.txt").exists()


def test_delete_within_generation_gap_removes_live_path_on_hub_and_other_replicas(
    live_workspace: tuple[LiveSync, Path, Path, Path],
) -> None:
    """A delete still wins on the live path when hub_gen - base_gen is at most 3."""
    live, managed, target_a, target_b = live_workspace
    (target_b / "shared.txt").write_text("divergent")
    (target_a / "shared.txt").write_text("a1")
    live.tick()
    assert (managed / "shared.txt").read_text() == "a1"
    assert (target_b / "shared.txt").read_text() == "divergent"

    (target_a / "shared.txt").write_text("a2")
    live.tick()
    (target_a / "shared.txt").write_text("a3")
    live.tick()
    assert get_generation(live.baseline, managed, "shared.txt") == DELETE_WINDOW

    (target_b / "shared.txt").unlink()
    live.tick()

    assert not (managed / "shared.txt").exists()
    assert not (target_a / "shared.txt").exists()
    assert not (target_b / "shared.txt").exists()


def test_delete_past_generation_gap_holds_then_removes_live_path(
    live_workspace: tuple[LiveSync, Path, Path, Path],
    isolated_home: dict[str, str],
) -> None:
    """Gap greater than 3 holds hub bytes under ~/.blf/held/<hash>/, then delete-wins."""
    live, managed, target_a, target_b = live_workspace
    (target_b / "shared.txt").write_text("divergent")
    (target_a / "shared.txt").write_text("a1")
    live.tick()
    (target_a / "shared.txt").write_text("a2")
    live.tick()
    (target_a / "shared.txt").write_text("a3")
    live.tick()
    (target_a / "shared.txt").write_text("a4")
    live.tick()
    assert get_generation(live.baseline, managed, "shared.txt") == DELETE_WINDOW + 1
    assert (managed / "shared.txt").read_text() == "a4"

    (target_b / "shared.txt").unlink()
    live.tick()

    assert not (managed / "shared.txt").exists()
    assert not (target_a / "shared.txt").exists()
    assert not (target_b / "shared.txt").exists()
    held_root = _expected_held_dir(managed, Path(isolated_home["BLF_HOME"]))
    slots = [path for path in held_root.iterdir() if path.is_dir()]
    assert len(slots) == 1
    assert (slots[0] / "content").read_text() == "a4"


def test_fan_out_does_not_write_replica_whose_disk_hash_is_not_expected_base(
    live_workspace: tuple[LiveSync, Path, Path, Path],
) -> None:
    """Fan-out skips a replica whose on-disk hash is not the generation's expected base."""
    live, managed, target_a, target_b = live_workspace
    (target_a / "shared.txt").write_text("from-a")
    live.observe()
    (target_b / "shared.txt").write_text("divergent")
    live.apply()

    assert (managed / "shared.txt").read_text() == "from-a"
    assert (target_a / "shared.txt").read_text() == "from-a"
    assert (target_b / "shared.txt").read_text() == "divergent"
    assert (target_b, "shared.txt") in live.out_of_sync


def test_target_edit_applies_to_the_owning_hub_not_another_contributor(tmp_path: Path) -> None:
    """A path change on a shared target writes the managed project that owns that item."""
    hub_a = tmp_path / "proj-a"
    hub_b = tmp_path / "proj-b"
    target_shared = tmp_path / "target-shared"
    target_a_only = tmp_path / "target-a-only"
    for path in (hub_a, hub_b, target_shared, target_a_only):
        path.mkdir()
    (hub_a / "alpha.txt").write_text("alpha-0")
    (hub_b / "beta.txt").write_text("beta-0")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "\n".join(
            [
                "proj-a:",
                f"  target: [{target_shared}, {target_a_only}]",
                "  subpath:",
                "    - alpha.txt",
                "proj-b:",
                f"  target: {target_shared}",
                "  subpath:",
                "    - beta.txt",
                "",
            ]
        )
    )
    live = _live_sync(config_path)

    (target_shared / "alpha.txt").write_text("alpha-from-target")
    live.tick()

    assert (hub_a / "alpha.txt").read_text() == "alpha-from-target"
    assert (target_a_only / "alpha.txt").read_text() == "alpha-from-target"
    assert (hub_b / "beta.txt").read_text() == "beta-0"

    (target_shared / "beta.txt").write_text("beta-from-target")
    live.tick()

    assert (hub_b / "beta.txt").read_text() == "beta-from-target"
    assert (hub_a / "alpha.txt").read_text() == "alpha-from-target"
    assert (target_a_only / "alpha.txt").read_text() == "alpha-from-target"


def test_fan_out_does_not_write_another_hubs_replica_with_the_same_item_name(tmp_path: Path) -> None:
    """Fan-out stays inside the owning managed project's replicas."""
    hub_a = tmp_path / "proj-a"
    hub_b = tmp_path / "proj-b"
    target_a = tmp_path / "target-a"
    target_b = tmp_path / "target-b"
    for path in (hub_a, hub_b, target_a, target_b):
        path.mkdir()
    (hub_a / "local-file").mkdir()
    (hub_b / "local-file").mkdir()
    (hub_a / "local-file" / "note.txt").write_text("a-0")
    (hub_b / "local-file" / "note.txt").write_text("b-0")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "\n".join(
            [
                "proj-a:",
                f"  target: {target_a}",
                "  subpath:",
                "    - local-file",
                "proj-b:",
                f"  target: {target_b}",
                "  subpath:",
                "    - local-file",
                "",
            ]
        )
    )
    live = _live_sync(config_path)

    (target_a / "local-file" / "note.txt").write_text("a-from-target")
    live.tick()

    assert (hub_a / "local-file" / "note.txt").read_text() == "a-from-target"
    assert (hub_b / "local-file" / "note.txt").read_text() == "b-0"
    assert (target_b / "local-file" / "note.txt").read_text() == "b-0"
    assert (target_b, "local-file/note.txt") not in live.out_of_sync


def _write_lab_workspace(tmp_path: Path, items: tuple[str, ...] = ("shared.txt",)) -> tuple[Path, Path, Path, Path]:
    """Managed project lab-app with selective replicas alpha and example."""
    hub = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    example = tmp_path / "example"
    for path in (hub, alpha, example):
        path.mkdir()
    for item in items:
        (hub / item).write_text("v0")
    listed = "".join(f"      - {item}\n" for item in items)
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"lab-app:\n  - target: {alpha}\n    subpath:\n{listed}  - target: {example}\n    subpath:\n{listed}"
    )
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


def _committed_live(config_path: Path) -> LiveSync:
    """Catch-up mappings, persist snapshot/baseline, and return a live observer."""
    cfg = Config(config_path)
    cfg.load()
    projects = cfg.get_config_projects()
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


def test_replace_projects_keeps_a_queued_path_change(tmp_path: Path) -> None:
    """replace_projects rebuilds watch roots without dropping a queued PathChange."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path)
    live = _live_sync(config_path)
    (alpha / "shared.txt").write_text("from-alpha")
    live.observe()

    live.replace_projects(_with_items(live.projects, ["shared.txt", "notes.md"]))
    live.apply()

    assert (hub / "shared.txt").read_text() == "from-alpha"
    assert (example / "shared.txt").read_text() == "from-alpha"


def test_replace_projects_watches_a_newly_added_item(tmp_path: Path) -> None:
    """Watch roots after replace_projects include a newly declared item."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path)
    live = _live_sync(config_path)
    (hub / "notes.md").write_text("from-hub")

    live.replace_projects(_with_items(live.projects, ["shared.txt", "notes.md"]))
    live.tick()

    assert (alpha / "notes.md").read_text() == "from-hub"
    assert (example / "notes.md").read_text() == "from-hub"


def test_replace_projects_drops_a_removed_item_from_watch_roots(tmp_path: Path) -> None:
    """Watch roots after replace_projects no longer apply a dropped item."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path, items=("shared.txt", "notes.md"))
    live = _live_sync(config_path)

    live.replace_projects(_with_items(live.projects, ["shared.txt"]))
    (alpha / "notes.md").write_text("from-alpha")
    live.tick()

    assert (hub / "notes.md").read_text() == "v0"
    assert (example / "notes.md").read_text() == "v0"


def test_replace_projects_keeps_out_of_sync_for_an_unrelated_path(tmp_path: Path) -> None:
    """Out-of-sync on one path survives a mapping splice of another item."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path)
    live = _live_sync(config_path)
    (alpha / "shared.txt").write_text("from-alpha")
    live.observe()
    (example / "shared.txt").write_text("divergent")
    live.apply()
    assert (example, "shared.txt") in live.out_of_sync

    live.replace_projects(_with_items(live.projects, ["shared.txt", "notes.md"]))

    assert (example, "shared.txt") in live.out_of_sync
    assert (hub / "shared.txt").read_text() == "from-alpha"


def test_create_keeps_unrelated_mailbox_and_does_not_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mutating create updates watch roots without reload or forgetting last-seen."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path)
    live = _committed_live(config_path)
    (alpha / "shared.txt").write_text("from-alpha")
    live.tick()
    shared_gen = get_generation(live.baseline, hub, "shared.txt")
    assert shared_gen == 1
    (alpha / "notes.md").write_text("adopt me")
    unit = _worker_unit(live, config_path)
    original_run = CreateOperation.run

    def run_and_queue(self: CreateOperation) -> int:
        (alpha / "shared.txt").write_text("queued")
        live.observe()
        return original_run(self)

    monkeypatch.setattr(CreateOperation, "run", run_and_queue)
    monkeypatch.setattr(LiveSync, "reload", lambda *_args, **_kwargs: pytest.fail("reload"))

    response = _execute_unit_request(
        config_path,
        {"op": "create", "cwd": str(alpha), "path": "notes.md"},
        on_progress=None,
        unit=unit,
    )

    assert response["exit_code"] == 0, response["stdout"]
    live.apply()
    assert (hub / "shared.txt").read_text() == "queued"
    assert (example / "shared.txt").read_text() == "queued"
    assert get_generation(live.baseline, hub, "shared.txt") == shared_gen + 1
    assert (hub / "notes.md").read_text() == "adopt me"
    assert (example / "notes.md").read_text() == "adopt me"
    assert get_generation(live.baseline, hub, "notes.md") == 0
    live.tick()
    assert get_generation(live.baseline, hub, "notes.md") == 0
    (alpha / "notes.md").write_text("edited")
    live.tick()
    assert (hub / "notes.md").read_text() == "edited"
    assert (example / "notes.md").read_text() == "edited"


def test_restore_drops_the_removed_item_from_watch_roots_without_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mutating restore drops watch roots for the item and does not call reload."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path, items=("shared.txt", "notes.md"))
    live = _committed_live(config_path)
    unit = _worker_unit(live, config_path)
    monkeypatch.setattr(LiveSync, "reload", lambda *_args, **_kwargs: pytest.fail("reload"))

    response = _execute_unit_request(
        config_path,
        {"op": "restore", "cwd": str(alpha), "path": "notes.md"},
        on_progress=None,
        unit=unit,
    )

    assert response["exit_code"] == 0, response["stdout"]
    assert not (hub / "notes.md").exists()
    assert not (example / "notes.md").exists()
    assert (alpha / "notes.md").read_text() == "v0"
    (alpha / "notes.md").write_text("from-alpha")
    live.tick()
    assert not (hub / "notes.md").exists()
    assert not (example / "notes.md").exists()
    (alpha / "shared.txt").write_text("from-alpha")
    live.tick()
    assert (hub / "shared.txt").read_text() == "from-alpha"
    assert (example / "shared.txt").read_text() == "from-alpha"


def test_remove_drops_the_removed_item_from_watch_roots_without_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mutating remove drops watch roots for the item and does not call reload."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path, items=("shared.txt", "notes.md"))
    live = _committed_live(config_path)
    unit = _worker_unit(live, config_path)
    monkeypatch.setattr(LiveSync, "reload", lambda *_args, **_kwargs: pytest.fail("reload"))

    response = _execute_unit_request(
        config_path,
        {"op": "remove", "cwd": str(alpha), "path": "notes.md"},
        on_progress=None,
        unit=unit,
    )

    assert response["exit_code"] == 0, response["stdout"]
    assert not (hub / "notes.md").exists()
    assert not (alpha / "notes.md").exists()
    assert not (example / "notes.md").exists()
    (alpha / "notes.md").write_text("from-alpha")
    live.tick()
    assert not (hub / "notes.md").exists()
    assert not (example / "notes.md").exists()
    (alpha / "shared.txt").write_text("from-alpha")
    live.tick()
    assert (hub / "shared.txt").read_text() == "from-alpha"
    assert (example / "shared.txt").read_text() == "from-alpha"
