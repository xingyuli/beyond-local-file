"""Configuration management for the symlink CLI tool."""

from pathlib import Path
from typing import Any

import yaml

from .models import ProjectConfiguration


class Config:
    """Manages configuration loaded from a YAML file.

    The configuration file maps project names to their target paths.
    Each project can have a single target path or a list of target paths.

    Example config format:
        project-a:
          - /path/to/target1
          - /path/to/target2
        project-b: /path/to/target

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
            targets = self._data[project_name]
            return {
                project_name: ProjectConfiguration(
                    name=project_name,
                    project_path=self._resolve_project_path(project_name),
                    targets=self._normalize_targets(targets),
                )
            }

        return {
            name: ProjectConfiguration(
                name=name,
                project_path=self._resolve_project_path(name),
                targets=self._normalize_targets(targets),
            )
            for name, targets in self._data.items()
        }

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
