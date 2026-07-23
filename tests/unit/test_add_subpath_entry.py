"""Unit tests for ConfigUpdater.add_subpath_entry.

Covers all three config shapes and the zero-noise correctness contract:
- Shape (A): string mapping — sync-all, no subpath key
- Shape (B): dict mapping — project-name: {target: /target, subpath: [...]}
- Shape (C): list of mappings — project-name: [{target: /t1, ...}, ...]

Within a subpath list each entry is either:
  (1) a plain string  — "filename.txt"
  (2) a path-dict     — {path: "filename.txt", copy: true}

Correctness contract:
  - The new entry is inserted immediately after the last existing subpath item
    using the same leading whitespace as that item.
  - No other lines in the file are modified (zero noise).
  - Full file content is compared in every test that writes a change.
"""

from pathlib import Path

from beyond_local_file.config import ConfigUpdater

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def write_raw_config(tmp_path: Path, content: str) -> Path:
    """Write a raw YAML string to a config file and return its path."""
    config_path = tmp_path / "config.yml"
    config_path.write_text(content)
    return config_path


# ---------------------------------------------------------------------------
# Shape (A): string mapping — project-name: /target
# ---------------------------------------------------------------------------


class TestStringMapping:
    """Shape (A): project-name: /target — sync-all, no subpath key."""

    def test_string_mapping_returns_false_and_leaves_file_unchanged(self, tmp_path: Path) -> None:
        """A plain string mapping already syncs everything; no update is needed.

        ConfigUpdater must return False and not modify the file when the
        project value is a bare target path (no subpath key).
        """
        config_path = tmp_path / "config.yml"
        config_path.write_text(
            """\
my-project: /tmp/ta
"""
        )

        changed = ConfigUpdater(config_path).add_subpath_entry("my-project", Path("/tmp/ta"), "newfile.txt")

        assert changed is False
        assert config_path.read_text() == "my-project: /tmp/ta\n"


# ---------------------------------------------------------------------------
# Shape (B): dict mapping — project-name: {target: /target, subpath: [...]}
# ---------------------------------------------------------------------------


class TestDictMapping:
    """Shape (B): project-name: {target: /target, subpath: [...]}"""

    def test_appends_entry_to_existing_subpath_list(self, tmp_path: Path) -> None:
        """Appending to a single-item subpath list preserves all existing content exactly.

        Shape (B) + variant (1): plain string entries.
        ConfigUpdater must return True and write the file with the new entry
        appended using the same indentation as the existing items — no
        re-indentation or other noise introduced.
        """
        config_path = tmp_path / "config.yml"
        config_path.write_text(
            """\
my-project:
  target: /tmp/ta
  subpath:
    - existing.txt
"""
        )

        changed = ConfigUpdater(config_path).add_subpath_entry("my-project", Path("/tmp/ta"), "newfile.txt")

        assert changed is True
        assert config_path.read_text() == (
            """\
my-project:
  target: /tmp/ta
  subpath:
    - existing.txt
    - newfile.txt
"""
        )

    def test_no_subpath_key_returns_false(self, tmp_path: Path) -> None:
        """A dict mapping with no subpath key syncs everything; no update needed.

        Shape (B) without a subpath key — must return False and leave the file
        unchanged.
        """
        config_path = tmp_path / "config.yml"
        config_path.write_text(
            """\
my-project:
  target: /tmp/ta
"""
        )

        changed = ConfigUpdater(config_path).add_subpath_entry("my-project", Path("/tmp/ta"), "newfile.txt")

        assert changed is False
        assert config_path.read_text() == "my-project:\n  target: /tmp/ta\n"

    def test_does_not_duplicate_plain_string_entry(self, tmp_path: Path) -> None:
        """Adding an entry that already exists as a plain string is a no-op.

        Shape (B) + variant (1): deduplication against existing plain-string
        subpath entries. File must be left unchanged.
        """
        config_path = tmp_path / "config.yml"
        config_path.write_text(
            """\
my-project:
  target: /tmp/ta
  subpath:
    - existing.txt
"""
        )

        changed = ConfigUpdater(config_path).add_subpath_entry("my-project", Path("/tmp/ta"), "existing.txt")

        assert changed is False
        assert config_path.read_text() == (
            """\
my-project:
  target: /tmp/ta
  subpath:
    - existing.txt
"""
        )

    def test_does_not_duplicate_path_dict_entry(self, tmp_path: Path) -> None:
        """Adding an entry that already exists as a path-dict is a no-op.

        Shape (B) + variant (2): deduplication against existing path-dict
        subpath entries (e.g. ``{path: rules.md, copy: true}``).
        File must be left unchanged.
        """
        config_path = tmp_path / "config.yml"
        config_path.write_text(
            """\
my-project:
  target: /tmp/ta
  subpath:
    - path: rules.md
      copy: true
"""
        )

        changed = ConfigUpdater(config_path).add_subpath_entry("my-project", Path("/tmp/ta"), "rules.md")

        assert changed is False
        assert config_path.read_text() == (
            """\
my-project:
  target: /tmp/ta
  subpath:
    - path: rules.md
      copy: true
"""
        )

    def test_empty_inline_subpath_list_converted_to_block(self, tmp_path: Path) -> None:
        """An empty inline subpath list ``subpath: []`` gets the first entry added.

        Shape (B): ``subpath: []`` means selective sync with nothing declared.
        Adding the first entry must convert it to a block sequence using
        consistent indentation (key indent + 2 spaces).
        """
        config_path = tmp_path / "config.yml"
        config_path.write_text(
            """\
my-project:
  target: /tmp/ta
  subpath: []
"""
        )

        changed = ConfigUpdater(config_path).add_subpath_entry("my-project", Path("/tmp/ta"), "newfile.txt")

        assert changed is True
        assert config_path.read_text() == (
            """\
my-project:
  target: /tmp/ta
  subpath:
    - newfile.txt
"""
        )

    def test_preserves_4space_indent_and_strips_trailing_eof_blank(self, tmp_path: Path) -> None:
        """Appending preserves 4-space indentation and removes the trailing blank line at EOF.

        Trigger: the source ends with ``\\n\\n`` (trailing blank line).
        The new entry must use the same indentation as the existing items and
        the trailing blank line must be consumed, not reproduced.
        """
        config_path = tmp_path / "config.yml"
        config_path.write_text(
            """\
my-project:
  target: /tmp/ta
  subpath:
    - foo
    - bar

"""
        )

        ConfigUpdater(config_path).add_subpath_entry("my-project", Path("/tmp/ta"), "baz")

        assert config_path.read_text() == (
            """\
my-project:
  target: /tmp/ta
  subpath:
    - foo
    - bar
    - baz
"""
        )

    def test_preserves_blank_line_between_projects(self, tmp_path: Path) -> None:
        """Appending preserves indentation and the blank line separating two projects.

        Real config files typically have a blank line between projects.
        The new entry must land before the blank line; the blank line and all
        content below must be preserved byte-for-byte.
        """
        config_path = tmp_path / "config.yml"
        config_path.write_text(
            """\
project-a:
  target: /tmp/ta
  subpath:
    - foo
    - bar

project-b:
  target: /tmp/tb
  subpath:
    - other
"""
        )

        ConfigUpdater(config_path).add_subpath_entry("project-a", Path("/tmp/ta"), "baz")

        assert config_path.read_text() == (
            """\
project-a:
  target: /tmp/ta
  subpath:
    - foo
    - bar
    - baz

project-b:
  target: /tmp/tb
  subpath:
    - other
"""
        )


# ---------------------------------------------------------------------------
# Shape (C): list of mappings
# ---------------------------------------------------------------------------


class TestListOfMappings:
    """Shape (C): project-name: [{target: /t1, subpath: [...]}, {target: /t2}]"""

    def test_matching_target_gets_entry_appended_exactly(self, tmp_path: Path) -> None:
        """The matching dict mapping inside a list gets the new entry appended exactly.

        Shape (C): two dict mappings; only the one whose target matches cwd
        is updated. Source indentation and the unrelated mapping are preserved
        byte-for-byte.
        """
        config_path = tmp_path / "config.yml"
        t1 = tmp_path / "t1"
        t2 = tmp_path / "t2"
        config_path.write_text(
            f"""\
my-project:
  - target: {t1}
    subpath:
      - existing.txt
  - target: {t2}
    subpath:
      - other.txt
"""
        )

        changed = ConfigUpdater(config_path).add_subpath_entry("my-project", t1, "newfile.txt")

        assert changed is True
        assert config_path.read_text() == (
            f"""\
my-project:
  - target: {t1}
    subpath:
      - existing.txt
      - newfile.txt
  - target: {t2}
    subpath:
      - other.txt
"""
        )

    def test_non_matching_target_returns_false(self, tmp_path: Path) -> None:
        """When cwd does not match any target in the list, no update is made.

        File must be left unchanged.
        """
        config_path = tmp_path / "config.yml"
        t1 = tmp_path / "t1"
        unrelated = tmp_path / "unrelated"
        config_path.write_text(
            f"""\
my-project:
  - target: {t1}
    subpath:
      - existing.txt
"""
        )

        changed = ConfigUpdater(config_path).add_subpath_entry("my-project", unrelated, "newfile.txt")

        assert changed is False
        assert config_path.read_text() == (
            f"""\
my-project:
  - target: {t1}
    subpath:
      - existing.txt
"""
        )

    def test_list_of_string_mappings_returns_false(self, tmp_path: Path) -> None:
        """A list of plain string mappings syncs everything; no update needed.

        Shape (C) where all items are bare target paths (no subpath key).
        File must be left unchanged.
        """
        config_path = tmp_path / "config.yml"
        t1 = tmp_path / "t1"
        t2 = tmp_path / "t2"
        config_path.write_text(
            f"""\
my-project:
  - {t1}
  - {t2}
"""
        )

        changed = ConfigUpdater(config_path).add_subpath_entry("my-project", t1, "newfile.txt")

        assert changed is False
        assert config_path.read_text() == (
            f"""\
my-project:
  - {t1}
  - {t2}
"""
        )

    def test_matching_target_without_subpath_key_returns_false(self, tmp_path: Path) -> None:
        """A matching dict mapping in a list with no subpath key is a no-op.

        Shape (C): the matching mapping exists but syncs everything.
        File must be left unchanged.
        """
        config_path = tmp_path / "config.yml"
        t1 = tmp_path / "t1"
        config_path.write_text(
            f"""\
my-project:
  - target: {t1}
"""
        )

        changed = ConfigUpdater(config_path).add_subpath_entry("my-project", t1, "newfile.txt")

        assert changed is False
        assert config_path.read_text() == (
            f"""\
my-project:
  - target: {t1}
"""
        )

    def test_preserves_blank_line_between_list_items(self, tmp_path: Path) -> None:
        """Appending preserves indentation and the blank line between two list mappings.

        Shape (C): the new entry must not land after the blank separator; both
        the blank line and the unrelated mapping must be preserved exactly.
        """
        config_path = tmp_path / "config.yml"
        t1 = tmp_path / "t1"
        t2 = tmp_path / "t2"
        config_path.write_text(
            f"""\
my-project:
  - target: {t1}
    subpath:
      - foo
      - bar

  - target: {t2}
    subpath:
      - other
"""
        )

        ConfigUpdater(config_path).add_subpath_entry("my-project", t1, "baz")

        assert config_path.read_text() == (
            f"""\
my-project:
  - target: {t1}
    subpath:
      - foo
      - bar
      - baz

  - target: {t2}
    subpath:
      - other
"""
        )


# ---------------------------------------------------------------------------
# Unknown project
# ---------------------------------------------------------------------------


class TestUnknownProject:
    """add_subpath_entry with a project name not present in the config."""

    def test_unknown_project_returns_false(self, tmp_path: Path) -> None:
        """Requesting an update for a project that doesn't exist returns False.

        ConfigUpdater must not raise and must not modify the file.
        """
        config_path = tmp_path / "config.yml"
        config_path.write_text("my-project: /tmp/ta\n")

        changed = ConfigUpdater(config_path).add_subpath_entry("does-not-exist", Path("/tmp/ta"), "newfile.txt")

        assert changed is False
        assert config_path.read_text() == "my-project: /tmp/ta\n"
