"""Project processing utilities for CLI commands.

This module handles config loading, path resolution, and project orchestration.
Operation logic lives in the ``operations`` package — one module per subcommand.
"""

from __future__ import annotations

from pathlib import Path

import click
import yaml

from .blfrc import BlfrcError, resolve_config_from_blfrc
from .config import Config, ConfigError
from .constants import DEFAULT_CONFIG_FILE
from .model.config import ConfigProject
from .model.translator import translate_config_to_processing
from .operations import CmdOperation


class ProjectProcessor:
    """Orchestrates processing of all projects for a given CLI operation.

    Iterates over all processing units derived from the config and delegates
    execution to the provided :class:`~beyond_local_file.operations.CmdOperation`.
    """

    @staticmethod
    def process_all_units(
        config_projects: dict[str, ConfigProject],
        operation: CmdOperation,
        skip_invalid: bool = True,
    ) -> bool:
        """Process all projects using new model structure with translation layer.

        Args:
            config_projects: Dictionary of ConfigProject instances.
            operation: The operation to execute for each processing unit.
            skip_invalid: Whether to skip invalid projects or stop processing.

        Returns:
            True if all operations completed, False if aborted.
        """
        processing_units = translate_config_to_processing(config_projects)

        for unit in processing_units:
            if not unit.managed_project_path.exists():
                click.echo(f"Project directory does not exist: {unit.managed_project_path}")
                if not skip_invalid:
                    return False
                continue

            if not unit.target_project_path.exists():
                click.echo(f"Target directory does not exist: {unit.target_project_path}")
                continue

            if operation.verbose_progress:
                click.echo(f"\nProcessing {unit.display_name} -> {unit.target_project_path}")

            if not operation.execute_unit(unit):
                return False

        return True


def load_config_projects(config: str, project_name: str | None = None) -> tuple[dict[str, ConfigProject], Path] | None:
    """Load configuration using new model structure with .blfrc support.

    Config resolution order:
    1. Explicit config parameter (from --config flag)
    2. ~/.blfrc file (if present and has config_file field)
    3. Default to config.yml in current directory

    Args:
        config: Path to the YAML configuration file from --config flag.
        project_name: Optional project name to filter. If provided, only
            returns configuration for that project.

    Returns:
        Tuple of (ConfigProject dict, config directory path).
        Returns None if loading failed.
    """
    config_paths = _resolve_config_paths_with_blfrc(config)
    if config_paths is None:
        return None

    if len(config_paths) == 1:
        return _load_single_config(config_paths[0], project_name)
    return _load_and_combine_configs(config_paths, project_name)


def _resolve_config_paths_with_blfrc(config: str) -> list[Path] | None:
    """Resolve config file paths using .blfrc or default.

    Args:
        config: Config path from --config flag.

    Returns:
        List of config file paths to load, or None if config not found.
    """
    if config != DEFAULT_CONFIG_FILE:
        config_path = Path(_get_absolute_path(config))
        if not config_path.exists():
            click.echo(f"Config file not found: {config_path}")
            return None
        return [config_path]

    try:
        blfrc_configs = resolve_config_from_blfrc()
        if blfrc_configs:
            return blfrc_configs
    except BlfrcError as e:
        click.echo(f"Error: {e}")
        return None

    config_path = Path(_get_absolute_path(config))
    if not config_path.exists():
        click.echo(f"Config file not found: {config_path}")
        return None
    return [config_path]


def _load_single_config(
    config_path: Path | str, project_name: str | None
) -> tuple[dict[str, ConfigProject], Path] | None:
    """Load a single config file.

    Args:
        config_path: Path to the YAML configuration file.
        project_name: Optional project name to filter.

    Returns:
        Tuple of (ConfigProject dict, config directory path).
        Returns None if loading failed.
    """
    try:
        cfg = Config(Path(config_path))
        cfg.load()
        projects = cfg.get_config_projects(project_name)
        config_dir = Path(config_path).parent
        return projects, config_dir
    except (FileNotFoundError, ValueError, yaml.YAMLError) as e:
        click.echo(str(e))
        return None


def _load_and_combine_configs(
    config_paths: list[Path], project_name: str | None
) -> tuple[dict[str, ConfigProject], Path] | None:
    """Load and combine multiple config files with conflict detection.

    Each config file's project names are resolved relative to that config
    file's own directory, preserving correct managed project paths. Each
    config file is read exactly once.

    Args:
        config_paths: List of config file paths to load.
        project_name: Optional project name to filter.

    Returns:
        Tuple of (ConfigProject dict, first config directory path).
        Returns None if loading failed.
    """
    try:
        combined_projects: dict[str, ConfigProject] = {}
        managed_project_sources: dict[Path, Path] = {}

        for path in config_paths:
            cfg = Config(path)
            cfg.load()
            projects = cfg.get_config_projects()

            for proj in projects.values():
                managed_path = proj.managed_project_path

                if managed_path in managed_project_sources:
                    existing = managed_project_sources[managed_path]
                    raise ConfigError(
                        f"Managed project '{managed_path}' defined in multiple config files: {existing}, {path}"
                    )

                managed_project_sources[managed_path] = path
                combined_projects[str(managed_path)] = proj

        if project_name:
            matches = {k: v for k, v in combined_projects.items() if v.managed_project_name == project_name}
            if not matches:
                click.echo(f"Project '{project_name}' not found in config")
                return None
            combined_projects = matches

        config_dir = config_paths[0].parent
        return combined_projects, config_dir
    except (ConfigError, ValueError) as e:
        click.echo(f"Error: {e}")
        return None
    except Exception as e:
        click.echo(str(e))
        return None


def get_absolute_path(path: str) -> str:
    """Resolve a path to its absolute form.

    Args:
        path: A file or directory path.

    Returns:
        Absolute path as a string.
    """
    return str(Path(path).resolve())


def _get_absolute_path(path: str) -> str:
    return get_absolute_path(path)
