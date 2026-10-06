"""Out-of-sync and held-copy listing at the shared read seam."""

from __future__ import annotations

from pathlib import Path

from beyond_local_file.daemon.oos_held import OosAndHeld, OosRow, list_oos_and_held, new_rels
from beyond_local_file.daemon.store import REASON_STALE_BASE, oos_reason_clause, path_state
from beyond_local_file.held import REASON_DELETE_GAP, HeldCopy, store_held_copy
from beyond_local_file.model.config import ConfigProject, Mapping


def _project(tmp_path: Path, *, name: str = "lab-app") -> tuple[Path, Path, ConfigProject]:
    hub = tmp_path / name
    replica = tmp_path / "alpha"
    hub.mkdir()
    replica.mkdir()
    project = ConfigProject(
        managed_project_name=name,
        managed_project_path=hub,
        mappings=[Mapping(targets=[replica], subpaths=None)],
    )
    return hub, replica, project


def test_empty_listing_is_falsy() -> None:
    """No out-of-sync rows and no held copies is an empty listing."""
    assert not list_oos_and_held({}, {})


def test_listing_carries_out_of_sync_reason_and_clause(tmp_path: Path) -> None:
    """An out-of-sync baseline row becomes an OosRow with reason and clause."""
    _hub, replica, project = _project(tmp_path)
    clause = oos_reason_clause(
        REASON_STALE_BASE,
        replica=str(replica),
        path="shared.txt",
        gen=1,
        winner=str(tmp_path / "example"),
    )
    state = path_state(True, "abc", gen=1, oos=True)
    state["reason"] = REASON_STALE_BASE
    state["clause"] = clause
    trees = {str(replica): {"shared.txt": state}}
    listing = list_oos_and_held(trees, {"lab-app": project})
    assert listing
    assert listing.oos == (OosRow(replica=replica, rel="shared.txt", reason=REASON_STALE_BASE, clause=clause),)
    assert listing.held == ()


def test_listing_held_once_per_managed_root(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Two project entries for the same hub list the held copy once."""
    del isolated_home
    hub, replica, project = _project(tmp_path)
    duplicate = ConfigProject(
        managed_project_name="lab-app",
        managed_project_path=hub,
        mappings=[Mapping(targets=[tmp_path / "example"], subpaths=None)],
    )
    (tmp_path / "example").mkdir()
    sidecar = tmp_path / "kept.txt"
    sidecar.write_text("hold-me")
    slot = store_held_copy(
        hub,
        rel_path=Path("kept.txt"),
        source=sidecar,
        replica=replica,
        reason=REASON_DELETE_GAP,
    )
    listing = list_oos_and_held({}, {"a": project, "b": duplicate})
    assert listing.oos == ()
    assert len(listing.held) == 1
    copy = listing.held[0]
    assert copy.slot == slot
    assert copy.path == "kept.txt"
    assert copy.replica == replica.as_posix()
    assert copy.reason == REASON_DELETE_GAP


def test_new_rels_two_replicas_of_one_path_are_one_rel() -> None:
    """New out-of-sync pairs on the same relative path are one banner path."""
    before = OosAndHeld(oos=(), held=())
    after = OosAndHeld(
        oos=(
            OosRow(replica=Path("/tmp/alpha"), rel="shared.txt", reason="stale-base", clause=""),
            OosRow(replica=Path("/tmp/example"), rel="shared.txt", reason="stale-base", clause=""),
        ),
        held=(),
    )
    oos_rels, held_rels = new_rels(before, after)
    assert oos_rels == ("shared.txt",)
    assert held_rels == ()


def test_new_rels_existing_pair_is_not_new() -> None:
    """A pair already in the listing does not count as first-seen."""
    row = OosRow(replica=Path("/tmp/alpha"), rel="shared.txt", reason="stale-base", clause="")
    listing = OosAndHeld(oos=(row,), held=())
    assert new_rels(listing, listing) == ((), ())


def test_new_rels_second_replica_of_listed_path_is_new() -> None:
    """A new replica of an already-listed path still counts as a new rel."""
    before = OosAndHeld(
        oos=(OosRow(replica=Path("/tmp/alpha"), rel="shared.txt", reason="stale-base", clause=""),),
        held=(),
    )
    after = OosAndHeld(
        oos=(
            OosRow(replica=Path("/tmp/alpha"), rel="shared.txt", reason="stale-base", clause=""),
            OosRow(replica=Path("/tmp/example"), rel="shared.txt", reason="stale-base", clause=""),
        ),
        held=(),
    )
    oos_rels, held_rels = new_rels(before, after)
    assert oos_rels == ("shared.txt",)
    assert held_rels == ()


def test_new_rels_held_slot_uses_item_path() -> None:
    """A new held slot is reported by item path, not slot directory name."""
    before = OosAndHeld(oos=(), held=())
    after = OosAndHeld(
        oos=(),
        held=(
            HeldCopy(
                slot=Path("/tmp/held/slot-1"),
                reason=REASON_DELETE_GAP,
                path="shared.txt",
                replica="/tmp/example",
                clause="",
            ),
        ),
    )
    oos_rels, held_rels = new_rels(before, after)
    assert oos_rels == ()
    assert held_rels == ("shared.txt",)


def test_new_rels_cleared_out_of_sync_is_silent() -> None:
    """Clearing an out-of-sync row is not a new rel."""
    before = OosAndHeld(
        oos=(OosRow(replica=Path("/tmp/alpha"), rel="shared.txt", reason="stale-base", clause=""),),
        held=(),
    )
    after = OosAndHeld(oos=(), held=())
    assert new_rels(before, after) == ((), ())
