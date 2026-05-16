"""Shell completion helpers for CLI arguments."""

from pathlib import Path

import click
import click.shell_completion
import yaml

from .blfrc import resolve_config_from_blfrc
from .constants import DEFAULT_CONFIG_FILE


def complete_project_names(
    ctx: click.Context,
    param: click.Parameter,
    incomplete: str,
) -> list[click.shell_completion.CompletionItem]:
    """Return project name completions from the active config file.

    Reads the same config that the command would use (respecting --config
    and ~/.blfrc), then filters project names by the incomplete prefix.
    Returns an empty list on any error so completion never crashes the shell.

    Args:
        ctx: The current Click context (carries --config via ctx.obj).
        param: The parameter being completed (unused, required by protocol).
        incomplete: The partial string typed so far.

    Returns:
        List of CompletionItem objects for matching project names.
    """
    try:
        config_path = _resolve_config_path(ctx)
        if config_path is None or not config_path.exists():
            return []

        with open(config_path) as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            return []

        return [click.shell_completion.CompletionItem(name) for name in data if name.startswith(incomplete)]
    except Exception:
        return []


def _resolve_config_path(ctx: click.Context) -> Path | None:
    """Resolve the config file path from context, .blfrc, or default.

    Mirrors the resolution order of load_config_projects but returns
    None instead of printing errors, so completion stays silent.

    Args:
        ctx: The current Click context.

    Returns:
        Resolved Path to the config file, or None if unresolvable.
    """
    # 1. Explicit --config flag
    config_obj = ctx.obj or {}
    explicit = config_obj.get("config")
    if explicit is not None:
        return Path(explicit).resolve()

    # 2. ~/.blfrc
    try:
        blfrc_paths = resolve_config_from_blfrc()
        if blfrc_paths:
            return blfrc_paths[0]  # first config is sufficient for name listing
    except Exception:
        pass

    # 3. Default config.yml in CWD
    return Path(DEFAULT_CONFIG_FILE).resolve()
