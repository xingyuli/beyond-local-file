"""Configuration set identity, set run directory, and mapping-file I/O."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import click
import yaml

from beyond_local_file.blfrc import (
    BlfrcError,
    global_config_path,
    resolve_global_mapping_files,
    runtime_home,
)
from beyond_local_file.config import Config, ConfigError
from beyond_local_file.constants import DEFAULT_CONFIG_FILE
from beyond_local_file.daemon.pid import pid_is_alive, read_pid_file
from beyond_local_file.model.config import ConfigProject

__all__ = [
    "ConfigError",
    "ConfigurationSet",
    "RunningOverlap",
    "configuration_set_for_shell",
    "configuration_set_for_start",
]

_PID_NAME = "daemon.pid"
_MAPPING_FILES_NAME = "mapping-files"
_GLOBAL_RUN_NAME = "global"


@dataclass(frozen=True)
class RunningOverlap:
    """A running set that already loaded one of this set's mapping files.

    Attributes:
        identity: Running set's identity path.
        pid: Live daemon pid in that set's run directory.
        mapping_file: Mapping yaml both sets would load.
    """

    identity: Path
    pid: int
    mapping_file: Path


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

    def running_overlap(self) -> RunningOverlap | None:
        """Return a running set that already loaded one of this set's mapping files.

        May return this set when its identity is already running.

        Returns:
            The first live overlap, or None when no live pid loaded these files.
        """
        wanted = {path.resolve() for path in self.mapping_files()}
        if not wanted:
            return None
        run_root = runtime_home() / "run"
        if not run_root.is_dir():
            return None
        for entry in sorted(run_root.iterdir(), key=lambda path: path.name):
            if not entry.is_dir():
                continue
            pid = read_pid_file(entry / _PID_NAME)
            if pid is None or not pid_is_alive(pid):
                continue
            loaded = _loaded_mapping_files(entry)
            if not loaded and entry.name != _GLOBAL_RUN_NAME:
                loaded = [path for path in wanted if ConfigurationSet(path).run_directory.name == entry.name]
            for loaded_path in loaded:
                if loaded_path.resolve() in wanted:
                    identity = _identity_path_for_run_dir(entry, loaded)
                    if identity is None:
                        continue
                    return RunningOverlap(identity=identity, pid=pid, mapping_file=loaded_path.resolve())
        return None


def configuration_set_for_shell(config: str | None) -> ConfigurationSet | None:
    """Resolve the configuration set a shell should talk to.

    When ``config`` names a mapping yaml already loaded by a running set,
    returns that running owner so the shell does not start a second watcher.
    Does not attach when ``config`` is None or already the global config.

    Args:
        config: Path from ``-c`` / ``--config``, or None.

    Returns:
        The resolved set, or None after echoing a resolution error.
    """
    asked = _resolve_configuration_set_identity(config)
    if asked is None or config is None or asked.is_global:
        return asked
    overlap = asked.running_overlap()
    if overlap is None:
        return asked
    return ConfigurationSet(overlap.identity)


def configuration_set_for_start(config: str | None) -> ConfigurationSet | None:
    """Resolve the configuration set ``daemon start`` asked for, without attach.

    Does not refuse overlap; the caller checks ``is_running`` then
    :meth:`ConfigurationSet.running_overlap`.

    Args:
        config: Path from ``-c`` / ``--config``, or None.

    Returns:
        The asked set, or None after echoing a resolution error.
    """
    return _resolve_configuration_set_identity(config)


def _resolve_configuration_set_identity(config: str | None) -> ConfigurationSet | None:
    """Resolve set identity without parsing mapping yaml.

    Args:
        config: Path from ``-c`` / ``--config``, or None.

    Returns:
        The asked set, or None after echoing a resolution error.
    """
    if config is not None:
        path = Path(config).resolve()
        asked = ConfigurationSet(path)
        if asked.is_global:
            return _global_set_or_none()
        if not path.exists():
            click.echo(f"Config file not found: {path}")
            return None
        return asked

    try:
        global_files = resolve_global_mapping_files()
    except BlfrcError as error:
        click.echo(f"Error: {error}")
        return None
    if global_files:
        return ConfigurationSet(global_config_path())
    return _cwd_set_or_none()


def _global_set_or_none() -> ConfigurationSet | None:
    """Return the global set when the pointer list names mapping files."""
    asked = ConfigurationSet(global_config_path())
    try:
        mapping_files = asked.mapping_files()
    except ConfigError as error:
        click.echo(f"Error: {error}")
        return None
    if not mapping_files:
        click.echo(f"Error: no mapping files in {global_config_path()}")
        return None
    return asked


def _cwd_set_or_none() -> ConfigurationSet | None:
    """Return the CWD ``config.yml`` singleton, or None when it is missing."""
    path = Path(DEFAULT_CONFIG_FILE).resolve()
    if not path.exists():
        click.echo(f"Config file not found: {path}\nHint: use --config <path> or add mapping files to ~/.blf/config")
        return None
    return ConfigurationSet(path)


def _read_mapping_files(run_dir: Path) -> list[Path]:
    path = run_dir / _MAPPING_FILES_NAME
    if not path.exists():
        return []
    files: list[Path] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            files.append(Path(text))
    return files


def _loaded_mapping_files(run_dir: Path) -> list[Path]:
    files = _read_mapping_files(run_dir)
    if files:
        return files
    if run_dir.name == _GLOBAL_RUN_NAME:
        return list(resolve_global_mapping_files() or [])
    return []


def _identity_path_for_run_dir(run_dir: Path, loaded: list[Path]) -> Path | None:
    if run_dir.name == _GLOBAL_RUN_NAME:
        return runtime_home() / "config"
    if loaded:
        return loaded[0].resolve()
    return None


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
