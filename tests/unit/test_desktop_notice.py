"""Desktop notices at the public notice seam."""

from __future__ import annotations

from pathlib import Path

import pytest

from beyond_local_file.daemon.live import LiveSync
from beyond_local_file.daemon.notice import (
    Banner,
    IsolationSnapshot,
    banners_for,
    emit_isolation_notices,
    new_isolation_rels,
    snapshot_isolation,
)
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


def test_two_replicas_of_one_path_count_as_one_path() -> None:
    """New out-of-sync pairs on the same relative path are one banner path."""
    before = IsolationSnapshot(oos=frozenset(), held=frozenset())
    after = IsolationSnapshot(
        oos=frozenset({("/tmp/a", "shared.txt"), ("/tmp/b", "shared.txt")}),
        held=frozenset(),
    )
    oos_rels, held_rels = new_isolation_rels(before, after)
    assert oos_rels == ("shared.txt",)
    assert held_rels == ()


def test_existing_out_of_sync_pair_is_not_new() -> None:
    """A pair already persisted in this process does not count as first isolation."""
    pair = ("/tmp/a", "shared.txt")
    before = IsolationSnapshot(oos=frozenset({pair}), held=frozenset())
    after = IsolationSnapshot(oos=frozenset({pair}), held=frozenset())
    assert new_isolation_rels(before, after) == ((), ())


def test_new_held_slot_uses_its_relative_path() -> None:
    """A new held slot is reported by item path, not slot directory name."""
    before = IsolationSnapshot(oos=frozenset(), held=frozenset())
    after = IsolationSnapshot(
        oos=frozenset(),
        held=frozenset({("/tmp/held/slot-1", "shared.txt")}),
    )
    oos_rels, held_rels = new_isolation_rels(before, after)
    assert oos_rels == ()
    assert held_rels == ("shared.txt",)


def test_cleared_out_of_sync_does_not_toast() -> None:
    """Clearing isolation is not a desktop notice."""
    before = IsolationSnapshot(oos=frozenset({("/tmp/a", "shared.txt")}), held=frozenset())
    after = IsolationSnapshot(oos=frozenset(), held=frozenset())
    assert new_isolation_rels(before, after) == ((), ())


def test_emit_sends_composed_banners(monkeypatch: pytest.MonkeyPatch) -> None:
    """Emit sends title and body through the injected sender."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "beyond_local_file.daemon.notice.send_banner",
        lambda title, body: sent.append((title, body)),
    )
    before = IsolationSnapshot(oos=frozenset(), held=frozenset())
    after = IsolationSnapshot(oos=frozenset({("/tmp/a", "shared.txt")}), held=frozenset())
    emit_isolation_notices(project="lab-app", before=before, after=after, skip=False)
    assert sent == [("blf: out-of-sync", "shared.txt in lab-app")]


def test_emit_skips_tty_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolation caused by a TTY shell does not send a banner."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "beyond_local_file.daemon.notice.send_banner",
        lambda title, body: sent.append((title, body)),
    )
    before = IsolationSnapshot(oos=frozenset(), held=frozenset())
    after = IsolationSnapshot(oos=frozenset({("/tmp/a", "shared.txt")}), held=frozenset())
    emit_isolation_notices(project="lab-app", before=before, after=after, skip=True)
    assert sent == []


def test_emit_respects_opt_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """BLF_NOTIFY=0 disables desktop notices."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setenv("BLF_NOTIFY", "0")
    monkeypatch.setattr(
        "beyond_local_file.daemon.notice.send_banner",
        lambda title, body: sent.append((title, body)),
    )
    before = IsolationSnapshot(oos=frozenset(), held=frozenset())
    after = IsolationSnapshot(oos=frozenset({("/tmp/a", "shared.txt")}), held=frozenset())
    emit_isolation_notices(project="lab-app", before=before, after=after, skip=False)
    assert sent == []


def test_sender_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """A refused OS banner must not fail persist."""

    def _fail(title: str, body: str) -> None:
        del title, body
        raise RuntimeError("denied")

    monkeypatch.setattr("beyond_local_file.daemon.notice.send_banner", _fail)
    before = IsolationSnapshot(oos=frozenset(), held=frozenset())
    after = IsolationSnapshot(oos=frozenset({("/tmp/a", "shared.txt")}), held=frozenset())
    emit_isolation_notices(project="lab-app", before=before, after=after, skip=False)


def test_live_tick_snapshot_sees_new_out_of_sync(
    live_workspace: tuple,
) -> None:
    """A live apply that isolates a replica shows up as a new out-of-sync rel."""
    live, _config_path, _managed, target_a, target_b = live_workspace
    before = snapshot_isolation(live)
    _mark_loser_out_of_sync(live, target_a, target_b)
    oos_rels, held_rels = new_isolation_rels(before, snapshot_isolation(live))
    assert oos_rels == ("shared.txt",)
    assert held_rels == ()


def test_live_hold_snapshot_sees_new_held_slot(
    live_workspace: tuple,
    isolated_home: dict[str, str],
) -> None:
    """A new held slot on disk is a new held rel on the snapshot."""
    del isolated_home
    live, _config_path, managed, _target_a, target_b = live_workspace
    before = snapshot_isolation(live)
    source = managed / "kept.txt"
    source.write_text("hold-me")
    store_held_copy(
        managed,
        rel_path=Path("kept.txt"),
        source=source,
        replica=target_b,
        reason=REASON_DELETE_GAP,
    )
    oos_rels, held_rels = new_isolation_rels(before, snapshot_isolation(live))
    assert oos_rels == ()
    assert held_rels == ("kept.txt",)
