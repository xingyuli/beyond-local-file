"""Create item-add is a named LiveSync job: hub copy, fan-out, hold, git exclude, gen 0."""

from __future__ import annotations

from pathlib import Path

from beyond_local_file.config import Config
from beyond_local_file.daemon.catchup import run_catch_up
from beyond_local_file.daemon.live import LiveSync
from beyond_local_file.daemon.store import get_generation
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


def test_install_item_copies_source_to_hub_and_fans_out(tmp_path: Path) -> None:
    """Item-add copies alpha onto the hub and example and records generation 0."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path)
    (alpha / "notes.md").write_text("adopt me")
    live = _live_sync(config_path)
    live.replace_projects(_with_items(live.projects, ["notes.md"]))

    live.install_item(alpha, "notes.md")

    assert (hub / "notes.md").read_text() == "adopt me"
    assert (example / "notes.md").read_text() == "adopt me"
    assert (alpha / "notes.md").is_file()
    assert not (alpha / "notes.md").is_symlink()
    assert (alpha / "notes.md").read_text() == "adopt me"
    assert get_generation(live.baseline, hub, "notes.md") == 0
    assert get_generation(live.baseline, alpha, "notes.md") == 0
    assert get_generation(live.baseline, example, "notes.md") == 0
    live.tick()
    assert get_generation(live.baseline, hub, "notes.md") == 0
    (alpha / "notes.md").write_text("edited")
    live.tick()
    assert (hub / "notes.md").read_text() == "edited"
    assert (example / "notes.md").read_text() == "edited"
    assert get_generation(live.baseline, hub, "notes.md") == 1


def test_install_item_holds_colliding_replica_then_overwrites(tmp_path: Path) -> None:
    """Different bytes on example are held create-overwrite, then overwritten from the hub."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path)
    (alpha / "notes.md").write_text("adopt me")
    (example / "notes.md").write_text("other bytes")
    live = _live_sync(config_path)
    live.replace_projects(_with_items(live.projects, ["notes.md"]))

    live.install_item(alpha, "notes.md")

    assert (example / "notes.md").read_text() == "adopt me"
    copies = list_held_copies(hub)
    assert len(copies) == 1
    assert copies[0].reason == "create-overwrite"
    assert (copies[0].slot / "content").read_text() == "other bytes"


def test_install_item_leaves_equal_replica_bytes(tmp_path: Path) -> None:
    """Equal bytes on example stay in place and are not held."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path)
    (alpha / "notes.md").write_text("adopt me")
    (example / "notes.md").write_text("adopt me")
    live = _live_sync(config_path)
    live.replace_projects(_with_items(live.projects, ["notes.md"]))

    live.install_item(alpha, "notes.md")

    assert (example / "notes.md").read_text() == "adopt me"
    assert list_held_copies(hub) == ()
    assert get_generation(live.baseline, example, "notes.md") == 0


def test_install_item_writes_git_exclude_on_projecting_replicas(tmp_path: Path) -> None:
    """Git exclude is added on every replica that starts projecting the item."""
    config_path, _hub, alpha, example = _write_lab_workspace(tmp_path)
    alpha_exclude = _make_git_repo(alpha)
    example_exclude = _make_git_repo(example)
    (alpha / "notes.md").write_text("adopt me")
    live = _live_sync(config_path)
    live.replace_projects(_with_items(live.projects, ["notes.md"]))

    live.install_item(alpha, "notes.md")

    assert "notes.md" in alpha_exclude.read_text()
    assert "notes.md" in example_exclude.read_text()


def test_install_item_copies_nested_rel_to_hub_and_replica(tmp_path: Path) -> None:
    """A nested item is copied at the full rel_path, not the basename."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path)
    source = alpha / ".kiro" / "specs" / "foo"
    source.mkdir(parents=True)
    (source / "file.txt").write_text("content")
    live = _live_sync(config_path)
    live.replace_projects(_with_items(live.projects, [".kiro/specs/foo"]))

    live.install_item(alpha, ".kiro/specs/foo")

    assert (hub / ".kiro" / "specs" / "foo" / "file.txt").read_text() == "content"
    assert (example / ".kiro" / "specs" / "foo" / "file.txt").read_text() == "content"
    assert not (hub / "foo").exists()
    assert get_generation(live.baseline, hub, ".kiro/specs/foo") == 0
    assert get_generation(live.baseline, hub, ".kiro/specs/foo/file.txt") == 0


def test_install_item_git_exclude_uses_full_rel_path(tmp_path: Path) -> None:
    """Git exclude records the full rel_path, not the basename."""
    config_path, _hub, alpha, example = _write_lab_workspace(tmp_path)
    alpha_exclude = _make_git_repo(alpha)
    example_exclude = _make_git_repo(example)
    source = alpha / ".kiro" / "specs" / "foo"
    source.mkdir(parents=True)
    (source / "file.txt").write_text("content")
    live = _live_sync(config_path)
    live.replace_projects(_with_items(live.projects, [".kiro/specs/foo"]))

    live.install_item(alpha, ".kiro/specs/foo")

    for exclude in (alpha_exclude, example_exclude):
        content = exclude.read_text()
        assert ".kiro/specs/foo" in content
        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
        assert "foo" not in lines


def test_install_item_does_not_drain_mailbox(tmp_path: Path) -> None:
    """Item-add leaves a queued path change for later apply."""
    config_path, hub, alpha, example = _write_lab_workspace(tmp_path, items=("shared.txt",))
    live = _live_sync(config_path)
    (alpha / "shared.txt").write_text("queued")
    live.observe()
    (alpha / "notes.md").write_text("adopt me")
    live.replace_projects(_with_items(live.projects, ["shared.txt", "notes.md"]))

    live.install_item(alpha, "notes.md")

    assert (hub / "shared.txt").read_text() == "v0"
    assert (example / "shared.txt").read_text() == "v0"
    assert (hub / "notes.md").read_text() == "adopt me"
    live.apply()
    assert (hub / "shared.txt").read_text() == "queued"
    assert (example / "shared.txt").read_text() == "queued"
    assert get_generation(live.baseline, hub, "notes.md") == 0
    assert get_generation(live.baseline, hub, "shared.txt") == 1
