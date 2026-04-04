"""Configuration management for the link CLI tool."""

from pathlib import Path
from typing import Any

import yaml

from .models import ProjectConfiguration


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

    def get_projects(self, project_name: str | None = None) -> dict[str, ProjectConfiguration]:
        """Get project configurations with normalized paths.

        The configuration supports two mapping types:

        1. Simple string mapping: ``project-a: /path/to/target``
        2. Dict mapping with optional subpath:

           .. code-block:: yaml

              project-a:
                target: /path/to/target
                subpath:
                  - .kiro/hooks

        Mappings can be combined in a list:

           .. code-block:: yaml

              project-a:
                - /path/to/target1
                - target: /path/to/target2
                  subpath:
                    - .kiro/hooks

        Args:
            project_name: Optional project name to filter. If provided, only
                        returns configuration for that project.

        Returns:
            Dictionary mapping project names to ProjectConfiguration objects
            containing the project path and target paths. When a list contains
            mixed mapping types, multiple ProjectConfiguration objects are created
            with synthetic names using 1-based sequence numbers (e.g., "project-a#1", "project-a#2", "project-a#3").

        Raises:
            ValueError: If the specified project_name is not in the config.
        """
        if self._data is None:
            self.load()

        if project_name:
            if project_name not in self._data:
                raise ValueError(f"Project '{project_name}' not found in config")
            return self._build_project_configs(project_name, self._data[project_name])

        result = {}
        for name, value in self._data.items():
            result.update(self._build_project_configs(name, value))
        return result

    def _is_full_format(self, value: str | list[str] | dict) -> bool:
        """Check whether a config value uses the full dict format.

        The full format is a dict containing a ``target`` key.

        Args:
            value: The raw config value for a project.

        Returns:
            True if the value is a dict with a ``target`` key.
        """
        return isinstance(value, dict) and "target" in value

    def _is_mixed_format(self, value: str | list | dict) -> bool:
        """Check whether a config value uses mixed format (list with strings and dicts).

        Args:
            value: The raw config value for a project.

        Returns:
            True if the value is a list containing both strings and dicts.
        """
        if not isinstance(value, list):
            return False
        has_string = any(isinstance(item, str) for item in value)
        has_dict = any(isinstance(item, dict) and "target" in item for item in value)
        return has_string and has_dict

    def _build_project_configs(self, name: str, value: str | list | dict) -> dict[str, ProjectConfiguration]:
        """Build ProjectConfiguration(s) from a raw config value.

        When a project maps to multiple targets, creates separate ProjectConfiguration
        objects with 1-based sequence suffixes (e.g., "project#1", "project#2").

        Args:
            name: The project name.
            value: The raw YAML value (string, list, or dict).

        Returns:
            Dictionary mapping (possibly synthetic) names to ProjectConfiguration objects.
        """
        # Handle mixed format: list with both strings and dicts
        if self._is_mixed_format(value):
            return self._build_mixed_configs(name, value)

        # Build single configuration
        config = self._build_project_config(name, value)

        # If multiple targets, split into separate configs with sequence suffixes
        if len(config.targets) > 1:
            return self._split_by_targets(name, config)

        # Single target - return as-is without suffix
        return {name: config}

    def _split_by_targets(self, name: str, config: ProjectConfiguration) -> dict[str, ProjectConfiguration]:
        """Split a configuration with multiple targets into separate configs.

        Args:
            name: The base project name.
            config: ProjectConfiguration with multiple targets.

        Returns:
            Dictionary mapping synthetic names to ProjectConfiguration objects,
            one per target with 1-based sequence suffixes.
        """
        configs = {}
        for seq, target in enumerate(config.targets, start=1):
            synthetic_name = f"{name}#{seq}"
            configs[synthetic_name] = ProjectConfiguration(
                name=synthetic_name,
                project_path=config.project_path,
                targets=[target],
                subpaths=config.subpaths,
                copy_paths=config.copy_paths,
            )
        return configs

    def _build_project_config(self, name: str, value: str | list[str] | dict) -> ProjectConfiguration:
        """Build a ProjectConfiguration from a raw config value.

        Args:
            name: The project name.
            value: The raw YAML value (string, list, or dict).

        Returns:
            A fully resolved ProjectConfiguration.
        """
        if self._is_full_format(value):
            targets = self._normalize_targets(value["target"])
            raw_subpaths = value.get("subpath")
            subpaths, copy_paths = self._parse_subpaths(raw_subpaths)
            return ProjectConfiguration(
                name=name,
                project_path=self._resolve_project_path(name),
                targets=targets,
                subpaths=subpaths,
                copy_paths=copy_paths or None,
            )

        return ProjectConfiguration(
            name=name,
            project_path=self._resolve_project_path(name),
            targets=self._normalize_targets(value),
        )

    def _build_mixed_configs(self, name: str, value: list) -> dict[str, ProjectConfiguration]:
        """Build multiple ProjectConfiguration objects from a mixed format list.

        Splits a list containing both strings and dicts into separate configurations.
        Uses 1-based sequence numbering (#{seq}) for all configurations when multiple exist.

        Args:
            name: The project name.
            value: List containing strings and/or dicts with target+subpath.

        Returns:
            Dictionary mapping synthetic names to ProjectConfiguration objects.
        """
        configs = {}
        simple_targets = []
        seq = 1  # 1-based sequence number

        for item in value:
            if isinstance(item, str):
                # Collect simple string targets
                simple_targets.append(item)
            elif isinstance(item, dict) and "target" in item:
                # Create a separate config for this dict entry with 1-based sequence
                synthetic_name = f"{name}#{seq}"
                seq += 1
                configs[synthetic_name] = self._build_project_config(synthetic_name, item)

        # If there are simple targets, create a config for them
        if simple_targets:
            synthetic_name = f"{name}#{seq}"
            configs[synthetic_name] = ProjectConfiguration(
                name=synthetic_name,
                project_path=self._resolve_project_path(name),
                targets=self._normalize_targets(simple_targets),
            )

        return configs

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
