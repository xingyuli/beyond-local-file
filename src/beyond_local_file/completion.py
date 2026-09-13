"""Shell completion helpers for CLI arguments."""

from pathlib import Path

import click
import click.shell_completion
import yaml

from .blfrc import resolve_global_mapping_files
from .constants import DEFAULT_CONFIG_FILE


def complete_project_names(
    ctx: click.Context,
    param: click.Parameter,
    incomplete: str,
) -> list[click.shell_completion.CompletionItem]:
    """Return project name completions from the active config file.

    Reads the same config that the command would use (respecting --config
    and ~/.blf/config), then filters project names by the incomplete prefix.
    Returns an empty list on any error so completion never crashes the shell.

    Args:
        ctx: The current Click context (carries --config via ctx.obj).
        param: The parameter being completed (unused, required by protocol).
        incomplete: The partial string typed so far.

    Returns:
        List of CompletionItem objects for matching project names.
    """
    try:
        names: list[str] = []
        for config_path in _resolve_mapping_files(ctx):
            if not config_path.exists():
                continue
            with open(config_path) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                continue
            names.extend(name for name in data if name.startswith(incomplete) and name not in names)
        return [click.shell_completion.CompletionItem(name) for name in names]
    except Exception:
        return []


def _resolve_mapping_files(ctx: click.Context) -> list[Path]:
    """Resolve mapping files from context, the global config, or CWD.

    Mirrors the resolution order of load_config_projects but stays silent.

    Args:
        ctx: The current Click context.

    Returns:
        Mapping yaml paths to read project names from.
    """
    config_obj = ctx.obj or {}
    explicit = config_obj.get("config")
    if explicit is not None:
        return [Path(explicit).resolve()]

    try:
        global_files = resolve_global_mapping_files()
        if global_files:
            return global_files
    except Exception:
        pass

    return [Path(DEFAULT_CONFIG_FILE).resolve()]
