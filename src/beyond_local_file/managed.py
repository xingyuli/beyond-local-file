"""What blf projects into a directory, answered from committed mappings.

The dataclasses below are the single definition of the ``blf managed`` output.
:data:`MANAGED_SCHEMA` is generated from them, so the schema cannot drift from
what the command prints. Each field's ``description`` metadata and each class
docstring become the schema's descriptions.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from types import UnionType
from typing import Any, Literal, get_args, get_origin, get_type_hints

from beyond_local_file.contribution import mapping_item_names, projects_targeting
from beyond_local_file.model.config import ConfigProject

_JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


@dataclass(frozen=True, kw_only=True)
class GitState:
    """Whether the managed project directory sits inside a git repository.

    When it does not, there is nothing to commit for this managed project.
    """

    is_repo: bool = field(metadata={"description": "True when the managed project directory is inside a git repo."})
    root: str | None = field(
        metadata={
            "description": "Absolute path of the nearest ancestor holding .git, where a commit for this "
            "managed project runs. It can be above the managed project path. Null when is_repo is false."
        }
    )


@dataclass(frozen=True, kw_only=True)
class ManagedItem:
    """One file or directory the managed project projects into the target."""

    path: str = field(
        metadata={
            "description": "Item path relative to the target root. A directory item covers every file inside it. "
            "A path in the target belongs to the managed project when it equals this path or sits under it."
        }
    )
    hub_path: str = field(
        metadata={
            "description": "Absolute path of the item in the managed project. For a file inside a directory item, "
            "append the rest of its path."
        }
    )


@dataclass(frozen=True, kw_only=True)
class ManagedProject:
    """One managed project that projects items into the target."""

    name: str = field(metadata={"description": "Managed project name from the mapping file."})
    path: str = field(metadata={"description": "Absolute path of the managed project directory (the hub)."})
    git: GitState = field(metadata={"description": "Git state of the managed project directory."})
    items: list[ManagedItem] = field(
        metadata={
            "description": "Items this managed project projects into the target, from item discovery. "
            "A declared item that is still missing in the managed project is listed."
        }
    )


@dataclass(frozen=True, kw_only=True)
class ManagedAnswer:
    """Output of `blf managed [PATH]`.

    Reports whether PATH is inside a target project that blf projects files into, which managed
    projects contribute, and which items they project. Call it to learn whether a directory has
    blf-managed files and where their hub copies live. It answers from the running daemon's
    committed mappings and needs the daemon running. Exit 0 means the daemon answered, including
    managed false. Exit 1 means it could not answer. Exit 2 is a usage error.
    """

    schema_version: Literal[1] = field(
        metadata={"description": "Version of this output format. It changes only on a breaking change."}, default=1
    )
    path: str = field(metadata={"description": "The directory asked about, as an absolute normalized path."})
    target: str | None = field(
        metadata={
            "description": "Absolute path of the target project: the nearest ancestor-or-self of path "
            "that blf projects files into. Null when there is none."
        }
    )
    is_target_root: bool = field(
        metadata={
            "description": "True when path is the target itself. False when the answer came from a parent directory, "
            "so a caller can confirm the directory is the intended one."
        }
    )
    managed: bool = field(
        metadata={
            "description": "True when a target project was found. It answers at the project level only. "
            "To learn whether one file is projected, check managed_projects[].items."
        }
    )
    managed_projects: list[ManagedProject] = field(
        metadata={
            "description": "Managed projects that project into the target, sorted by name. Empty when not managed."
        }
    )


def _schema_of_type(annotation: object) -> dict[str, Any]:
    """Return the JSON Schema for one dataclass field annotation."""
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is str:
        return {"type": "string"}
    if isinstance(annotation, type) and is_dataclass(annotation):
        return _object_schema(annotation)
    origin = get_origin(annotation)
    if origin is Literal:
        (value,) = get_args(annotation)
        return {"const": value}
    if origin is list:
        (inner,) = get_args(annotation)
        return {"type": "array", "items": _schema_of_type(inner)}
    if origin is UnionType and set(get_args(annotation)) == {str, type(None)}:
        return {"type": ["string", "null"]}
    raise TypeError(f"No JSON Schema mapping for {annotation!r}")


def _object_schema(cls: type) -> dict[str, Any]:
    """Return the JSON Schema for dataclass *cls*, every field required and documented."""
    hints = get_type_hints(cls)
    properties = {
        item.name: {**_schema_of_type(hints[item.name]), "description": item.metadata["description"]}
        for item in fields(cls)
    }
    return {
        "type": "object",
        "description": " ".join((inspect.getdoc(cls) or "").split()),
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


_EXAMPLE = ManagedAnswer(
    path="/Users/me/repo/src",
    target="/Users/me/repo",
    is_target_root=False,
    managed=True,
    managed_projects=[
        ManagedProject(
            name="team-kit",
            path="/Users/me/team-kit",
            git=GitState(is_repo=True, root="/Users/me/team-kit"),
            items=[ManagedItem(path=".kiro/steering", hub_path="/Users/me/team-kit/.kiro/steering")],
        )
    ],
)

MANAGED_SCHEMA: dict[str, Any] = {
    "$schema": _JSON_SCHEMA_DIALECT,
    "title": "blf managed",
    **_object_schema(ManagedAnswer),
    "examples": [asdict(_EXAMPLE)],
}


def managed_answer(projects: dict[str, ConfigProject], path: Path) -> dict[str, Any]:
    """Return the ``blf managed`` document for *path*.

    Args:
        projects: Committed mappings.
        path: Normalized absolute directory to look at.

    Returns:
        The JSON-serialisable answer described by :data:`MANAGED_SCHEMA`.
    """
    target = _nearest_ancestor_or_self(path, lambda candidate: bool(projects_targeting(projects, candidate)))
    contributors = projects_targeting(projects, target) if target is not None else []
    answer = ManagedAnswer(
        path=str(path),
        target=str(target) if target is not None else None,
        is_target_root=target == path,
        managed=target is not None,
        managed_projects=[_project_entry(project, target) for project in contributors if target is not None],
    )
    return asdict(answer)


def _project_entry(project: ConfigProject, target: Path) -> ManagedProject:
    hub = project.managed_project_path
    return ManagedProject(
        name=project.managed_project_name,
        path=str(hub),
        git=_git_state(hub),
        items=[ManagedItem(path=name, hub_path=str(hub / name)) for name in mapping_item_names(project, target)],
    )


def _git_state(directory: Path) -> GitState:
    """Report the git repo holding *directory*, found by walking up for ``.git``.

    ``.git`` may be a directory or a file (worktree, submodule). Git is not run.
    """
    root = _nearest_ancestor_or_self(directory, lambda candidate: (candidate / ".git").exists())
    return GitState(is_repo=root is not None, root=str(root) if root is not None else None)


def _nearest_ancestor_or_self(path: Path, matches: Callable[[Path], bool]) -> Path | None:
    """Return *path* or its nearest parent for which *matches* is true, else ``None``."""
    return next((candidate for candidate in (path, *path.parents) if matches(candidate)), None)
