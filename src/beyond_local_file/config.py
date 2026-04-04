"""Configuration management for the link CLI tool."""

from pathlib import Path
from typing import Any

import yaml

from .model.config import ConfigProject, Mapping


class Config:
    """Manages configuration loaded from a YAML file.

    The configuration file maps project names to their target paths.
    Each project can have one or more mappings, where each mapping can be:

    - **Simple string mapping**: Syncs everything from project to target::

        project-a: /path/to/target

    - **Dict mapping**: Supports selective subpath sync and copy strategy::

        project-b:
          target: /path/to/target
          subpath:
            - .kiro/hooks
            - path: .qoder/rules.md
              copy: true

    Mappings can be combined in a list for multiple targets::

        project-c:
          - /path/to/target1
          - target: /path/to/target2
            subpath:
              - .kiro/hooks

    Attributes:
        config_path: Path to the configuration file.
    """

    def __init__(self, config_path: Path):
        """Initialize the Config with a config file path.

        Args:
            config_path: Path to the YAML configuration file.
        """
        self.config_path = Path(config_path).resolve()
        self._data: dict[str, Any] | None = None

    def load(self) -> dict[str, Any]:
        """Load the configuration from the YAML file.

        Returns:
            The loaded configuration dictionary.

        Raises:
            FileNotFoundError: If the config file does not exist.
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path) as f:
            self._data = yaml.safe_load(f)

        return self._data

    def get_config_projects(self, project_name: str | None = None) -> dict[str, ConfigProject]:
        """Get project configurations using new model structure.

        Parses YAML according to the formal grammar, preserving the mapping structure.
        Each project has a list of mappings, where each mapping defines targets and
        optional sync rules (subpaths, copy strategy).

        Grammar structure:
        - project-name: string-mapping | dict-mapping | list-of-mappings
        - string-mapping: target-path (string)
        - dict-mapping: {target: target-path(s), subpath?: [...], ...}
        - list-of-mappings: [string-mapping | dict-mapping, ...]

        Args:
            project_name: Optional project name to filter. If provided, only
                        returns configuration for that project.

        Returns:
            Dictionary mapping project names to ConfigProject objects.
            Each ConfigProject contains the project path and list of mappings.

        Raises:
            ValueError: If the specified project_name is not in the config.
        """
        if self._data is None:
            self.load()

        if project_name:
            if project_name not in self._data:
                raise ValueError(f"Project '{project_name}' not found in config")
            config_project = self._build_config_project(project_name, self._data[project_name])
            return {project_name: config_project}

        result = {}
        for name, value in self._data.items():
            result[name] = self._build_config_project(name, value)
        return result

    def _resolve_project_path(self, project_name: str) -> Path:
        """Resolve project path relative to config file directory.

        Args:
            project_name: The project name/path from the config file.

        Returns:
            Resolved absolute Path to the project directory.
        """
        project_path = Path(project_name)
        if project_path.is_absolute():
            return project_path.resolve()
        # Resolve relative to config file's directory
        config_dir = self.config_path.parent
        return (config_dir / project_path).resolve()

    def _normalize_targets(self, targets: str | list[str]) -> list[Path]:
        """Normalize target paths to resolved Path objects.

        Args:
            targets: A single target path string or list of target paths.

        Returns:
            List of resolved Path objects.
        """
        if isinstance(targets, str):
            targets = [targets]
        return [Path(t).resolve() for t in targets]

    def _parse_subpaths(self, raw: str | list | None) -> tuple[list[str] | None, set[str] | None]:
        """Parse subpath entries, extracting copy flags.

        Each entry can be a plain string or a dict with ``path`` and
        optional ``copy: true``.

        Args:
            raw: Raw subpath value from YAML — string, list, or None.

        Returns:
            Tuple of (subpath list, set of paths marked for copy).
            Either element may be None when there are no entries.
        """
        if raw is None:
            return None, None

        if isinstance(raw, str):
            return [raw], None

        subpaths: list[str] = []
        copy_paths: set[str] = set()

        for entry in raw:
            if isinstance(entry, str):
                subpaths.append(entry)
            elif isinstance(entry, dict) and "path" in entry:
                path = entry["path"]
                subpaths.append(path)
                if entry.get("copy", False):
                    copy_paths.add(path)

        return subpaths or None, copy_paths or None

    def _build_config_project(self, name: str, value: str | list | dict) -> ConfigProject:
        """Build a ConfigProject from raw YAML value according to grammar.

        Grammar productions:
        - string-mapping: target-path (string)
        - dict-mapping: {target: target-path(s), subpath?: [...], ...}
        - list-of-mappings: [string-mapping | dict-mapping, ...]

        Args:
            name: The project name.
            value: The raw YAML value (string, list, or dict).

        Returns:
            ConfigProject with list of mappings preserving the YAML structure.
        """
        project_path = self._resolve_project_path(name)

        # Single string mapping: project-name: /target
        if isinstance(value, str):
            mapping = self._parse_string_mapping(value)
            return ConfigProject(
                managed_project_name=name,
                managed_project_path=project_path,
                mappings=[mapping],
            )

        # Single dict mapping: project-name: {target: /target, subpath: [...]}
        if isinstance(value, dict) and "target" in value:
            mapping = self._parse_dict_mapping(value)
            return ConfigProject(
                managed_project_name=name,
                managed_project_path=project_path,
                mappings=[mapping],
            )

        # List of mappings: project-name: [mapping1, mapping2, ...]
        if isinstance(value, list):
            mappings = []
            for item in value:
                if isinstance(item, str):
                    mappings.append(self._parse_string_mapping(item))
                elif isinstance(item, dict) and "target" in item:
                    mappings.append(self._parse_dict_mapping(item))
            return ConfigProject(
                managed_project_name=name,
                managed_project_path=project_path,
                mappings=mappings,
            )

        # Fallback: treat as string mapping
        mapping = self._parse_string_mapping(str(value))
        return ConfigProject(
            managed_project_name=name,
            managed_project_path=project_path,
            mappings=[mapping],
        )

    def _parse_string_mapping(self, target: str) -> Mapping:
        """Parse a string mapping: /target or [/target1, /target2].

        Args:
            target: Target path string.

        Returns:
            Mapping with single target, no subpaths.
        """
        targets = self._normalize_targets(target)
        return Mapping(targets=targets, subpaths=None, copy_paths=None)

    def _parse_dict_mapping(self, mapping_dict: dict) -> Mapping:
        """Parse a dict mapping with target and optional subpath/copy.

        Args:
            mapping_dict: Dictionary with 'target' key and optional 'subpath'.

        Returns:
            Mapping with targets, subpaths, and copy_paths.
        """
        targets = self._normalize_targets(mapping_dict["target"])
        raw_subpaths = mapping_dict.get("subpath")
        subpaths, copy_paths = self._parse_subpaths(raw_subpaths)

        return Mapping(
            targets=targets,
            subpaths=subpaths,
            copy_paths=copy_paths,
        )
