"""Configuration management for the link CLI tool."""

from pathlib import Path
from typing import Any

import yaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from .model.config import ConfigProject, Mapping

_KEY_TARGET = "target"
_KEY_SUBPATH = "subpath"


class ConfigError(Exception):
    """Error related to configuration loading or validation."""

    pass


class Config:
    """Manages configuration loaded from a YAML file.

    The configuration file maps project names to their target paths.
    Each project can have one or more mappings, where each mapping can be:

    - **Simple string mapping**: Syncs everything from project to target::

        project-a: /path/to/target

    - **Dict mapping**: Supports selective subpath sync and copy strategy::

        project-b:
          target: /path/to/target
          subpath:
            - .kiro/hooks
            - path: .qoder/rules.md
              copy: true

    Mappings can be combined in a list for multiple targets::

        project-c:
          - /path/to/target1
          - target: /path/to/target2
            subpath:
              - .kiro/hooks

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

    def get_config_projects(self, project_name: str | None = None) -> dict[str, ConfigProject]:
        """Get project configurations using new model structure.

        Parses YAML according to the formal grammar, preserving the mapping structure.
        Each project has a list of mappings, where each mapping defines targets and
        optional sync rules (subpaths, copy strategy).

        Grammar structure:
        - project-name: string-mapping | dict-mapping | list-of-mappings
        - string-mapping: target-path (string)
        - dict-mapping: {target: target-path(s), subpath?: [...], ...}
        - list-of-mappings: [string-mapping | dict-mapping, ...]

        Args:
            project_name: Optional project name to filter. If provided, only
                        returns configuration for that project.

        Returns:
            Dictionary mapping project names to ConfigProject objects.
            Each ConfigProject contains the project path and list of mappings.

        Raises:
            ValueError: If the specified project_name is not in the config.
        """
        if self._data is None:
            self.load()

        if project_name:
            if project_name not in self._data:
                raise ValueError(f"Project '{project_name}' not found in config")
            config_project = self._build_config_project(project_name, self._data[project_name])
            return {project_name: config_project}

        result = {}
        for name, value in self._data.items():
            result[name] = self._build_config_project(name, value)
        return result

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

    def _parse_subpaths(self, raw: str | list | None) -> tuple[list[str] | None, set[str] | None]:
        """Parse subpath entries, extracting copy flags.

        Each entry can be a plain string or a dict with ``path`` and
        optional ``copy: true``.

        Args:
            raw: Raw subpath value from YAML — string, list, or None.

        Returns:
            Tuple of (subpath list, set of paths marked for copy).
            Either element may be None when there are no entries.
        """
        if raw is None:
            return None, None

        if isinstance(raw, str):
            return [raw], None

        subpaths: list[str] = []
        copy_paths: set[str] = set()

        for entry in raw:
            if isinstance(entry, str):
                subpaths.append(entry)
            elif isinstance(entry, dict) and "path" in entry:
                path = entry["path"]
                subpaths.append(path)
                if entry.get("copy", False):
                    copy_paths.add(path)

        return subpaths or None, copy_paths or None

    def _build_config_project(self, name: str, value: str | list | dict) -> ConfigProject:
        """Build a ConfigProject from raw YAML value according to grammar.

        Grammar productions:
        - string-mapping: target-path (string)
        - dict-mapping: {target: target-path(s), subpath?: [...], ...}
        - list-of-mappings: [string-mapping | dict-mapping, ...]

        Args:
            name: The project name.
            value: The raw YAML value (string, list, or dict).

        Returns:
            ConfigProject with list of mappings preserving the YAML structure.
        """
        project_path = self._resolve_project_path(name)

        # Single string mapping: project-name: /target
        if isinstance(value, str):
            mapping = self._parse_string_mapping(value)
            return ConfigProject(
                managed_project_name=name,
                managed_project_path=project_path,
                mappings=[mapping],
            )

        # Single dict mapping: project-name: {target: /target, subpath: [...]}
        if isinstance(value, dict) and _KEY_TARGET in value:
            mapping = self._parse_dict_mapping(value)
            return ConfigProject(
                managed_project_name=name,
                managed_project_path=project_path,
                mappings=[mapping],
            )

        # List of mappings: project-name: [mapping1, mapping2, ...]
        if isinstance(value, list):
            mappings = []
            for item in value:
                if isinstance(item, str):
                    mappings.append(self._parse_string_mapping(item))
                elif isinstance(item, dict) and _KEY_TARGET in item:
                    mappings.append(self._parse_dict_mapping(item))
            return ConfigProject(
                managed_project_name=name,
                managed_project_path=project_path,
                mappings=mappings,
            )

        # Fallback: treat as string mapping
        mapping = self._parse_string_mapping(str(value))
        return ConfigProject(
            managed_project_name=name,
            managed_project_path=project_path,
            mappings=[mapping],
        )

    def _parse_string_mapping(self, target: str) -> Mapping:
        """Parse a string mapping: /target or [/target1, /target2].

        Args:
            target: Target path string.

        Returns:
            Mapping with single target, no subpaths.
        """
        targets = self._normalize_targets(target)
        return Mapping(targets=targets, subpaths=None, copy_paths=None)

    def _parse_dict_mapping(self, mapping_dict: dict) -> Mapping:
        """Parse a dict mapping with target and optional subpath/copy.

        Args:
            mapping_dict: Dictionary with 'target' key and optional 'subpath'.

        Returns:
            Mapping with targets, subpaths, and copy_paths.
        """
        targets = self._normalize_targets(mapping_dict[_KEY_TARGET])
        raw_subpaths = mapping_dict.get(_KEY_SUBPATH)
        subpaths, copy_paths = self._parse_subpaths(raw_subpaths)

        return Mapping(
            targets=targets,
            subpaths=subpaths,
            copy_paths=copy_paths,
        )


class ConfigUpdater:
    """Manages subpath entries in an existing config file for the revlink workflow.

    Used by ``revlink create`` to register a newly adopted item in the config so
    that ``link sync`` and ``link check`` will manage it going forward, and by
    ``revlink restore`` to de-register the item when the symlink is dissolved.

    Only acts when the matched mapping already has a ``subpath`` list.  When
    the mapping syncs everything (no ``subpath``), the item is already covered
    and no update is required.

    Uses ``ruamel.yaml`` for round-trip editing so that comments, blank lines,
    and indentation in the original file are preserved.
    """

    def __init__(self, config_path: Path) -> None:
        """Initialise the updater for a specific config file.

        Args:
            config_path: Absolute path to the YAML configuration file to
                update.
        """
        self._config_path = config_path
        self._yaml = YAML()
        self._yaml.preserve_quotes = True

    def add_subpath_entry(
        self,
        project_name: str,
        cwd: Path,
        entry_name: str,
    ) -> bool:
        """Add *entry_name* to the subpath list of the mapping that targets *cwd*.

        Loads the raw YAML while preserving comments and formatting, locates
        the correct mapping for *project_name* and *cwd*, appends *entry_name*
        to its ``subpath`` list, and writes the file back in-place.

        Does nothing and returns ``False`` when:

        - The mapping has no ``subpath`` key (sync-all mapping — no update
          needed).
        - *entry_name* is already present in the subpath list.

        Args:
            project_name: The project key as it appears in the config file.
            cwd: The current working directory; used to identify which mapping
                to update when a project has multiple mappings.
            entry_name: The filename or directory name to add (e.g.
                ``"myfile.txt"``).

        Returns:
            ``True`` if the file was updated, ``False`` if no change was
            needed.
        """
        data = self._yaml.load(self._config_path)
        project_value = data.get(project_name)
        if project_value is None:
            return False

        changed = self._patch_value(project_value, cwd, entry_name)
        if changed:
            with self._config_path.open("w") as fh:
                self._yaml.dump(data, fh)
        return changed

    def _patch_value(self, value: str | CommentedMap | CommentedSeq, cwd: Path, entry_name: str) -> bool:
        """Mutate *value* in-place to add *entry_name* to the right subpath list.

        Args:
            value: Raw YAML value for the project (string, dict, or list).
            cwd: Target directory to match against.
            entry_name: Subpath entry to add.

        Returns:
            ``True`` if a subpath list was found and updated.
        """
        if isinstance(value, str):
            # String mapping — syncs everything, nothing to do.
            return False

        if isinstance(value, dict) and _KEY_TARGET in value:
            return self._patch_dict_mapping(value, entry_name)

        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and _KEY_TARGET in item:
                    targets = item[_KEY_TARGET]
                    if isinstance(targets, str):
                        targets = [targets]
                    if any(Path(t).resolve() == cwd for t in targets):
                        return self._patch_dict_mapping(item, entry_name)
            # List of string mappings — syncs everything, nothing to do.
            return False

        return False

    def _patch_dict_mapping(self, mapping: CommentedMap, entry_name: str) -> bool:
        """Add *entry_name* to the ``subpath`` list of *mapping* if one exists.

        Args:
            mapping: A dict-mapping node from the round-trip YAML parse.
            entry_name: Subpath entry to add.

        Returns:
            ``True`` if the subpath list was updated, ``False`` otherwise.
        """
        if _KEY_SUBPATH not in mapping:
            # No subpath key — mapping syncs everything, nothing to do.
            return False

        subpath_list = mapping[_KEY_SUBPATH]

        # Collect existing plain-string entries and path-dict entries.
        existing = {e if isinstance(e, str) else e.get("path", "") for e in subpath_list}
        if entry_name in existing:
            return False

        subpath_list.append(entry_name)
        return True

    def remove_subpath_entry(
        self,
        project_name: str,
        cwd: Path,
        entry_name: str,
    ) -> bool:
        """Remove *entry_name* from the subpath list of the mapping that targets *cwd*.

        Loads the raw YAML while preserving comments and formatting, locates
        the correct mapping for *project_name* and *cwd*, removes *entry_name*
        from its ``subpath`` list, and writes the file back in-place.

        Does nothing and returns ``False`` when:

        - The mapping has no ``subpath`` key (sync-all mapping — no update
          needed).
        - *entry_name* is not present in the subpath list.

        When the subpath list becomes empty after removal, the empty list is
        left in place — removing the ``subpath`` key entirely would change the
        mapping semantics from selective sync to sync-all.

        Args:
            project_name: The project key as it appears in the config file.
            cwd: The current working directory; used to identify which mapping
                to update when a project has multiple mappings.
            entry_name: The filename or directory name to remove (e.g.
                ``"myfile.txt"``).

        Returns:
            ``True`` if the file was updated, ``False`` if no change was
            needed.
        """
        data = self._yaml.load(self._config_path)
        project_value = data.get(project_name)
        if project_value is None:
            return False

        changed = self._unpatch_value(project_value, cwd, entry_name)
        if changed:
            with self._config_path.open("w") as fh:
                self._yaml.dump(data, fh)
        return changed

    def _unpatch_value(self, value: str | CommentedMap | CommentedSeq, cwd: Path, entry_name: str) -> bool:
        """Mutate *value* in-place to remove *entry_name* from the right subpath list.

        Args:
            value: Raw YAML value for the project (string, dict, or list).
            cwd: Target directory to match against.
            entry_name: Subpath entry to remove.

        Returns:
            ``True`` if a subpath list was found and updated.
        """
        if isinstance(value, str):
            # String mapping — syncs everything, nothing to do.
            return False

        if isinstance(value, dict) and _KEY_TARGET in value:
            return self._unpatch_dict_mapping(value, entry_name)

        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and _KEY_TARGET in item:
                    targets = item[_KEY_TARGET]
                    if isinstance(targets, str):
                        targets = [targets]
                    if any(Path(t).resolve() == cwd for t in targets):
                        return self._unpatch_dict_mapping(item, entry_name)
            # List of string mappings — syncs everything, nothing to do.
            return False

        return False

    def _unpatch_dict_mapping(self, mapping: CommentedMap, entry_name: str) -> bool:
        """Remove *entry_name* from the ``subpath`` list of *mapping* if present.

        When the subpath list becomes empty after removal, the empty list is
        left in place to preserve selective-sync semantics.

        Args:
            mapping: A dict-mapping node from the round-trip YAML parse.
            entry_name: Subpath entry to remove.

        Returns:
            ``True`` if the subpath list was updated, ``False`` otherwise.
        """
        if _KEY_SUBPATH not in mapping:
            # No subpath key — mapping syncs everything, nothing to do.
            return False

        subpath_list = mapping[_KEY_SUBPATH]

        if not subpath_list:
            # Subpath key is present but the list is empty or None — nothing to remove.
            return False

        # Find the index of the matching entry (plain string or {"path": ...} dict).
        index_to_remove = None
        for i, entry in enumerate(subpath_list):
            if isinstance(entry, str) and entry == entry_name:
                index_to_remove = i
                break
            if isinstance(entry, dict) and entry.get("path") == entry_name:
                index_to_remove = i
                break

        if index_to_remove is None:
            return False

        del subpath_list[index_to_remove]
        return True
