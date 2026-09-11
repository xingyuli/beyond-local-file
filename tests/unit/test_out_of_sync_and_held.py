"""Out-of-sync isolation and held copies at the public seams."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner, Result

from beyond_local_file.cli import cli
from beyond_local_file.config import Config
from beyond_local_file.daemon.catchup import run_catch_up
from beyond_local_file.daemon.live import LiveSync
from beyond_local_file.daemon.store import save_baseline, save_snapshot
from beyond_local_file.held import REASON_DELETE_GAP, reason_clause, store_held_copy
from tests.daemon_support import invoke_cli, start_daemon, stop_daemon

_READY_WAIT_S = 15.0
_POLL_S = 0.05
_DELETE_GAP_CLAUSE = "delete applied past the generation window; kept hub bytes of shared.txt (reason: delete-gap)"


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
    save_snapshot(config_path, projects)
    save_baseline(config_path, baseline)
    return LiveSync(projects, baseline)


def _persist(config_path: Path, live: LiveSync) -> None:
    """Write the live baseline so status/start/reload can see isolation state."""
    cfg = Config(config_path)
    cfg.load()
    save_snapshot(config_path, cfg.get_config_projects())
    save_baseline(config_path, live.baseline)


def _wait_until(predicate, *, timeout: float = _READY_WAIT_S) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(_POLL_S)
    raise TimeoutError("condition was not met")


def _invoke_start(
    config_path: Path,
    env: dict[str, str],
    *,
    input_text: str | None = None,
) -> Result:
    return CliRunner().invoke(
        cli,
        ["--config", str(config_path), "daemon", "start"],
        env=env,
        input=input_text,
    )


def _invoke_reload(
    config_path: Path,
    env: dict[str, str],
    *,
    input_text: str | None = None,
) -> Result:
    return CliRunner().invoke(
        cli,
        ["--config", str(config_path), "daemon", "reload"],
        env=env,
        input=input_text,
    )


def _mark_loser_out_of_sync(live: LiveSync, target_a: Path, target_b: Path) -> None:
    """Two replicas edit the same path; first apply wins and the other is isolated."""
    (target_a / "shared.txt").write_text("from-a")
    (target_b / "shared.txt").write_text("from-b")
    live.tick()


@pytest.fixture
def live_workspace(tmp_path: Path) -> tuple[LiveSync, Path, Path, Path, Path]:
    """In-process live observer after a fresh catch-up onto two targets."""
    config_path, managed, target_a, target_b = _write_two_target_workspace(tmp_path)
    live = _live_sync(config_path)
    return live, config_path, managed.resolve(), target_a.resolve(), target_b.resolve()


@pytest.fixture
def daemon_workspace(tmp_path: Path, isolated_home: dict[str, str]) -> Iterator[tuple[Path, Path, Path, Path]]:
    """Two-target workspace used with a spawned daemon."""
    config_path, managed, target_a, target_b = _write_two_target_workspace(tmp_path)
    try:
        yield config_path, managed.resolve(), target_a.resolve(), target_b.resolve()
    finally:
        stop_daemon(config_path, isolated_home)


def test_two_targets_same_path_first_apply_wins_other_listed_out_of_sync(
    live_workspace: tuple[LiveSync, Path, Path, Path, Path],
) -> None:
    """The first apply updates the hub; the other replica is kept and listed as out-of-sync."""
    live, _config_path, managed, target_a, target_b = live_workspace
    _mark_loser_out_of_sync(live, target_a, target_b)

    assert (managed / "shared.txt").read_text() == "from-a"
    assert (target_a / "shared.txt").read_text() == "from-a"
    assert (target_b / "shared.txt").read_text() == "from-b"
    assert (target_b, "shared.txt") in live.out_of_sync
    assert (target_a, "shared.txt") not in live.out_of_sync


def test_out_of_sync_skipped_by_later_fan_out_and_further_edits_discarded(
    live_workspace: tuple[LiveSync, Path, Path, Path, Path],
) -> None:
    """Later hub changes skip the isolated replica; its further edits do not reach the hub."""
    live, _config_path, managed, target_a, target_b = live_workspace
    _mark_loser_out_of_sync(live, target_a, target_b)

    (managed / "shared.txt").write_text("hub-later")
    live.tick()

    assert (target_a / "shared.txt").read_text() == "hub-later"
    assert (target_b / "shared.txt").read_text() == "from-b"

    (target_b / "shared.txt").write_text("from-b-later")
    live.tick()

    assert (managed / "shared.txt").read_text() == "hub-later"
    assert (target_a / "shared.txt").read_text() == "hub-later"
    assert (target_b / "shared.txt").read_text() == "from-b-later"
    assert (target_b, "shared.txt") in live.out_of_sync


def test_equal_hashes_clear_out_of_sync_and_rejoin_fan_out(
    live_workspace: tuple[LiveSync, Path, Path, Path, Path],
    isolated_home: dict[str, str],
) -> None:
    """Matching the hub clears out-of-sync and the replica receives later fan-out."""
    live, config_path, managed, target_a, target_b = live_workspace
    _mark_loser_out_of_sync(live, target_a, target_b)

    (target_b / "shared.txt").write_text("from-a")
    live.tick()

    assert (target_b, "shared.txt") not in live.out_of_sync
    assert (target_b / "shared.txt").read_text() == "from-a"
    _persist(config_path, live)
    cleared = invoke_cli(["--config", str(config_path), "daemon", "status"], env=isolated_home)
    assert "Out-of-sync:" not in cleared.output

    (managed / "shared.txt").write_text("from-hub")
    live.tick()

    assert (target_a / "shared.txt").read_text() == "from-hub"
    assert (target_b / "shared.txt").read_text() == "from-hub"


def test_delete_past_generation_gap_holds_then_delete_wins(
    live_workspace: tuple[LiveSync, Path, Path, Path, Path],
) -> None:
    """Gap greater than 3 stores hub bytes under .blf-held, then live-delete-wins."""
    live, _config_path, managed, target_a, target_b = live_workspace
    (target_b / "shared.txt").write_text("divergent")
    (target_a / "shared.txt").write_text("a1")
    live.tick()
    (target_a / "shared.txt").write_text("a2")
    live.tick()
    (target_a / "shared.txt").write_text("a3")
    live.tick()
    (target_a / "shared.txt").write_text("a4")
    live.tick()
    assert (managed / "shared.txt").read_text() == "a4"

    (target_b / "shared.txt").unlink()
    live.tick()

    assert not (managed / "shared.txt").exists()
    assert not (target_a / "shared.txt").exists()
    assert not (target_b / "shared.txt").exists()
    held_root = managed / ".blf-held"
    slots = [path for path in held_root.iterdir() if path.is_dir()]
    assert len(slots) == 1
    assert (slots[0] / "content").read_text() == "a4"
    meta = yaml.safe_load((slots[0] / "reason.yml").read_text())
    assert meta["reason"] == "delete-gap"
    assert meta["clause"] == _DELETE_GAP_CLAUSE
    assert not (target_a / ".blf-held").exists()
    assert not (target_b / ".blf-held").exists()


def test_held_directory_is_not_projected_including_sync_all(tmp_path: Path) -> None:
    """``.blf-held`` is reserved and is not copied onto targets, including sync-all."""
    config_path, managed, target_a, target_b = _write_two_target_workspace(tmp_path)
    held_slot = managed / ".blf-held" / "slot"
    held_slot.mkdir(parents=True)
    (held_slot / "content").write_text("secret")
    live = _live_sync(config_path)

    assert not (target_a / ".blf-held").exists()
    assert not (target_b / ".blf-held").exists()
    (held_slot / "content").write_text("secret-changed")
    live.tick()
    assert not (target_a / ".blf-held").exists()
    assert not (target_b / ".blf-held").exists()
    (managed / "shared.txt").write_text("after-held")
    live.tick()
    assert (target_a / "shared.txt").read_text() == "after-held"
    assert (target_b / "shared.txt").read_text() == "after-held"
    assert not (target_a / ".blf-held").exists()
    assert not (target_b / ".blf-held").exists()


def test_status_lists_out_of_sync_and_held_copies(
    live_workspace: tuple[LiveSync, Path, Path, Path, Path],
    isolated_home: dict[str, str],
) -> None:
    """daemon status lists out-of-sync paths and held-copy clauses."""
    live, config_path, managed, target_a, target_b = live_workspace
    _mark_loser_out_of_sync(live, target_a, target_b)
    sidecar = config_path.parent / "hub-bytes.txt"
    sidecar.write_text("kept-hub-bytes")
    store_held_copy(
        managed,
        rel_path=Path("shared.txt"),
        source=sidecar,
        replica=target_b,
        reason=REASON_DELETE_GAP,
    )
    _persist(config_path, live)

    result = invoke_cli(["--config", str(config_path), "daemon", "status"], env=isolated_home)

    assert result.exit_code == 0, result.output
    assert "out-of-sync" in result.output.lower() or "out of sync" in result.output.lower()
    assert "shared.txt" in result.output
    assert str(target_b) in result.output
    assert _DELETE_GAP_CLAUSE in result.output
    assert ".blf-held" in result.output
    assert (managed / ".blf-held").is_dir()


def test_start_warns_and_acks_without_blocking(
    live_workspace: tuple[LiveSync, Path, Path, Path, Path],
    isolated_home: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """start prints isolation WARNINGs, requires ack, and still backgrounds on no."""
    live, config_path, _managed, target_a, target_b = live_workspace
    _mark_loser_out_of_sync(live, target_a, target_b)
    _persist(config_path, live)
    monkeypatch.setattr("beyond_local_file.operations.daemon.stdin_is_tty", lambda: True)

    result = _invoke_start(config_path, isolated_home, input_text="n\n")

    assert result.exit_code == 0, result.output
    assert "WARNING" in result.output
    assert "shared.txt" in result.output
    assert str(target_b) in result.output
    assert "without resolving" in result.output.lower() or "continue" in result.output.lower()
    status = invoke_cli(["--config", str(config_path), "daemon", "status"], env=isolated_home)
    assert "running" in status.output.lower()
    stop_daemon(config_path, isolated_home)


def test_reload_warns_and_acks_without_blocking(
    daemon_workspace: tuple[Path, Path, Path, Path],
    isolated_home: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reload prints isolation WARNINGs, requires ack, and does not stop the daemon."""
    config_path, managed, target_a, target_b = daemon_workspace
    start_daemon(config_path, isolated_home)
    _wait_until(lambda: (target_a / "shared.txt").is_file() and (target_a / "shared.txt").read_text() == "v0")
    (target_a / "shared.txt").write_text("from-a")
    (target_b / "shared.txt").write_text("from-b")
    _wait_until(lambda: (managed / "shared.txt").read_text() == "from-a")
    _wait_until(lambda: (target_b / "shared.txt").read_text() == "from-b")
    monkeypatch.setattr("beyond_local_file.operations.daemon.stdin_is_tty", lambda: True)

    result = _invoke_reload(config_path, isolated_home, input_text="n\n")

    assert result.exit_code == 0, result.output
    assert "WARNING" in result.output
    assert "shared.txt" in result.output
    assert str(target_b) in result.output
    assert "without resolving" in result.output.lower() or "continue" in result.output.lower()
    status = invoke_cli(["--config", str(config_path), "daemon", "status"], env=isolated_home)
    assert "running" in status.output.lower()
    assert "not running" not in status.output.lower()


def test_reason_clause_delete_gap_is_stable() -> None:
    """Hold-reason clause text is the same string status and WARNINGs must show."""
    assert (
        reason_clause("delete-gap", path="shared.txt", replica="/tmp/target-b")
        == _DELETE_GAP_CLAUSE
    )
