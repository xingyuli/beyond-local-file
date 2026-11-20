"""What ``blf managed`` reports for a directory, from committed mappings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema

from beyond_local_file.managed import MANAGED_SCHEMA, managed_answer
from beyond_local_file.model.config import ConfigProject, Mapping


def _project(name: str, hub: Path, targets: list[Path], subpaths: list[str] | None) -> ConfigProject:
    hub.mkdir(parents=True, exist_ok=True)
    return ConfigProject(
        managed_project_name=name,
        managed_project_path=hub,
        mappings=[Mapping(targets=targets, subpaths=subpaths)],
    )


def test_target_root_reports_project_and_items(tmp_path: Path) -> None:
    """A target root lists each contributing managed project with its items."""
    target = tmp_path / "repo"
    target.mkdir()
    hub = tmp_path / "team-kit"
    projects = {"team-kit": _project("team-kit", hub, [target], [".kiro/steering"])}

    answer = managed_answer(projects, target)

    assert answer["schema_version"] == 1
    assert answer["path"] == str(target)
    assert answer["target"] == str(target)
    assert answer["is_target_root"] is True
    assert answer["managed"] is True
    assert [project["name"] for project in answer["managed_projects"]] == ["team-kit"]
    project = answer["managed_projects"][0]
    assert project["path"] == str(hub)
    assert project["items"] == [{"path": ".kiro/steering", "hub_path": str(hub / ".kiro/steering")}]


def test_subdirectory_reports_enclosing_target(tmp_path: Path) -> None:
    """A subdirectory of a target answers with the target and says it is not the root."""
    target = tmp_path / "repo"
    (target / "src").mkdir(parents=True)
    projects = {"team-kit": _project("team-kit", tmp_path / "team-kit", [target], [".kiro/steering"])}

    answer = managed_answer(projects, target / "src")

    assert answer["path"] == str(target / "src")
    assert answer["target"] == str(target)
    assert answer["is_target_root"] is False
    assert answer["managed"] is True


def test_path_in_no_target_is_not_managed(tmp_path: Path) -> None:
    """A directory with no target at or above it is a normal, empty answer."""
    target = tmp_path / "repo"
    target.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    projects = {"team-kit": _project("team-kit", tmp_path / "team-kit", [target], None)}

    answer = managed_answer(projects, elsewhere)

    assert answer["path"] == str(elsewhere)
    assert answer["target"] is None
    assert answer["is_target_root"] is False
    assert answer["managed"] is False
    assert answer["managed_projects"] == []


def test_parent_of_a_target_is_not_a_target(tmp_path: Path) -> None:
    """A directory that only contains a target is not managed."""
    target = tmp_path / "work" / "repo"
    target.mkdir(parents=True)
    projects = {"team-kit": _project("team-kit", tmp_path / "team-kit", [target], None)}

    answer = managed_answer(projects, tmp_path / "work")

    assert answer["managed"] is False
    assert answer["target"] is None


def test_two_projects_are_sorted_and_items_follow_discovery(tmp_path: Path) -> None:
    """Projects sort by name; sync-all lists present hub entries; a declared missing item is listed."""
    target = tmp_path / "repo"
    target.mkdir()
    hub_b = tmp_path / "b-kit"
    (hub_b / "docs").mkdir(parents=True)
    (hub_b / "notes.md").write_text("n")
    projects = {
        "b-kit": _project("b-kit", hub_b, [target], None),
        "a-kit": _project("a-kit", tmp_path / "a-kit", [target], ["not-on-hub.md"]),
    }

    answer = managed_answer(projects, target)

    assert [project["name"] for project in answer["managed_projects"]] == ["a-kit", "b-kit"]
    by_name = {project["name"]: project for project in answer["managed_projects"]}
    assert [item["path"] for item in by_name["a-kit"]["items"]] == ["not-on-hub.md"]
    assert [item["path"] for item in by_name["b-kit"]["items"]] == ["docs", "notes.md"]


def test_nearest_target_wins_when_targets_nest(tmp_path: Path) -> None:
    """With a target inside another target, the nearest ancestor answers."""
    outer = tmp_path / "outer"
    inner = outer / "inner"
    (inner / "src").mkdir(parents=True)
    projects = {
        "outer-kit": _project("outer-kit", tmp_path / "outer-kit", [outer], None),
        "inner-kit": _project("inner-kit", tmp_path / "inner-kit", [inner], None),
    }

    answer = managed_answer(projects, inner / "src")

    assert answer["target"] == str(inner)
    assert [project["name"] for project in answer["managed_projects"]] == ["inner-kit"]


def test_managed_project_git_state(tmp_path: Path) -> None:
    """git reports whether the managed project sits in a repo and where its root is."""
    target = tmp_path / "repo"
    target.mkdir()
    repo_hub = tmp_path / "in-repo"
    (repo_hub / ".git").mkdir(parents=True)
    nested_hub = tmp_path / "big" / "local-file"
    nested_hub.mkdir(parents=True)
    (tmp_path / "big" / ".git").write_text("gitdir: elsewhere\n")  # worktree or submodule marker file
    plain_hub = tmp_path / "plain"
    projects = {
        name: _project(name, hub, [target], None)
        for name, hub in {"in-repo": repo_hub, "nested": nested_hub, "plain": plain_hub}.items()
    }

    answer = managed_answer(projects, target)

    git = {project["name"]: project["git"] for project in answer["managed_projects"]}
    assert git["in-repo"] == {"is_repo": True, "root": str(repo_hub)}
    assert git["nested"] == {"is_repo": True, "root": str(tmp_path / "big")}
    assert git["plain"] == {"is_repo": False, "root": None}


def _property_schemas(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Every property schema reachable from *schema*, nested objects and array items included."""
    found: list[dict[str, Any]] = []
    for sub in schema.get("properties", {}).values():
        found.append(sub)
        found.extend(_property_schemas(sub))
        if "items" in sub:
            found.append(sub["items"])
            found.extend(_property_schemas(sub["items"]))
    return found


def test_schema_is_valid_and_accepts_real_answers(tmp_path: Path) -> None:
    """Answers for a managed and an unmanaged directory both validate against the schema."""
    target = tmp_path / "repo"
    target.mkdir()
    projects = {"team-kit": _project("team-kit", tmp_path / "team-kit", [target], ["a.md"])}
    jsonschema.Draft202012Validator.check_schema(MANAGED_SCHEMA)
    validator = jsonschema.Draft202012Validator(MANAGED_SCHEMA)

    validator.validate(managed_answer(projects, target))
    validator.validate(managed_answer(projects, tmp_path))


def test_schema_explains_itself() -> None:
    """The command states its purpose, every field has a description, and an example is given."""
    assert MANAGED_SCHEMA["description"]
    assert MANAGED_SCHEMA["examples"]
    undocumented = [sub for sub in _property_schemas(MANAGED_SCHEMA) if not sub.get("description")]
    assert undocumented == []
    jsonschema.Draft202012Validator(MANAGED_SCHEMA).validate(MANAGED_SCHEMA["examples"][0])
