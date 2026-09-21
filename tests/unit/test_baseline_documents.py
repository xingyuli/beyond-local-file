"""Item-document baseline under the set run directory."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from beyond_local_file.daemon.catchup import record_baseline
from beyond_local_file.daemon.process import state_dir
from beyond_local_file.daemon.store import load_baseline, save_baseline
from beyond_local_file.model.config import ConfigProject, Mapping
from tests.daemon_support import invoke_cli, start_daemon, stop_daemon


def test_save_uses_managed_project_name_when_projects_are_keyed_by_hub_path(tmp_path: Path) -> None:
    """Document paths use managed_project_name even if the project map is keyed by hub path."""
    managed = tmp_path / "alpha"
    target = tmp_path / "lab-app"
    managed.mkdir()
    target.mkdir()
    (managed / "shared.txt").write_text("hello")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"alpha: {target}\n")
    project = ConfigProject(
        managed_project_name="alpha",
        managed_project_path=managed,
        mappings=[Mapping(targets=[target], subpaths=None)],
    )
    trees = record_baseline({"alpha": project})

    save_baseline(config_path, trees, {str(managed): project})

    document = state_dir(config_path) / "baseline" / "alpha" / "files"
    assert document.is_file()
    data = yaml.safe_load(document.read_text(encoding="utf-8"))
    assert "shared.txt" in data["trees"][str(managed)]


def test_save_writes_file_items_under_managed_project_files_document(tmp_path: Path) -> None:
    """FILE items persist in baseline/<managed-project>/files, not baseline.yml."""
    managed = tmp_path / "alpha"
    target = tmp_path / "lab-app"
    managed.mkdir()
    target.mkdir()
    (managed / "shared.txt").write_text("hello")
    (target / "shared.txt").write_text("hello")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"alpha: {target}\n")
    projects = {
        "alpha": ConfigProject(
            managed_project_name="alpha",
            managed_project_path=managed,
            mappings=[Mapping(targets=[target], subpaths=None)],
        )
    }
    trees = record_baseline(projects)

    save_baseline(config_path, trees, projects)

    run_dir = state_dir(config_path)
    assert not (run_dir / "baseline.yml").exists()
    document = run_dir / "baseline" / "alpha" / "files"
    assert document.is_file()
    data = yaml.safe_load(document.read_text(encoding="utf-8"))
    hub_tree = data["trees"][str(managed)]
    replica_tree = data["trees"][str(target)]
    assert hub_tree["shared.txt"]["present"] is True
    assert replica_tree["shared.txt"]["present"] is True
    assert hub_tree["shared.txt"]["hash"] == replica_tree["shared.txt"]["hash"]
    assert load_baseline(config_path) == trees


def test_save_writes_directory_item_as_nested_files_and_subtree_documents(tmp_path: Path) -> None:
    """A DIRECTORY item stores direct files plus one document per child subtree."""
    managed = tmp_path / "alpha"
    target = tmp_path / "lab-app"
    for root in (managed, target):
        item = root / "local-file"
        (item / "requirements").mkdir(parents=True)
        (item / "tasks").mkdir()
        (item / "README.md").write_text("readme")
        (item / "requirements" / "a.txt").write_text("req")
        (item / "tasks" / "b.txt").write_text("task")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"alpha: {target}\n")
    projects = {
        "alpha": ConfigProject(
            managed_project_name="alpha",
            managed_project_path=managed,
            mappings=[Mapping(targets=[target], subpaths=None)],
        )
    }
    trees = record_baseline(projects)

    save_baseline(config_path, trees, projects)

    run_dir = state_dir(config_path)
    item_dir = run_dir / "baseline" / "alpha" / "local-file"
    files_doc = yaml.safe_load((item_dir / "files").read_text(encoding="utf-8"))
    requirements_doc = yaml.safe_load((item_dir / "requirements").read_text(encoding="utf-8"))
    tasks_doc = yaml.safe_load((item_dir / "tasks").read_text(encoding="utf-8"))
    hub_files = files_doc["trees"][str(managed)]
    assert hub_files["local-file"]["present"] is True
    assert hub_files["local-file"]["hash"] is None
    assert "local-file/README.md" in hub_files
    assert "local-file/requirements" not in hub_files
    assert "local-file/tasks" not in hub_files
    hub_requirements = requirements_doc["trees"][str(managed)]
    assert "local-file/requirements" in hub_requirements
    assert "local-file/requirements/a.txt" in hub_requirements
    assert "local-file/README.md" not in hub_requirements
    hub_tasks = tasks_doc["trees"][str(managed)]
    assert "local-file/tasks" in hub_tasks
    assert "local-file/tasks/b.txt" in hub_tasks
    assert str(target) in files_doc["trees"]
    assert str(target) in requirements_doc["trees"]
    assert not (run_dir / "baseline.yml").exists()
    assert not (run_dir / "baseline" / "alpha" / "files").exists()
    assert load_baseline(config_path) == trees


def test_load_baseline_reads_legacy_yaml_when_item_documents_are_absent(tmp_path: Path) -> None:
    """A leftover baseline.yml is still the baseline until item documents exist."""
    managed = tmp_path / "alpha"
    target = tmp_path / "lab-app"
    managed.mkdir()
    target.mkdir()
    (managed / "shared.txt").write_text("hello")
    (target / "shared.txt").write_text("hello")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"alpha: {target}\n")
    projects = {
        "alpha": ConfigProject(
            managed_project_name="alpha",
            managed_project_path=managed,
            mappings=[Mapping(targets=[target], subpaths=None)],
        )
    }
    trees = record_baseline(projects)
    save_baseline(config_path, trees)

    run_dir = state_dir(config_path)
    assert (run_dir / "baseline.yml").is_file()
    assert not (run_dir / "baseline").exists()
    assert load_baseline(config_path) == trees


def test_save_with_projects_replaces_legacy_yaml_with_item_documents(tmp_path: Path) -> None:
    """Writing item documents removes baseline.yml so load does not mix two sources."""
    managed = tmp_path / "alpha"
    target = tmp_path / "lab-app"
    managed.mkdir()
    target.mkdir()
    (managed / "shared.txt").write_text("hello")
    (target / "shared.txt").write_text("hello")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"alpha: {target}\n")
    projects = {
        "alpha": ConfigProject(
            managed_project_name="alpha",
            managed_project_path=managed,
            mappings=[Mapping(targets=[target], subpaths=None)],
        )
    }
    trees = record_baseline(projects)
    save_baseline(config_path, trees)
    save_baseline(config_path, trees, projects)

    run_dir = state_dir(config_path)
    assert not (run_dir / "baseline.yml").exists()
    assert (run_dir / "baseline" / "alpha" / "files").is_file()
    assert load_baseline(config_path) == trees


def test_save_writes_nested_directory_item_under_its_item_path(tmp_path: Path) -> None:
    """A nested DIRECTORY item such as .kiro/hooks uses that path under the project."""
    managed = tmp_path / "alpha"
    target = tmp_path / "lab-app"
    for root in (managed, target):
        hooks = root / ".kiro" / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "lint.sh").write_text("#!/bin/sh\n")
        (hooks / "extra").mkdir()
        (hooks / "extra" / "note.txt").write_text("n")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"alpha:\n  target: {target}\n  subpath: [.kiro/hooks]\n")
    projects = {
        "alpha": ConfigProject(
            managed_project_name="alpha",
            managed_project_path=managed,
            mappings=[Mapping(targets=[target], subpaths=[".kiro/hooks"])],
        )
    }
    trees = record_baseline(projects)

    save_baseline(config_path, trees, projects)

    item_dir = state_dir(config_path) / "baseline" / "alpha" / ".kiro" / "hooks"
    files_doc = yaml.safe_load((item_dir / "files").read_text(encoding="utf-8"))
    extra_doc = yaml.safe_load((item_dir / "extra").read_text(encoding="utf-8"))
    hub_files = files_doc["trees"][str(managed)]
    assert ".kiro/hooks" in hub_files
    assert ".kiro/hooks/lint.sh" in hub_files
    assert ".kiro/hooks/extra" not in hub_files
    assert ".kiro/hooks/extra" in extra_doc["trees"][str(managed)]
    assert ".kiro/hooks/extra/note.txt" in extra_doc["trees"][str(managed)]
    assert load_baseline(config_path) == trees


def test_save_rewrites_only_documents_covering_changed_paths(tmp_path: Path) -> None:
    """A path change rewrites that item document and leaves sibling documents intact."""
    managed = tmp_path / "alpha"
    target = tmp_path / "lab-app"
    for root in (managed, target):
        root.mkdir()
        (root / "shared.txt").write_text("hello")
        item = root / "local-file"
        (item / "requirements").mkdir(parents=True)
        (item / "tasks").mkdir()
        (item / "README.md").write_text("readme")
        (item / "requirements" / "a.txt").write_text("req")
        (item / "tasks" / "b.txt").write_text("task")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"alpha: {target}\n")
    projects = {
        "alpha": ConfigProject(
            managed_project_name="alpha",
            managed_project_path=managed,
            mappings=[Mapping(targets=[target], subpaths=None)],
        )
    }
    trees = record_baseline(projects)
    save_baseline(config_path, trees, projects)
    run_dir = state_dir(config_path)
    files_bytes = (run_dir / "baseline" / "alpha" / "files").read_bytes()
    requirements_bytes = (run_dir / "baseline" / "alpha" / "local-file" / "requirements").read_bytes()
    changed_hash = "ab" * 32
    trees[str(managed)]["local-file/tasks/b.txt"]["hash"] = changed_hash

    save_baseline(config_path, trees, projects, changed_rels=["local-file/tasks/b.txt"])

    assert (run_dir / "baseline" / "alpha" / "files").read_bytes() == files_bytes
    assert (run_dir / "baseline" / "alpha" / "local-file" / "requirements").read_bytes() == requirements_bytes
    loaded = load_baseline(config_path)
    assert loaded is not None
    assert loaded[str(managed)]["local-file/tasks/b.txt"]["hash"] == changed_hash
    assert loaded[str(managed)]["shared.txt"]["hash"] == trees[str(managed)]["shared.txt"]["hash"]


def test_daemon_start_writes_item_documents_not_baseline_yml(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Fresh catch-up persist writes baseline/<managed-project>/ files, not baseline.yml."""
    managed = tmp_path / "alpha"
    target = tmp_path / "lab-app"
    managed.mkdir()
    target.mkdir()
    (managed / "shared.txt").write_text("hello")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"alpha: {target}\n")
    start_daemon(config_path, isolated_home)
    try:
        run_dir = state_dir(config_path)
        assert not (run_dir / "baseline.yml").exists()
        document = run_dir / "baseline" / "alpha" / "files"
        assert document.is_file()
        data = yaml.safe_load(document.read_text(encoding="utf-8"))
        assert "shared.txt" in data["trees"][str(managed.resolve())]
        assert "shared.txt" in data["trees"][str(target.resolve())]
        loaded = load_baseline(config_path)
        assert loaded is not None
        assert loaded[str(managed.resolve())]["shared.txt"]["present"] is True
    finally:
        stop_daemon(config_path, isolated_home)


def test_create_rewrites_only_the_new_file_item_document(
    tmp_path: Path,
    isolated_home: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create persists the new FILE item document and leaves sibling documents on disk."""
    managed = tmp_path / "alpha"
    target = tmp_path / "lab-app"
    managed.mkdir()
    target.mkdir()
    (managed / "shared.txt").write_text("hello")
    item = managed / "local-file"
    (item / "requirements").mkdir(parents=True)
    (item / "tasks").mkdir()
    (item / "README.md").write_text("readme")
    (item / "requirements" / "a.txt").write_text("req")
    (item / "tasks" / "b.txt").write_text("task")
    (target / "item.txt").write_text("adopt me")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"alpha: {target}\n")
    start_daemon(config_path, isolated_home)
    try:
        run_dir = state_dir(config_path)
        sibling = run_dir / "baseline" / "alpha" / "local-file" / "requirements"
        assert sibling.is_file()
        os.utime(sibling, (0, 0))
        monkeypatch.chdir(target)
        created = invoke_cli(
            ["--config", str(config_path), "revlink", "create", "item.txt"],
            env=isolated_home,
        )
        assert created.exit_code == 0, created.output
        assert sibling.stat().st_mtime == 0
        files_doc = yaml.safe_load((run_dir / "baseline" / "alpha" / "files").read_text(encoding="utf-8"))
        assert "item.txt" in files_doc["trees"][str(managed.resolve())]
        assert "shared.txt" in files_doc["trees"][str(managed.resolve())]
        assert not (run_dir / "baseline.yml").exists()
    finally:
        stop_daemon(config_path, isolated_home)


def test_remove_drops_the_item_from_its_baseline_document(
    tmp_path: Path,
    isolated_home: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Remove rewrites the FILE item document without the unregistered item."""
    managed = tmp_path / "alpha"
    target = tmp_path / "lab-app"
    managed.mkdir()
    target.mkdir()
    (managed / "shared.txt").write_text("hello")
    (managed / "item.txt").write_text("adopt me")
    (target / "shared.txt").write_text("hello")
    (target / "item.txt").write_text("adopt me")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"alpha:\n  target: {target}\n  subpath: [shared.txt, item.txt]\n")
    start_daemon(config_path, isolated_home)
    try:
        run_dir = state_dir(config_path)
        files_path = run_dir / "baseline" / "alpha" / "files"
        before = yaml.safe_load(files_path.read_text(encoding="utf-8"))
        assert "item.txt" in before["trees"][str(managed.resolve())]
        monkeypatch.chdir(target)
        removed = invoke_cli(
            ["--config", str(config_path), "remove", "item.txt"],
            env=isolated_home,
        )
        assert removed.exit_code == 0, removed.output
        after = yaml.safe_load(files_path.read_text(encoding="utf-8"))
        assert "item.txt" not in after["trees"][str(managed.resolve())]
        assert "shared.txt" in after["trees"][str(managed.resolve())]
    finally:
        stop_daemon(config_path, isolated_home)
