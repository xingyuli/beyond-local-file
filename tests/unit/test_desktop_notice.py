"""Desktop notices at the public notice seam."""

from __future__ import annotations

from pathlib import Path

import pytest

from beyond_local_file.daemon.live import LiveSync
from beyond_local_file.daemon.notice import Banner, banners_for, emit_desktop_notices
from beyond_local_file.daemon.oos_held import OosAndHeld, OosRow, list_oos_and_held, new_rels
from beyond_local_file.held import REASON_DELETE_GAP, store_held_copy
from tests.unit.test_out_of_sync_and_held import (
    _live_sync,
    _mark_loser_out_of_sync,
    _write_two_target_workspace,
)


@pytest.fixture
def live_workspace(tmp_path: Path, isolated_home: dict[str, str]) -> tuple[LiveSync, Path, Path, Path, Path]:
    """In-process live observer after a fresh catch-up onto two targets."""
    del isolated_home
    config_path, managed, target_a, target_b = _write_two_target_workspace(tmp_path)
    live = _live_sync(config_path)
    return live, config_path, managed.resolve(), target_a.resolve(), target_b.resolve()


def _oos_listing(*replicas: str, rel: str = "shared.txt") -> OosAndHeld:
    return OosAndHeld(
        oos=tuple(OosRow(replica=Path(replica), rel=rel, reason="stale-base", clause="") for replica in replicas),
        held=(),
    )


def test_one_out_of_sync_path_names_managed_project() -> None:
    """A single new out-of-sync path names the managed project, not a replica."""
    banners = banners_for(project="lab-app", oos_rels=("shared.txt",), held_rels=())
    assert banners == (Banner(title="blf: out-of-sync", body="shared.txt in lab-app"),)


def test_several_out_of_sync_paths_use_a_count() -> None:
    """Several new out-of-sync paths on one job become one counted banner."""
    banners = banners_for(
        project="lab-app",
        oos_rels=("a.txt", "b.txt", "c.txt"),
        held_rels=(),
    )
    assert banners == (Banner(title="blf: out-of-sync", body="3 paths in lab-app"),)


def test_one_held_path_is_its_own_banner() -> None:
    """A new held copy is a separate kind, still named by managed project."""
    banners = banners_for(project="lab-app", oos_rels=(), held_rels=("shared.txt",))
    assert banners == (Banner(title="blf: held copy", body="shared.txt in lab-app"),)


def test_out_of_sync_and_held_are_two_banners() -> None:
    """One persist job can emit one out-of-sync banner and one held banner."""
    banners = banners_for(
        project="lab-app",
        oos_rels=("shared.txt",),
        held_rels=("notes.md",),
    )
    assert banners == (
        Banner(title="blf: out-of-sync", body="shared.txt in lab-app"),
        Banner(title="blf: held copy", body="notes.md in lab-app"),
    )


def test_no_new_paths_emits_nothing() -> None:
    """Leftover isolation that did not grow is silent."""
    assert banners_for(project="lab-app", oos_rels=(), held_rels=()) == ()


def test_emit_sends_composed_banners(monkeypatch: pytest.MonkeyPatch) -> None:
    """Emit sends title and body through the injected sender."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "beyond_local_file.daemon.notice.send_banner",
        lambda title, body: sent.append((title, body)),
    )
    emit_desktop_notices(
        project="lab-app",
        before=_oos_listing(),
        after=_oos_listing("/tmp/alpha"),
        skip=False,
    )
    assert sent == [("blf: out-of-sync", "shared.txt in lab-app")]


def test_emit_skips_tty_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolation caused by a TTY shell does not send a banner."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "beyond_local_file.daemon.notice.send_banner",
        lambda title, body: sent.append((title, body)),
    )
    emit_desktop_notices(
        project="lab-app",
        before=_oos_listing(),
        after=_oos_listing("/tmp/alpha"),
        skip=True,
    )
    assert sent == []


def test_emit_respects_opt_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """BLF_NOTIFY=0 disables desktop notices."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setenv("BLF_NOTIFY", "0")
    monkeypatch.setattr(
        "beyond_local_file.daemon.notice.send_banner",
        lambda title, body: sent.append((title, body)),
    )
    emit_desktop_notices(
        project="lab-app",
        before=_oos_listing(),
        after=_oos_listing("/tmp/alpha"),
        skip=False,
    )
    assert sent == []


def test_sender_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """A refused OS banner must not fail persist."""

    def _fail(title: str, body: str) -> None:
        del title, body
        raise RuntimeError("denied")

    monkeypatch.setattr("beyond_local_file.daemon.notice.send_banner", _fail)
    emit_desktop_notices(
        project="lab-app",
        before=_oos_listing(),
        after=_oos_listing("/tmp/alpha"),
        skip=False,
    )


def test_live_tick_snapshot_sees_new_out_of_sync(
    live_workspace: tuple,
) -> None:
    """A live apply that isolates a replica shows up as a new out-of-sync rel."""
    live, _config_path, _managed, target_a, target_b = live_workspace
    before = list_oos_and_held(live.baseline, live.projects)
    _mark_loser_out_of_sync(live, target_a, target_b)
    oos_rels, held_rels = new_rels(before, list_oos_and_held(live.baseline, live.projects))
    assert oos_rels == ("shared.txt",)
    assert held_rels == ()


def test_live_hold_snapshot_sees_new_held_slot(
    live_workspace: tuple,
    isolated_home: dict[str, str],
) -> None:
    """A new held slot on disk is a new held rel on the listing."""
    del isolated_home
    live, _config_path, managed, _target_a, target_b = live_workspace
    before = list_oos_and_held(live.baseline, live.projects)
    source = managed / "kept.txt"
    source.write_text("hold-me")
    store_held_copy(
        managed,
        rel_path=Path("kept.txt"),
        source=source,
        replica=target_b,
        reason=REASON_DELETE_GAP,
    )
    oos_rels, held_rels = new_rels(before, list_oos_and_held(live.baseline, live.projects))
    assert oos_rels == ()
    assert held_rels == ("kept.txt",)
