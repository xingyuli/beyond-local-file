"""Live observe: mailbox, generation, hub apply, and fan-out at the public seams."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from beyond_local_file.config import Config
from beyond_local_file.daemon.catchup import run_catch_up
from beyond_local_file.daemon.live import DELETE_WINDOW, LiveSync
from beyond_local_file.daemon.store import get_generation
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


@pytest.fixture
def live_workspace(tmp_path: Path) -> tuple[LiveSync, Path, Path, Path]:
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
    with daemon_running(config_path, isolated_home):
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


def test_delete_past_generation_gap_does_not_remove_hub(
    live_workspace: tuple[LiveSync, Path, Path, Path],
) -> None:
    """Gap greater than 3 does not delete the hub in this ticket (held copies are later)."""
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

    assert (managed / "shared.txt").read_text() == "a4"
    assert (target_a / "shared.txt").read_text() == "a4"
    assert not (target_b / "shared.txt").exists()


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
