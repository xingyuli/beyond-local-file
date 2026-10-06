"""Configuration set identity, set run directory, and mapping-file I/O."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from beyond_local_file.blfrc import BlfrcError, resolve_global_mapping_files, runtime_home
from beyond_local_file.config import Config, ConfigError
from beyond_local_file.model.config import ConfigProject

__all__ = ["ConfigError", "ConfigurationSet"]


class ConfigurationSet:
    """The mapping yaml files one daemon process loads, identified by one path."""

    identity: Path

    def __init__(self, identity: Path) -> None:
        """Store the resolved identity path.

        Args:
            identity: Global config path or a mapping yaml path.
        """
        self.identity = identity.resolve()

    @property
    def is_global(self) -> bool:
        """Return whether this is the global configuration set.

        Returns:
            True when identity is the global config under runtime home.
        """
        return self.identity == runtime_home() / "config"

    @property
    def run_directory(self) -> Path:
        """Return the set run directory for this configuration set.

        Returns:
            ``<runtime home>/run/global`` or ``.../run/file-<sha256>``.
        """
        if self.is_global:
            return runtime_home() / "run" / "global"
        digest = hashlib.sha256(str(self.identity).encode("utf-8")).hexdigest()
        return runtime_home() / "run" / f"file-{digest}"

    def mapping_files(self) -> tuple[Path, ...]:
        """Return mapping yaml paths for this set, recomputed from disk.

        Returns:
            Mapping yaml paths. Empty when the global pointer list is missing
            or has no ``config_file`` field.

        Raises:
            ConfigError: If the global pointer list exists but is invalid.
        """
        if not self.is_global:
            return (self.identity,)
        try:
            paths = resolve_global_mapping_files()
        except BlfrcError as error:
            raise ConfigError(str(error)) from error
        if not paths:
            return ()
        return tuple(paths)

    def projects(self, project_name: str | None = None) -> dict[str, ConfigProject]:
        """Load mapping projects from this set's mapping files.

        Args:
            project_name: Optional project name to filter.

        Returns:
            Config projects from the mapping yaml.

        Raises:
            ConfigError: If there are no mapping files or a mapping file cannot be loaded.
        """
        projects, _sources = self._projects_and_sources(project_name)
        return projects

    def project_sources(self, project_name: str | None = None) -> dict[Path, Path]:
        """Return the mapping yaml that defined each managed project.

        Args:
            project_name: Optional project name to filter.

        Returns:
            Managed-project path to the mapping yaml that defined it.

        Raises:
            ConfigError: If there are no mapping files or a mapping file cannot be loaded.
        """
        _projects, sources = self._projects_and_sources(project_name)
        return sources

    def _projects_and_sources(self, project_name: str | None) -> tuple[dict[str, ConfigProject], dict[Path, Path]]:
        paths = self.mapping_files()
        if not paths:
            raise ConfigError(f"No mapping files for {self.identity}")
        try:
            if len(paths) == 1:
                cfg = Config(paths[0])
                cfg.load()
                projects = cfg.get_config_projects(project_name)
                sources = {project.managed_project_path: paths[0] for project in projects.values()}
                return projects, sources
            return _combine_mapping_projects(paths, project_name)
        except (FileNotFoundError, ValueError, yaml.YAMLError, BlfrcError) as error:
            raise ConfigError(str(error)) from error


def _combine_mapping_projects(
    config_paths: tuple[Path, ...] | list[Path],
    project_name: str | None = None,
) -> tuple[dict[str, ConfigProject], dict[Path, Path]]:
    """Load and combine mapping files, erroring on duplicate managed paths.

    Args:
        config_paths: Mapping yaml paths to load.
        project_name: Optional project name to filter.

    Returns:
        Combined projects and a map of managed-project path to source yaml.

    Raises:
        ConfigError: If the same managed project is defined in more than one file.
    """
    combined_projects: dict[str, ConfigProject] = {}
    sources: dict[Path, Path] = {}

    for path in config_paths:
        cfg = Config(path)
        cfg.load()
        for proj in cfg.get_config_projects().values():
            managed_path = proj.managed_project_path
            if managed_path in sources:
                existing = sources[managed_path]
                raise ConfigError(
                    f"Managed project '{managed_path}' defined in multiple config files: {existing}, {path}"
                )
            sources[managed_path] = path
            combined_projects[str(managed_path)] = proj

    if project_name:
        combined_projects = {
            key: project for key, project in combined_projects.items() if project.managed_project_name == project_name
        }
        sources = {
            managed: source
            for managed, source in sources.items()
            if any(project.managed_project_path == managed for project in combined_projects.values())
        }

    return combined_projects, sources
