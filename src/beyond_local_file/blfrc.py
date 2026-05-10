"""Support for .blfrc configuration file in home directory."""

import os
from pathlib import Path

import yaml


class BlfrcError(Exception):
    """Error related to .blfrc file processing."""

    pass


def get_home_directory() -> Path:
    """Get home directory, respecting BLF_HOME env var for testing.

    Returns:
        Path to home directory.
    """
    if "BLF_HOME" in os.environ:
        return Path(os.environ["BLF_HOME"])
    return Path.home()


def resolve_config_from_blfrc() -> list[Path] | None:
    """Resolve config file path(s) from ~/.blfrc.

    Returns:
        List of config file paths if .blfrc exists and is valid.
        None if .blfrc doesn't exist or config_file field is missing.

    Raises:
        BlfrcError: If .blfrc exists but is invalid.
    """
    blfrc_path = get_home_directory() / ".blfrc"

    # If .blfrc doesn't exist, return None (silent fallback)
    if not blfrc_path.exists():
        return None

    # Load and parse .blfrc
    data = _load_blfrc_file(blfrc_path)
    if data is None:
        return None

    # Extract and validate config_file field
    config_files = _extract_config_files(data, blfrc_path)
    if config_files is None:
        return None

    # Resolve and validate each config file path
    return _resolve_config_paths(config_files, blfrc_path)


def _load_blfrc_file(blfrc_path: Path) -> dict | None:
    """Load and parse .blfrc file.

    Args:
        blfrc_path: Path to .blfrc file.

    Returns:
        Parsed YAML data as dict, or None if file is empty.

    Raises:
        BlfrcError: If file is not readable or contains invalid YAML.
    """
    # Check if .blfrc is readable
    if not os.access(blfrc_path, os.R_OK):
        raise BlfrcError(f"Cannot read {blfrc_path}: Permission denied")

    # Parse .blfrc as YAML
    try:
        with open(blfrc_path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise BlfrcError(f"Invalid YAML in {blfrc_path}: {e}") from e
    except Exception as e:
        raise BlfrcError(f"Error reading {blfrc_path}: {e}") from e

    # If data is None or not a dict, treat as empty
    if data is None or not isinstance(data, dict):
        return None

    return data


def _extract_config_files(data: dict, blfrc_path: Path) -> list[str] | None:
    """Extract and validate config_file field from .blfrc data.

    Args:
        data: Parsed .blfrc YAML data.
        blfrc_path: Path to .blfrc file (for error messages).

    Returns:
        List of config file path strings, or None if field is missing.

    Raises:
        BlfrcError: If config_file field is invalid.
    """
    # Check if config_file field exists
    if "config_file" not in data:
        return None  # Silent fallback - allows disabling via comment

    config_file = data["config_file"]

    # Validate config_file type and normalize to list
    if isinstance(config_file, str):
        config_files = [config_file]
    elif isinstance(config_file, list):
        config_files = config_file
    else:
        raise BlfrcError(f"'config_file' in {blfrc_path} must be a string or list of strings")

    # Validate list is not empty
    if not config_files:
        raise BlfrcError(f"'config_file' in {blfrc_path} cannot be an empty list")

    # Validate all items are non-empty strings
    for i, item in enumerate(config_files, 1):
        if not isinstance(item, str):
            raise BlfrcError(f"All items in 'config_file' list must be strings (item {i} is {type(item).__name__})")
        if not item or not item.strip():
            raise BlfrcError(f"'config_file' in {blfrc_path} cannot be empty")

    return config_files


def _resolve_config_paths(config_files: list[str], blfrc_path: Path) -> list[Path]:
    """Resolve and validate config file paths.

    Args:
        config_files: List of config file path strings.
        blfrc_path: Path to .blfrc file (for error messages).

    Returns:
        List of resolved and validated Path objects.

    Raises:
        BlfrcError: If any path is invalid or file doesn't exist.
    """
    resolved_paths = []
    home_dir = get_home_directory()

    for i, raw_path in enumerate(config_files, 1):
        path_str = raw_path.strip()

        # Resolve path based on type
        resolved_path = _resolve_single_path(path_str, home_dir)

        # Validate the resolved path
        _validate_config_path(resolved_path, i, len(config_files), blfrc_path)

        resolved_paths.append(resolved_path)

    return resolved_paths


def _resolve_single_path(path_str: str, home_dir: Path) -> Path:
    """Resolve a single config file path string.

    Args:
        path_str: Config file path string.
        home_dir: Home directory path.

    Returns:
        Resolved absolute Path.
    """
    if path_str.startswith("/"):
        # Absolute path
        return Path(path_str).resolve()
    if path_str.startswith("~"):
        # Tilde expansion - replace ~ with home_dir
        # Don't use expanduser() as it uses system home, not BLF_HOME
        path_without_tilde = path_str[1:]  # Remove ~
        if path_without_tilde.startswith("/"):
            path_without_tilde = path_without_tilde[1:]  # Remove leading /
        return (home_dir / path_without_tilde).resolve()
    # Relative to home directory
    return (home_dir / path_str).resolve()


def _validate_config_path(resolved_path: Path, index: int, total: int, blfrc_path: Path) -> None:
    """Validate that a resolved config path exists and is readable.

    Args:
        resolved_path: Resolved config file path.
        index: Index of this file in the list (1-based).
        total: Total number of config files.
        blfrc_path: Path to .blfrc file (for error messages).

    Raises:
        BlfrcError: If path doesn't exist, is a directory, or is not readable.
    """
    file_info = f"file {index} of {total}" if total > 1 else ""

    # Verify file exists
    if not resolved_path.exists():
        raise BlfrcError(f"Config file not found: {resolved_path} ({file_info} from {blfrc_path})".strip())

    # Verify it's a file, not a directory
    if resolved_path.is_dir():
        raise BlfrcError(f"Config file is a directory: {resolved_path} ({file_info} from {blfrc_path})".strip())

    # Verify it's readable
    if not os.access(resolved_path, os.R_OK):
        raise BlfrcError(f"Cannot read config file: {resolved_path}: Permission denied")
