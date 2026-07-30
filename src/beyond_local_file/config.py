"""Configuration management for the link CLI tool."""

from pathlib import Path
from tempfile import NamedTemporaryFile
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

        return subpaths, copy_paths or None

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
    """Round-trip-preserving writer for revlink and removal subpath updates.

    ``revlink create`` registers one adopted subpath and ``revlink restore``
    de-registers it from the invocation mapping.  ``blf remove`` stages the
    same exact-entry removal across every selected selective mapping and
    persists the result atomically.  Sync-all mappings have no ``subpath`` key
    and remain unchanged.

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
        # Prevent ruamel.yaml from line-wrapping long path values (default is 80).
        self._yaml.width = 4096

    def add_subpath_entry(
        self,
        project_name: str,
        cwd: Path,
        entry_name: str,
    ) -> bool:
        """Add *entry_name* to the subpath list of the mapping that targets *cwd*.

        Locates the correct mapping for *project_name* and *cwd*, then inserts
        *entry_name* immediately after the last existing subpath item using a
        raw text splice.  This preserves the original indentation and all other
        content in the file exactly — no re-indentation or formatting changes.

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

        insert_line = self._find_insert_line(project_value, cwd, entry_name)
        if insert_line is None:
            return False

        source_lines = self._config_path.read_text().splitlines(keepends=True)

        if insert_line < 0:
            # Empty subpath list: find the ``subpath:`` key line and replace it
            # with a block sequence containing the new entry.
            # insert_line encodes the key's 0-based line as -(line + 1).
            key_line_idx = -(insert_line + 1)
            key_line = source_lines[key_line_idx]
            key_indent = len(key_line) - len(key_line.lstrip())
            item_indent = key_indent + 2
            source_lines[key_line_idx] = " " * key_indent + "subpath:\n"
            source_lines.insert(key_line_idx + 1, " " * item_indent + f"- {entry_name}\n")
            self._config_path.write_text("".join(source_lines))
            return True

        last_item_line = source_lines[insert_line]
        indent = len(last_item_line) - len(last_item_line.lstrip())
        new_line = " " * indent + f"- {entry_name}\n"
        source_lines.insert(insert_line + 1, new_line)
        # Remove any blank lines that were between the old last item and the
        # next content — they now sit between the new item and the next
        # content, which is unexpected.  A blank line at this position only
        # arises when the original file had one as a section separator; in
        # that case the blank line belongs *after* the new item, not before
        # the next section, so we leave it.  But a trailing blank line at EOF
        # (nothing follows) must be removed to avoid an orphaned blank line.
        new_item_pos = insert_line + 1
        end = new_item_pos + 1
        while end < len(source_lines) and source_lines[end].strip() == "":
            end += 1
        # Only strip blanks when they run all the way to EOF.
        if end == len(source_lines):
            del source_lines[new_item_pos + 1 : end]
        self._config_path.write_text("".join(source_lines))
        return True

    def _find_insert_line(
        self,
        value: str | CommentedMap | CommentedSeq,
        cwd: Path,
        entry_name: str,
    ) -> int | None:
        """Return the 0-based source line of the last subpath item to insert after.

        Uses ``seq.lc.data[last_idx][0]`` (ruamel.yaml's line/column tracking)
        to locate the exact source line of the last item.  Returns ``None``
        when no insertion is needed (no subpath key, already present, or
        no matching target).

        Args:
            value: Raw YAML value for the project (string, dict, or list).
            cwd: Target directory to match against.
            entry_name: Subpath entry to add.

        Returns:
            0-based line index to insert after, or ``None`` if no change needed.
        """
        if isinstance(value, str):
            return None

        if isinstance(value, dict) and _KEY_TARGET in value:
            return self._insert_line_for_mapping(value, entry_name)

        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and _KEY_TARGET in item:
                    targets = item[_KEY_TARGET]
                    if isinstance(targets, str):
                        targets = [targets]
                    if any(Path(t).resolve() == cwd for t in targets):
                        return self._insert_line_for_mapping(item, entry_name)
            return None

        return None

    def _insert_line_for_mapping(self, mapping: CommentedMap, entry_name: str) -> int | None:
        """Return the 0-based source line of the last subpath item in *mapping*.

        Returns ``None`` when the mapping has no subpath key or *entry_name*
        is already present.

        PRECONDITION: ``mapping`` is a ``CommentedMap`` from a ruamel.yaml
        round-trip load, so ``lc`` line/column data is available.

        Args:
            mapping: A dict-mapping node from the round-trip YAML parse.
            entry_name: Subpath entry to add.

        Returns:
            0-based line index of the last subpath item, or ``None``.
        """
        if _KEY_SUBPATH not in mapping:
            return None

        subpath_list = mapping[_KEY_SUBPATH]
        if not subpath_list:
            # Empty subpath list: return the 0-based line of the subpath key
            # encoded as a negative value -(line + 1) so the caller can
            # rewrite the inline ``subpath: []`` form to a block sequence.
            key_line = mapping.lc.value(_KEY_SUBPATH)[0]
            return -(key_line + 1)
        existing = {e if isinstance(e, str) else e.get("path", "") for e in subpath_list}
        if entry_name in existing:
            return None

        last_idx = len(subpath_list) - 1
        # lc.data[i] is (line, col, ...) — 0-based line in the source file.
        return subpath_list.lc.data[last_idx][0]

    def remove_subpath_entry(
        self,
        project_name: str,
        cwd: Path,
        entry_name: str,
    ) -> bool:
        """Remove *entry_name* from the subpath list of the mapping that targets *cwd*.

        Locates the correct mapping for *project_name* and *cwd*, then deletes
        the source line(s) for *entry_name* using a raw text splice.  This
        preserves the original indentation and all other content in the file
        exactly — no re-indentation or blank-line loss.

        Does nothing and returns ``False`` when:

        - The mapping has no ``subpath`` key (sync-all mapping — no update
          needed).
        - *entry_name* is not present in the subpath list.

        When the subpath list becomes empty after removal, the block sequence
        is replaced with an inline ``subpath: []`` to preserve selective-sync
        semantics without removing the key.

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

        removal = self._find_removal_lines(project_value, cwd, entry_name)
        if removal is None:
            return False

        delete_start, delete_end, becomes_empty, key_indent, key_line_0based = removal
        source_lines = self._config_path.read_text().splitlines(keepends=True)

        if becomes_empty:
            # Replace the ``subpath:`` key line AND the sole item line(s) with
            # ``subpath: []``.  key_line_0based is the 0-based index of the
            # ``subpath:`` key line, which is always one or more lines before
            # delete_start.
            source_lines[key_line_0based:delete_end] = [" " * key_indent + "subpath: []\n"]
        else:
            del source_lines[delete_start:delete_end]

        self._config_path.write_text("".join(source_lines))
        return True

    def _find_removal_lines(
        self,
        value: str | CommentedMap | CommentedSeq,
        cwd: Path,
        entry_name: str,
    ) -> tuple[int, int, bool, int, int] | None:
        """Locate the source line range to delete for *entry_name*.

        Returns a 5-tuple ``(delete_start, delete_end, becomes_empty,
        key_indent, key_line_0based)`` where:

        - ``delete_start``: 0-based index of the first line to delete
          (inclusive).
        - ``delete_end``: 0-based index of the line after the last line to
          delete (exclusive).
        - ``becomes_empty``: ``True`` when removing this entry empties the
          subpath list; the caller should replace ``source_lines[key_line_0based
          :delete_end]`` with ``subpath: []``.
        - ``key_indent``: number of leading spaces on the ``subpath:`` key
          line; used to reconstruct ``subpath: []`` at the right depth.
        - ``key_line_0based``: 0-based line index of the ``subpath:`` key.

        Returns ``None`` when no removal is needed.

        Args:
            value: Raw YAML value for the project (string, dict, or list).
            cwd: Target directory to match against.
            entry_name: Subpath entry to remove.

        Returns:
            ``(delete_start, delete_end, becomes_empty, key_indent,
            key_line_0based)`` or ``None``.
        """
        if isinstance(value, str):
            return None

        if isinstance(value, dict) and _KEY_TARGET in value:
            return self._removal_lines_for_mapping(value, entry_name)

        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and _KEY_TARGET in item:
                    targets = item[_KEY_TARGET]
                    if isinstance(targets, str):
                        targets = [targets]
                    if any(Path(t).resolve() == cwd for t in targets):
                        return self._removal_lines_for_mapping(item, entry_name)
            return None

        return None

    def _removal_lines_for_mapping(  # noqa: PLR0912 -- scalar and sequence YAML forms need distinct source-range handling
        self,
        mapping: CommentedMap,
        entry_name: str,
    ) -> tuple[int, int, bool, int, int] | None:
        """Return removal line range for *entry_name* inside *mapping*.

        Uses ``subpath_list.lc.data[i]`` (ruamel.yaml's line/column tracking)
        to locate the exact source lines of each entry.

        For a plain string entry the range covers exactly one line.  For a
        path-dict entry (``{path: ..., copy: true}``) the range extends from
        the ``- path:`` line up to but not including the next entry's first
        line (or the next sibling key in the same mapping if this is the last
        entry).

        PRECONDITION: ``mapping`` is a ``CommentedMap`` from a ruamel.yaml
        round-trip load, so ``lc`` line/column data is available.

        Args:
            mapping: A dict-mapping node from the round-trip YAML parse.
            entry_name: Subpath entry to remove.

        Returns:
            ``(delete_start, delete_end, becomes_empty, key_indent,
            key_line_0based)`` or ``None``.
        """
        if _KEY_SUBPATH not in mapping:
            return None

        subpath_list = mapping[_KEY_SUBPATH]
        if not subpath_list:
            return None

        # A scalar subpath is a one-item selective list written inline.  Replace
        # the complete key/value line with an empty list when it matches.
        key_line_0based = mapping.lc.key(_KEY_SUBPATH)[0]
        source_lines = self._config_path.read_text().splitlines(keepends=True)
        key_line_text = source_lines[key_line_0based]
        key_indent = len(key_line_text) - len(key_line_text.lstrip())
        if isinstance(subpath_list, str):
            if subpath_list != entry_name:
                return None
            return key_line_0based, key_line_0based + 1, True, key_indent, key_line_0based

        # Find the index of the matching entry.
        index_to_remove = None
        for i, entry in enumerate(subpath_list):
            if isinstance(entry, str) and entry == entry_name:
                index_to_remove = i
                break
            if isinstance(entry, dict) and entry.get("path") == entry_name:
                index_to_remove = i
                break

        if index_to_remove is None:
            return None

        # 0-based source line of the entry to remove.
        delete_start = subpath_list.lc.data[index_to_remove][0]

        becomes_empty = len(subpath_list) == 1

        # Key indent and source position were calculated before scalar/list
        # handling so both representations preserve their original indentation.

        # Determine delete_end: the line immediately after this entry's last
        # source line.
        #
        # For a non-last entry: the next entry's lc.data gives its start line.
        # For the last entry we scan forward from delete_start + 1 to find the
        # first line whose indentation is <= the entry's indent (the ``- ``
        # prefix), which marks the start of the next sibling.  This correctly
        # handles both single-line (plain string) and multi-line (path-dict)
        # entries without needing to know the entry type upfront.
        if index_to_remove < len(subpath_list) - 1:
            delete_end = subpath_list.lc.data[index_to_remove + 1][0]
        else:
            # Last entry: scan forward to find where this entry's indented
            # block ends.  The entry line starts with ``    - `` (entry_indent
            # spaces then ``-``).  Any subsequent line with indentation <=
            # entry_indent that is non-blank belongs to an outer scope.
            entry_indent = len(source_lines[delete_start]) - len(source_lines[delete_start].lstrip())
            delete_end = delete_start + 1
            while delete_end < len(source_lines):
                line = source_lines[delete_end]
                stripped = line.lstrip()
                if not stripped:
                    # Blank line — belongs to outer scope, stop here.
                    break
                line_indent = len(line) - len(stripped)
                if line_indent <= entry_indent:
                    # Back to same or outer indent — stop here.
                    break
                delete_end += 1

        return delete_start, delete_end, becomes_empty, key_indent, key_line_0based

    def remove_subpath_entries(
        self,
        project_name: str,
        target_paths: set[Path],
        entry_name: str,
    ) -> bool:
        """Atomically remove one subpath from every selected project mapping.

        The update is staged against a single round-trip parse and persisted by
        replacing the original only after all source-level changes are ready.
        Empty selective lists remain represented as ``subpath: []``.

        Args:
            project_name: Project key containing the mappings to update.
            target_paths: Target directories identifying the selective mappings.
            entry_name: Exact relative item path to remove from each mapping.

        Returns:
            True when one or more selected mappings changed; False when no
            selected mapping contains the entry.

        Raises:
            OSError: If the single atomic configuration replacement fails.
        """
        data = self._yaml.load(self._config_path)
        project_value = data.get(project_name)
        if project_value is None:
            return False

        removals = self._find_removals_for_targets(project_value, target_paths, entry_name)
        if not removals:
            return False

        source_lines = self._config_path.read_text().splitlines(keepends=True)
        for delete_start, delete_end, becomes_empty, key_indent, key_line in sorted(removals, reverse=True):
            if becomes_empty:
                source_lines[key_line:delete_end] = [" " * key_indent + "subpath: []\n"]
            else:
                del source_lines[delete_start:delete_end]

        self._write_atomically("".join(source_lines))
        return True

    def _find_removals_for_targets(
        self,
        value: str | CommentedMap | CommentedSeq,
        target_paths: set[Path],
        entry_name: str,
    ) -> list[tuple[int, int, bool, int, int]]:
        """Collect removal locations for mappings that target one requested path.

        Args:
            value: Raw round-trip YAML value for one project.
            target_paths: Resolved target directories that participate.
            entry_name: Exact subpath entry to remove.

        Returns:
            Source line ranges for every matching selective mapping.
        """
        mappings: list[CommentedMap] = []
        if isinstance(value, dict) and _KEY_TARGET in value:
            mappings.append(value)
        elif isinstance(value, list):
            mappings.extend(item for item in value if isinstance(item, dict) and _KEY_TARGET in item)

        removals: list[tuple[int, int, bool, int, int]] = []
        for mapping in mappings:
            targets = mapping[_KEY_TARGET]
            target_values = [targets] if isinstance(targets, str) else targets
            if not any(Path(target).resolve() in target_paths for target in target_values):
                continue
            removal = self._removal_lines_for_mapping(mapping, entry_name)
            if removal is not None:
                removals.append(removal)
        return removals

    def _write_atomically(self, content: str) -> None:
        """Replace the configuration file only after a complete staged write.

        Args:
            content: Fully assembled replacement configuration text.

        Raises:
            OSError: If the temporary write or atomic replacement fails.
        """
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self._config_path.parent,
            prefix=f".{self._config_path.name}.",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        try:
            temporary_path.replace(self._config_path)
        except OSError:
            temporary_path.unlink(missing_ok=True)
            raise
