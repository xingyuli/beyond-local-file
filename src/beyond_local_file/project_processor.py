"""Project processing utilities for CLI commands.

This module handles config loading, path resolution, and project orchestration.
Operation logic lives in the ``operations`` package — one module per subcommand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import click
import yaml

from .blfrc import (
    BlfrcError,
    global_config_path,
    is_global_config_path,
    resolve_global_mapping_files,
)
from .config import Config, ConfigError
from .constants import DEFAULT_CONFIG_FILE
from .contribution import contribution_owner, projects_targeting
from .daemon.process import mapping_files_for, running_owner_of
from .model.config import ConfigProject
from .model.translator import translate_config_to_processing
from .operations import CmdOperation
from .operations.revlink import RevlinkContext


@dataclass(frozen=True)
class ConfigLoadResult:
    """Result of a successful :func:`load_config_projects` call.

    Attributes:
        projects: Mapping of project key to :class:`~beyond_local_file.model.config.ConfigProject`.
        config_file: Set identity path used to talk to the daemon. The global
            set uses ``~/.blf/config``; a singleton set uses its mapping yaml.
        mapping_files: Mapping yaml files this set loads.
        project_sources: Managed-project path to the mapping yaml that defined it.
    """

    projects: dict[str, ConfigProject]
    config_file: Path
    mapping_files: tuple[Path, ...] = ()
    project_sources: dict[Path, Path] = field(default_factory=dict)


@dataclass(frozen=True)
class RevlinkResolveError:
    """Terminal error from revlink context resolution.

    Returned by :func:`resolve_revlink_context` when the resolution sequence
    cannot produce a :class:`~beyond_local_file.operations.revlink.RevlinkContext`.
    The caller should print ``message`` (if not ``None``) and exit with
    ``exit_code``.

    Attributes:
        message: Human-readable error message to display to the user.
            ``None`` when :func:`load_config_projects` already printed the
            diagnostic — the caller must skip ``click.echo`` in that case.
        exit_code: Suggested process exit code (always 1 for errors).
    """

    message: str | None
    exit_code: int = field(default=1)


def resolve_revlink_context(
    config: str | None,
    cwd: Path,
    *,
    project_name: str | None = None,
    rel_path: str | Path | None = None,
) -> RevlinkContext | RevlinkResolveError:
    """Resolve config, match CWD to a project, and build a RevlinkContext.

    Encapsulates the full resolution sequence shared by ``revlink create``,
    ``revlink restore``, and ``remove``: load the config, match ``cwd`` to
    managed projects, optionally disambiguate by ``project_name`` or the
    contribution source of ``rel_path``, and return a
    :class:`~beyond_local_file.operations.revlink.RevlinkContext` ready for
    the caller to pass to a standalone reverse-link or removal operation.

    Args:
        config: Path to the YAML config file (from ``--config``), or ``None``
            to use the default resolution order (``~/.blf/config`` → ``config.yml``).
        cwd: The current working directory to match against each mapping's
            target paths.
        project_name: When set, use this managed project; it must still
            target ``cwd``. Create sends this after a shell interview.
        rel_path: Target-relative path used by restore and remove to pick
            the unique contribution source among projects targeting ``cwd``.

    Returns:
        A :class:`~beyond_local_file.operations.revlink.RevlinkContext` when a
        unique project is found and its mapping is resolved.  A
        :class:`RevlinkResolveError` when config loading fails, no project
        matches ``cwd``, ``rel_path`` is not a managed item, or multiple
        projects match ``cwd`` with no owner and no ``project_name``.
        When the error message is empty, :func:`load_config_projects` has
        already printed the diagnostic; callers must skip ``click.echo``.
    """
    result = load_config_projects(config)
    if result is None:
        return RevlinkResolveError(message=None)

    project = _resolve_project_from_cwd(result.projects, cwd)

    if project is None:
        hint = (
            "Hint: add a target entry for this directory in your config, "
            "or use --config to specify the correct config file."
        )
        return RevlinkResolveError(message=f"No managed project found for current directory: {cwd}\n{hint}")

    if isinstance(project, list):
        project = _disambiguate_revlink_project(project, result.projects, cwd, project_name, rel_path)
        if isinstance(project, RevlinkResolveError):
            return project

    matched_mapping = next(m for m in project.mappings if cwd in m.targets)
    source = result.project_sources.get(project.managed_project_path, result.config_file)

    return RevlinkContext(
        config_path=source,
        project_name=project.managed_project_name,
        matched_mapping=matched_mapping,
        cwd=cwd,
        managed_project_path=project.managed_project_path,
        mappings=project.mappings,
    )


def _disambiguate_revlink_project(
    matches: list[ConfigProject],
    projects: dict[str, ConfigProject],
    cwd: Path,
    project_name: str | None,
    rel_path: str | Path | None,
) -> ConfigProject | RevlinkResolveError:
    """Pick one of *matches* by explicit name or contribution source.

    Args:
        matches: Managed projects whose mappings include *cwd*.
        projects: Full loaded project map.
        cwd: Target directory.
        project_name: Explicit hub from the create shell, if any.
        rel_path: Path used to derive contribution source.

    Returns:
        The chosen project, or a resolve error when the owner is missing.
    """
    if project_name:
        for candidate in matches:
            if candidate.managed_project_name == project_name:
                return candidate
        return RevlinkResolveError(message=f"Project '{project_name}' does not target {cwd}")
    if rel_path is not None:
        rel = Path(rel_path).as_posix()
        owner = contribution_owner(projects, cwd, rel)
        if owner is None:
            return RevlinkResolveError(message=f"'{rel}' is not a managed item")
        return owner
    names = ", ".join(candidate.managed_project_name for candidate in matches)
    return RevlinkResolveError(message=f"Ambiguous: multiple projects target {cwd}: {names}")


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


def load_config_projects(config: str | None, project_name: str | None = None) -> ConfigLoadResult | None:
    """Load configuration for shells, routing ``-c`` to a running owner set.

    Config resolution order:
    1. Explicit config parameter (from --config flag)
    2. ``~/.blf/config`` pointer list (the global set)
    3. Default to config.yml in current directory

    When ``-c`` names a mapping yaml already loaded by a running set, the
    result identifies that running set so shells do not start a second watcher.

    Args:
        config: Path to the YAML configuration file from --config flag,
            or None if the flag was not provided.
        project_name: Optional project name to filter. If provided, only
            returns configuration for that project.

    Returns:
        A :class:`ConfigLoadResult` on success, or ``None`` if loading failed.
    """
    result = resolve_configuration_set(config, project_name)
    if result is None or config is None:
        return result
    path = Path(_get_absolute_path(config))
    if is_global_config_path(path):
        return result
    owner = running_owner_of(path)
    if owner is None or owner.resolve() == result.config_file.resolve():
        return result
    return resolve_configuration_set(str(owner), project_name)


def resolve_configuration_set(config: str | None, project_name: str | None = None) -> ConfigLoadResult | None:
    """Resolve the configuration set the caller asked for, without overlap routing.

    Args:
        config: Path from ``--config``, or None to use global then CWD.
        project_name: Optional project name to filter.

    Returns:
        A :class:`ConfigLoadResult` on success, or ``None`` if loading failed.
    """
    if config is not None:
        path = Path(_get_absolute_path(config))
        if is_global_config_path(path):
            return _load_global_set(project_name)
        return _load_config_from_path(config, project_name)

    try:
        global_files = resolve_global_mapping_files()
    except BlfrcError as e:
        click.echo(f"Error: {e}")
        return None

    if global_files:
        return _load_global_set(project_name)

    return _load_config_from_path(DEFAULT_CONFIG_FILE, project_name, show_hint=True)


def load_set_projects(config_path: Path, project_name: str | None = None) -> dict[str, ConfigProject]:
    """Load mapping projects for a configuration set identity path.

    The global set loads every mapping file listed in ``~/.blf/config``.
    A singleton set loads that one mapping yaml.

    Args:
        config_path: Set identity path (global config or a mapping yaml).
        project_name: Optional project name to filter.

    Returns:
        Combined config projects.

    Raises:
        ConfigError: If mapping files conflict or cannot be loaded.
    """
    paths = mapping_files_for(config_path)
    if not paths:
        raise ConfigError(f"No mapping files for {config_path}")
    if len(paths) == 1:
        cfg = Config(paths[0])
        cfg.load()
        return cfg.get_config_projects(project_name)
    projects, _sources = combine_mapping_projects(paths, project_name)
    return projects


def _load_config_from_path(
    config: str, project_name: str | None, *, show_hint: bool = False
) -> ConfigLoadResult | None:
    """Resolve a config path string, check existence, and load it.

    Args:
        config: Path string to the YAML configuration file.
        project_name: Optional project name to filter.
        show_hint: When True, append a usage hint to the "not found" error
            message. Set by callers that fall back to the default path so
            users know how to specify a config explicitly.

    Returns:
        A :class:`ConfigLoadResult` on success, or ``None`` if the file does
        not exist or loading failed.
    """
    config_path = Path(_get_absolute_path(config))
    if not config_path.exists():
        msg = f"Config file not found: {config_path}"
        if show_hint:
            msg += "\nHint: use --config <path> or add mapping files to ~/.blf/config"
        click.echo(msg)
        return None
    return _load_single_config(config_path, project_name)


def _load_single_config(config_path: Path | str, project_name: str | None) -> ConfigLoadResult | None:
    """Load a single config file.

    Args:
        config_path: Path to the YAML configuration file.
        project_name: Optional project name to filter.

    Returns:
        A :class:`ConfigLoadResult` on success, or ``None`` if loading failed.
    """
    try:
        resolved = Path(config_path).resolve()
        cfg = Config(resolved)
        cfg.load()
        projects = cfg.get_config_projects(project_name)
        sources = {project.managed_project_path: resolved for project in projects.values()}
        return ConfigLoadResult(
            projects=projects,
            config_file=resolved,
            mapping_files=(resolved,),
            project_sources=sources,
        )
    except (ConfigError, FileNotFoundError, ValueError, yaml.YAMLError) as e:
        click.echo(str(e))
        return None


def _load_global_set(project_name: str | None) -> ConfigLoadResult | None:
    """Load every mapping file listed in the global pointer list.

    Args:
        project_name: Optional project name to filter.

    Returns:
        The global set, or ``None`` if loading failed.
    """
    try:
        paths = resolve_global_mapping_files()
    except BlfrcError as e:
        click.echo(f"Error: {e}")
        return None
    if not paths:
        click.echo(f"Error: no mapping files in {global_config_path()}")
        return None
    try:
        projects, sources = _projects_for_global_paths(paths, project_name)
    except (ConfigError, FileNotFoundError, ValueError, yaml.YAMLError) as e:
        click.echo(f"Error: {e}")
        return None
    if projects is None:
        return None
    if project_name and not projects:
        click.echo(f"Project '{project_name}' not found in config")
        return None
    return ConfigLoadResult(
        projects=projects,
        config_file=global_config_path(),
        mapping_files=tuple(paths),
        project_sources=sources,
    )


def _projects_for_global_paths(
    paths: list[Path],
    project_name: str | None,
) -> tuple[dict[str, ConfigProject], dict[Path, Path]] | tuple[None, None]:
    if len(paths) == 1:
        loaded = _load_single_config(paths[0], project_name)
        if loaded is None:
            return None, None
        return loaded.projects, loaded.project_sources
    return combine_mapping_projects(paths, project_name)


def combine_mapping_projects(
    config_paths: list[Path],
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


def _resolve_project_from_cwd(
    config_projects: dict[str, ConfigProject],
    cwd: Path,
) -> ConfigProject | None | list[ConfigProject]:
    """Resolve the managed project whose target paths include the given directory.

    Iterates all ``ConfigProject`` instances and collects those whose
    ``Mapping.targets`` contain ``cwd``.  The return type encodes the three
    possible outcomes:

    - **Exactly one match** — returns the matching ``ConfigProject`` directly.
    - **No match** — returns ``None``; the caller should emit a descriptive
      error and exit with a non-zero status code.
    - **Multiple matches** — returns a ``list[ConfigProject]`` containing every
      matching project; the caller should report the ambiguity and exit with a
      non-zero status code.

    Args:
        config_projects: Dictionary of project key → ``ConfigProject`` as
            returned by :func:`load_config_projects`.
        cwd: The current working directory to match against each mapping's
            target paths.

    Returns:
        A single ``ConfigProject`` when exactly one project targets ``cwd``,
        ``None`` when no project targets ``cwd``, or a ``list[ConfigProject]``
        when two or more projects target ``cwd``.
    """
    matches = projects_targeting(config_projects, cwd)

    if len(matches) == 1:
        return matches[0]
    if len(matches) == 0:
        return None
    return matches


def _get_absolute_path(path: str) -> str:
    """Resolve a path to its absolute form.

    Args:
        path: A file or directory path.

    Returns:
        Absolute path as a string.
    """
    return str(Path(path).resolve())
