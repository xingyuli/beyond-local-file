"""Restore, remove, and ingest retract are named LiveSync jobs."""

from __future__ import annotations

from pathlib import Path

from beyond_local_file.config import Config
from beyond_local_file.daemon.catchup import run_catch_up
from beyond_local_file.daemon.live import LiveSync
from beyond_local_file.daemon.store import get_generation, get_state
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


def _live_sync(config_path: Path) -> LiveSync:
    """Catch-up mappings and return a live observer for the committed trees."""
    cfg = Config(config_path)
    cfg.load()
    projects = cfg.get_config_projects()
    baseline = run_catch_up(projects, config_path.parent, None)
    return LiveSync(projects, baseline)


def _make_git_repo(directory: Path) -> Path:
    """Create a fake Git repository root and return its exclude file path."""
    exclude = directory / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True)
    exclude.write_text("# preserved\n")
    return exclude


def _adopt_notes(tmp_path: Path) -> tuple[LiveSync, Path, Path, Path]:
    """Install notes.md from alpha onto lab-app and example."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path)
    (alpha / "notes.md").write_text("adopt me")
    live = _live_sync(config_path)
    live.replace_projects(_with_items(live.projects, ["notes.md"]))
    live.install_item(alpha, "notes.md")
    return live, hub, alpha, example


def test_restore_item_deletes_hub_and_other_replicas_and_leaves_source(tmp_path: Path) -> None:
    """Restore from alpha deletes hub and example copies; alpha's file remains."""
    live, hub, alpha, example = _adopt_notes(tmp_path)

    live.restore_item(alpha, "notes.md")

    assert not (hub / "notes.md").exists()
    assert (alpha / "notes.md").is_file()
    assert not (alpha / "notes.md").is_symlink()
    assert (alpha / "notes.md").read_text() == "adopt me"
    assert not (example / "notes.md").exists()
    assert not get_state(live.baseline, hub, "notes.md").get("present")
    assert not get_state(live.baseline, example, "notes.md").get("present")
    assert get_state(live.baseline, alpha, "notes.md").get("present")
    assert get_generation(live.baseline, hub, "notes.md") == 0
    live.tick()
    assert not (hub / "notes.md").exists()
    assert (alpha / "notes.md").read_text() == "adopt me"


def test_restore_item_strips_git_exclude_on_every_replica_that_stops_projecting(tmp_path: Path) -> None:
    """Git exclude comes off alpha (file remains) and example (file gone)."""
    config_path, _hub, alpha, example = _write_lab_workspace(tmp_path)
    alpha_exclude = _make_git_repo(alpha)
    example_exclude = _make_git_repo(example)
    (alpha / "notes.md").write_text("adopt me")
    live = _live_sync(config_path)
    live.replace_projects(_with_items(live.projects, ["notes.md"]))
    live.install_item(alpha, "notes.md")

    live.restore_item(alpha, "notes.md")

    assert "notes.md" not in alpha_exclude.read_text()
    assert "# preserved" in alpha_exclude.read_text()
    assert "notes.md" not in example_exclude.read_text()
    assert "# preserved" in example_exclude.read_text()


def test_restore_item_does_not_increment_generation(tmp_path: Path) -> None:
    """Restore records absence at the observed generation; it does not apply a new one."""
    live, hub, alpha, example = _adopt_notes(tmp_path)
    (alpha / "notes.md").write_text("edited")
    live.tick()
    assert get_generation(live.baseline, hub, "notes.md") == 1

    live.restore_item(alpha, "notes.md")

    assert not (hub / "notes.md").exists()
    assert not (example / "notes.md").exists()
    assert get_generation(live.baseline, hub, "notes.md") == 1
    assert get_generation(live.baseline, example, "notes.md") == 1


def test_restore_item_does_not_drain_mailbox(tmp_path: Path) -> None:
    """Restore leaves a queued path change for later apply."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path, items=("shared.txt",))
    live = _live_sync(config_path)
    (alpha / "shared.txt").write_text("queued")
    live.observe()
    (alpha / "notes.md").write_text("adopt me")
    live.replace_projects(_with_items(live.projects, ["shared.txt", "notes.md"]))
    live.install_item(alpha, "notes.md")

    live.restore_item(alpha, "notes.md")

    assert (hub / "shared.txt").read_text() == "v0"
    assert not (hub / "notes.md").exists()
    assert (alpha / "notes.md").read_text() == "adopt me"
    live.apply()
    assert (hub / "shared.txt").read_text() == "queued"
    assert (example / "shared.txt").read_text() == "queued"
    assert not (hub / "notes.md").exists()


def test_restore_item_deletes_nested_rel_on_hub_and_other_replica(tmp_path: Path) -> None:
    """A nested item is removed at the full rel_path on hub and example."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path)
    source = alpha / ".kiro" / "specs" / "foo"
    source.mkdir(parents=True)
    (source / "file.txt").write_text("content")
    live = _live_sync(config_path)
    live.replace_projects(_with_items(live.projects, [".kiro/specs/foo"]))
    live.install_item(alpha, ".kiro/specs/foo")

    live.restore_item(alpha, ".kiro/specs/foo")

    assert not (hub / ".kiro" / "specs" / "foo").exists()
    assert (source / "file.txt").read_text() == "content"
    assert not (example / ".kiro" / "specs" / "foo").exists()
    assert not get_state(live.baseline, hub, ".kiro/specs/foo").get("present")
    assert not get_state(live.baseline, hub, ".kiro/specs/foo/file.txt").get("present")


def test_remove_item_deletes_hub_and_every_projection(tmp_path: Path) -> None:
    """Remove deletes hub, alpha, and example copies and records absence on each."""
    live, hub, alpha, example = _adopt_notes(tmp_path)

    live.remove_item(alpha, "notes.md")

    assert not (hub / "notes.md").exists()
    assert not (alpha / "notes.md").exists()
    assert not (example / "notes.md").exists()
    assert not get_state(live.baseline, hub, "notes.md").get("present")
    assert not get_state(live.baseline, alpha, "notes.md").get("present")
    assert not get_state(live.baseline, example, "notes.md").get("present")
    assert get_generation(live.baseline, hub, "notes.md") == 0
    live.tick()
    assert not (hub / "notes.md").exists()
    assert not (alpha / "notes.md").exists()


def test_remove_item_strips_git_exclude_on_every_projecting_replica(tmp_path: Path) -> None:
    """Git exclude comes off every replica that stops projecting the item."""
    config_path, _hub, alpha, example = _write_lab_workspace(tmp_path)
    alpha_exclude = _make_git_repo(alpha)
    example_exclude = _make_git_repo(example)
    (alpha / "notes.md").write_text("adopt me")
    live = _live_sync(config_path)
    live.replace_projects(_with_items(live.projects, ["notes.md"]))
    live.install_item(alpha, "notes.md")

    live.remove_item(alpha, "notes.md")

    assert "notes.md" not in alpha_exclude.read_text()
    assert "notes.md" not in example_exclude.read_text()


def test_remove_item_deletes_leftover_projection_path_symlink(tmp_path: Path) -> None:
    """Mapping membership is enough to delete a leftover symlink at a projection path."""
    live, hub, alpha, example = _adopt_notes(tmp_path)
    (example / "notes.md").unlink()
    (example / "notes.md").symlink_to(hub / "notes.md")

    live.remove_item(alpha, "notes.md")

    assert not (hub / "notes.md").exists()
    assert not (alpha / "notes.md").exists()
    assert not (example / "notes.md").exists()
    assert not (example / "notes.md").is_symlink()


def test_remove_item_does_not_drain_mailbox(tmp_path: Path) -> None:
    """Remove leaves a queued path change for later apply."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path, items=("shared.txt",))
    live = _live_sync(config_path)
    (alpha / "shared.txt").write_text("queued")
    live.observe()
    (alpha / "notes.md").write_text("adopt me")
    live.replace_projects(_with_items(live.projects, ["shared.txt", "notes.md"]))
    live.install_item(alpha, "notes.md")

    live.remove_item(alpha, "notes.md")

    assert (hub / "shared.txt").read_text() == "v0"
    assert not (hub / "notes.md").exists()
    live.apply()
    assert (hub / "shared.txt").read_text() == "queued"
    assert (example / "shared.txt").read_text() == "queued"


def test_drop_replica_deletes_target_copy_keeps_hub(tmp_path: Path) -> None:
    """Ingest retract deletes the listed replica copy and leaves the hub copy."""
    live, hub, alpha, example = _adopt_notes(tmp_path)

    live.drop_replica(example, "notes.md")

    assert (hub / "notes.md").read_text() == "adopt me"
    assert (alpha / "notes.md").read_text() == "adopt me"
    assert not (example / "notes.md").exists()
    assert get_state(live.baseline, hub, "notes.md").get("present")
    assert get_state(live.baseline, alpha, "notes.md").get("present")
    assert not get_state(live.baseline, example, "notes.md").get("present")
    assert get_generation(live.baseline, hub, "notes.md") == 0


def test_drop_replica_strips_git_exclude_on_that_replica_only(tmp_path: Path) -> None:
    """Ingest retract drops git exclude on the retracted replica, not siblings."""
    config_path, _hub, alpha, example = _write_lab_workspace(tmp_path)
    alpha_exclude = _make_git_repo(alpha)
    example_exclude = _make_git_repo(example)
    (alpha / "notes.md").write_text("adopt me")
    live = _live_sync(config_path)
    live.replace_projects(_with_items(live.projects, ["notes.md"]))
    live.install_item(alpha, "notes.md")

    live.drop_replica(example, "notes.md")

    assert "notes.md" in alpha_exclude.read_text()
    assert "notes.md" not in example_exclude.read_text()
    assert "# preserved" in example_exclude.read_text()


def test_drop_replica_does_not_drain_mailbox(tmp_path: Path) -> None:
    """Ingest retract leaves a queued path change for later apply."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path, items=("shared.txt",))
    live = _live_sync(config_path)
    (alpha / "shared.txt").write_text("queued")
    live.observe()
    (alpha / "notes.md").write_text("adopt me")
    live.replace_projects(_with_items(live.projects, ["shared.txt", "notes.md"]))
    live.install_item(alpha, "notes.md")

    live.drop_replica(example, "notes.md")

    assert (hub / "shared.txt").read_text() == "v0"
    assert (hub / "notes.md").read_text() == "adopt me"
    assert not (example / "notes.md").exists()
    live.apply()
    assert (hub / "shared.txt").read_text() == "queued"
    assert (example / "shared.txt").read_text() == "queued"
