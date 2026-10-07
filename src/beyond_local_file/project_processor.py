"""Project processing utilities for CLI commands.

This module resolves revlink contribution-source context.
Operation logic lives in the ``operations`` package — one module per subcommand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import click

from .configuration_set import ConfigError, configuration_set_for_shell
from .contribution import contribution_owner, projects_targeting
from .model.config import ConfigProject
from .operations.revlink import RevlinkContext


@dataclass(frozen=True)
class RevlinkResolveError:
    """Terminal error from revlink context resolution.

    Returned by :func:`resolve_revlink_context` when the resolution sequence
    cannot produce a :class:`~beyond_local_file.operations.revlink.RevlinkContext`.
    The caller should print ``message`` (if not ``None``) and exit with
    ``exit_code``.

    Attributes:
        message: Human-readable error message to display to the user.
            ``None`` when :func:`configuration_set_for_shell` already printed
            the diagnostic — the caller must skip ``click.echo`` in that case.
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
        When the error message is empty, :func:`configuration_set_for_shell`
        has already printed the diagnostic; callers must skip ``click.echo``.
    """
    asked = configuration_set_for_shell(config)
    if asked is None:
        return RevlinkResolveError(message=None)
    try:
        projects = asked.projects()
        sources = asked.project_sources()
    except ConfigError as error:
        if asked.is_global:
            click.echo(f"Error: {error}")
        else:
            click.echo(str(error))
        return RevlinkResolveError(message=None)

    project = _resolve_project_from_cwd(projects, cwd)

    if project is None:
        hint = (
            "Hint: add a target entry for this directory in your config, "
            "or use --config to specify the correct config file."
        )
        return RevlinkResolveError(message=f"No managed project found for current directory: {cwd}\n{hint}")

    if isinstance(project, list):
        project = _disambiguate_revlink_project(project, projects, cwd, project_name, rel_path)
        if isinstance(project, RevlinkResolveError):
            return project

    matched_mapping = next(m for m in project.mappings if cwd in m.targets)
    source = sources.get(project.managed_project_path, asked.identity)

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
        config_projects: Dictionary of project key → ``ConfigProject``.
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
