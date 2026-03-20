"""Configuration management for the symlink CLI tool."""

from pathlib import Path
from typing import Any

import yaml

from .models import ProjectConfiguration


class Config:
    """Manages configuration loaded from a YAML file.

    The configuration file maps project names to their target paths.
    Three formats are supported:

    1. Simplified (string)::

        project-b: /path/to/target

    2. Simplified (list)::

        project-a:
          - /path/to/target1
          - /path/to/target2

    3. Full (dict with ``target`` + optional ``subpath``)::

        project-c:
          target: /path/to/target
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

        Supports three config formats:

        1. Simplified (string): ``project-a: /path/to/target``
        2. Simplified (list): ``project-a: [/path/to/target1, /path/to/target2]``
        3. Full (dict with ``target`` + optional ``subpath``):

           .. code-block:: yaml

              project-a:
                target: /path/to/target
                subpath:
                  - .kiro/hooks

        Args:
            project_name: Optional project name to filter. If provided, only
                        returns configuration for that project.

        Returns:
            Dictionary mapping project names to ProjectConfiguration objects
            containing the project path and target paths.

        Raises:
            ValueError: If the specified project_name is not in the config.
        """
        if self._data is None:
            self.load()

        if project_name:
            if project_name not in self._data:
                raise ValueError(f"Project '{project_name}' not found in config")
            return {project_name: self._build_project_config(project_name, self._data[project_name])}

        return {name: self._build_project_config(name, value) for name, value in self._data.items()}

    def _is_full_format(self, value: str | list[str] | dict) -> bool:
        """Check whether a config value uses the full dict format.

        The full format is a dict containing a ``target`` key.

        Args:
            value: The raw config value for a project.

        Returns:
            True if the value is a dict with a ``target`` key.
        """
        return isinstance(value, dict) and "target" in value

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
            subpaths = value.get("subpath")
            if isinstance(subpaths, str):
                subpaths = [subpaths]
            return ProjectConfiguration(
                name=name,
                project_path=self._resolve_project_path(name),
                targets=targets,
                subpaths=subpaths,
            )

        return ProjectConfiguration(
            name=name,
            project_path=self._resolve_project_path(name),
            targets=self._normalize_targets(value),
        )

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
