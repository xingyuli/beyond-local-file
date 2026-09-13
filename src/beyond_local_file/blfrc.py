"""Support for the global config pointer list at ``~/.blf/config``."""

import os
from pathlib import Path

import yaml


class BlfrcError(Exception):
    """Error related to global config file processing."""


def get_home_directory() -> Path:
    """Get home directory, respecting BLF_HOME env var for testing.

    Returns:
        Path to home directory.
    """
    if "BLF_HOME" in os.environ:
        return Path(os.environ["BLF_HOME"])
    return Path.home()


def runtime_home() -> Path:
    """Return the runtime home directory.

    ``BLF_HOME`` relocates the home used for ``~/.blf``.

    Returns:
        ``<home>/.blf``.
    """
    return get_home_directory() / ".blf"


def global_config_path() -> Path:
    """Return the global config pointer-list path.

    Returns:
        ``<home>/.blf/config``.
    """
    return runtime_home() / "config"


def is_global_config_path(path: Path) -> bool:
    """Return whether *path* is the global config pointer list.

    Args:
        path: Candidate path.

    Returns:
        True when *path* resolves to ``~/.blf/config``.
    """
    try:
        return Path(path).resolve() == global_config_path().resolve()
    except OSError:
        return False


def resolve_global_mapping_files() -> list[Path] | None:
    """Resolve mapping file path(s) from ``~/.blf/config``.

    Returns:
        List of mapping file paths if the global config exists and is valid.
        None if it does not exist or the ``config_file`` field is missing.

    Raises:
        BlfrcError: If the global config exists but is invalid.
    """
    pointer_path = global_config_path()

    if not pointer_path.exists():
        return None

    data = _load_pointer_file(pointer_path)
    if data is None:
        return None

    config_files = _extract_config_files(data, pointer_path)
    if config_files is None:
        return None

    return _resolve_config_paths(config_files, pointer_path)


def _load_pointer_file(pointer_path: Path) -> dict | None:
    """Load and parse the global config pointer list.

    Args:
        pointer_path: Path to ``~/.blf/config``.

    Returns:
        Parsed YAML data as dict, or None if file is empty.

    Raises:
        BlfrcError: If file is not readable or contains invalid YAML.
    """
    if not os.access(pointer_path, os.R_OK):
        raise BlfrcError(f"Cannot read {pointer_path}: Permission denied")

    try:
        with open(pointer_path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise BlfrcError(f"Invalid YAML in {pointer_path}: {e}") from e
    except OSError as e:
        raise BlfrcError(f"Error reading {pointer_path}: {e}") from e

    if data is None or not isinstance(data, dict):
        return None

    return data


def _extract_config_files(data: dict, pointer_path: Path) -> list[str] | None:
    """Extract and validate config_file field from the pointer list.

    Args:
        data: Parsed YAML data.
        pointer_path: Path to the pointer list (for error messages).

    Returns:
        List of config file path strings, or None if field is missing.

    Raises:
        BlfrcError: If config_file field is invalid.
    """
    if "config_file" not in data:
        return None

    config_file = data["config_file"]

    if isinstance(config_file, str):
        config_files = [config_file]
    elif isinstance(config_file, list):
        config_files = config_file
    else:
        raise BlfrcError(f"'config_file' in {pointer_path} must be a string or list of strings")

    if not config_files:
        raise BlfrcError(f"'config_file' in {pointer_path} cannot be an empty list")

    for i, item in enumerate(config_files, 1):
        if not isinstance(item, str):
            raise BlfrcError(f"All items in 'config_file' list must be strings (item {i} is {type(item).__name__})")
        if not item or not item.strip():
            raise BlfrcError(f"'config_file' in {pointer_path} cannot be empty")

    return config_files


def _resolve_config_paths(config_files: list[str], pointer_path: Path) -> list[Path]:
    """Resolve and validate mapping file paths.

    Args:
        config_files: List of config file path strings.
        pointer_path: Path to the pointer list (for error messages).

    Returns:
        List of resolved and validated Path objects.

    Raises:
        BlfrcError: If any path is invalid or file doesn't exist.
    """
    resolved_paths = []
    home_dir = get_home_directory()

    for i, raw_path in enumerate(config_files, 1):
        path_str = raw_path.strip()
        resolved_path = _resolve_single_path(path_str, home_dir)
        _validate_config_path(resolved_path, i, len(config_files), pointer_path)
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
        return Path(path_str).resolve()
    if path_str.startswith("~"):
        path_without_tilde = path_str[1:]
        if path_without_tilde.startswith("/"):
            path_without_tilde = path_without_tilde[1:]
        return (home_dir / path_without_tilde).resolve()
    return (home_dir / path_str).resolve()


def _validate_config_path(resolved_path: Path, index: int, total: int, pointer_path: Path) -> None:
    """Validate that a resolved config path exists and is readable.

    Args:
        resolved_path: Resolved config file path.
        index: Index of this file in the list (1-based).
        total: Total number of config files.
        pointer_path: Path to the pointer list (for error messages).

    Raises:
        BlfrcError: If path doesn't exist, is a directory, or is not readable.
    """
    file_info = f"file {index} of {total}" if total > 1 else ""

    if not resolved_path.exists():
        raise BlfrcError(f"Config file not found: {resolved_path} ({file_info} from {pointer_path})".strip())

    if resolved_path.is_dir():
        raise BlfrcError(f"Config file is a directory: {resolved_path} ({file_info} from {pointer_path})".strip())

    if not os.access(resolved_path, os.R_OK):
        raise BlfrcError(f"Cannot read config file: {resolved_path}: Permission denied")
