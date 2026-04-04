"""Configuration models that reflect YAML grammar structure.

These models represent user intent as expressed in the configuration file.
They directly map to the formal grammar defined in the configuration reference.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Mapping:
    """Represents a single mapping (string-mapping or dict-mapping).

    A mapping defines one or more targets and optional rules for syncing.
    Each mapping can have its own subpaths and copy strategy settings.

    Attributes:
        targets: List of target paths (can have multiple from target: [t1, t2]).
        subpaths: Optional list of relative subpaths for selective sync.
        copy_paths: Optional set of subpath names that use copy strategy.

    Examples:
        String mapping:
            - /target1
            → Mapping(targets=[Path("/target1")], subpaths=None, copy_paths=None)

        Dict mapping with subpaths:
            - target: /target2
              subpath: [.kiro/hooks]
            → Mapping(targets=[Path("/target2")], subpaths=[".kiro/hooks"], copy_paths=None)

        Dict mapping with multiple targets:
            - target: [/target2, /target3]
              subpath: [.kiro/hooks]
            → Mapping(targets=[Path("/target2"), Path("/target3")],
                      subpaths=[".kiro/hooks"], copy_paths=None)
    """

    targets: list[Path]
    subpaths: list[str] | None = None
    copy_paths: set[str] | None = None


@dataclass
class ConfigProject:
    """Represents a project configuration with its mappings.

    A project has a name, path, and a list of mappings that define
    where and how it should be synced.

    Attributes:
        managed_project_name: The project name as defined in configuration.
        managed_project_path: Absolute path to the managed project directory.
        mappings: List of mappings, each defining targets and sync rules.

    Example:
        my-project:
          - /target1
          - target: [/target2, /target3]
            subpath: [.kiro/hooks]

        → ConfigProject(
              managed_project_name="my-project",
              managed_project_path=Path("/path/to/my-project"),
              mappings=[
                  Mapping(targets=[Path("/target1")], subpaths=None, copy_paths=None),
                  Mapping(targets=[Path("/target2"), Path("/target3")],
                          subpaths=[".kiro/hooks"], copy_paths=None),
              ]
          )
    """

    managed_project_name: str
    managed_project_path: Path
    mappings: list[Mapping]


@dataclass
class Config:
    """Top-level configuration containing all projects.

    Attributes:
        projects: Dictionary mapping project names to their configurations.
    """

    projects: dict[str, ConfigProject]
