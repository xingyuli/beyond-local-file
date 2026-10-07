"""Item discovery: declared vs present names, and path membership."""

from pathlib import Path

from beyond_local_file.discovery import item_covers_rel, item_names, rel_in_items
from beyond_local_file.held import HELD_DIR


def test_selective_keeps_declared_name_missing_from_hub(tmp_path: Path) -> None:
    """A selective mapping contributes declared names even when the hub file is missing."""
    hub = tmp_path / "lab-app"
    hub.mkdir()
    (hub / "notes.md").write_text("n")

    names = item_names(hub, ["notes.md", "ghost.md"])

    assert names == ["notes.md", "ghost.md"]


def test_selective_keeps_mapping_order_and_drops_held_and_empty(tmp_path: Path) -> None:
    """Declared names stay in yaml order; held-copy and empty entries are dropped."""
    hub = tmp_path / "lab-app"
    hub.mkdir()

    names = item_names(hub, ["b.md", "", f"{HELD_DIR}/x", "a.md", HELD_DIR])

    assert names == ["b.md", "a.md"]


def test_sync_all_returns_present_top_level_names_sorted(tmp_path: Path) -> None:
    """Sync-all enumerates the hub, skips the held-copy directory, and sorts."""
    hub = tmp_path / "lab-app"
    hub.mkdir()
    (hub / "notes.md").write_text("n")
    (hub / ".kiro").mkdir()
    (hub / "zebra").write_text("z")
    (hub / HELD_DIR).mkdir()

    names = item_names(hub, None)

    assert names == [".kiro", "notes.md", "zebra"]


def test_sync_all_missing_or_empty_hub_is_no_names(tmp_path: Path) -> None:
    """A missing or empty hub contributes nothing."""
    hub = tmp_path / "lab-app"
    assert item_names(tmp_path / "ghost", None) == []
    hub.mkdir()
    assert item_names(hub, None) == []


def test_item_covers_rel_requires_a_path_component() -> None:
    """CONTEXT.md does not cover CONTEXT-MAP.md."""
    assert item_covers_rel("notes.md", "notes.md")
    assert item_covers_rel("local-file", "local-file/tasks/x.md")
    assert not item_covers_rel("CONTEXT.md", "CONTEXT-MAP.md")
    assert not item_covers_rel("CONTEXT-MAP.md", "CONTEXT.md")


def test_rel_in_items_matches_any_covering_name() -> None:
    """A relative path belongs to a mapping when any contributed name covers it."""
    names = ["notes.md", "local-file"]
    assert rel_in_items("notes.md", names)
    assert rel_in_items("local-file/tasks/x.md", names)
    assert not rel_in_items("CONTEXT-MAP.md", ["CONTEXT.md"])
