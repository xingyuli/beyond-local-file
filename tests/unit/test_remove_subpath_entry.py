"""Unit tests for ConfigUpdater.remove_subpath_entry.

Covers:
- Removes plain string entry when present (full-content assertion)
- Removes {"path": entry_name, ...} dict entry when present
- Returns False when entry is absent
- Returns False when mapping has no subpath key
- Leaves empty list in place when last entry is removed
- Zero-noise guarantee: indentation and blank lines preserved byte-for-byte

Requirements: 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
"""

from pathlib import Path

from ruamel.yaml import YAML

from beyond_local_file.config import ConfigUpdater

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_raw_config(tmp_path: Path, content: str) -> Path:
    """Write a raw YAML string to a config file and return its path.

    Used instead of yaml.dump() so that ruamel.yaml round-trip behaviour
    (comments, indentation) is exercised with realistic input.

    Args:
        tmp_path: Temporary directory provided by pytest.
        content: Raw YAML string to write.

    Returns:
        Path to the written config file.
    """
    config_path = tmp_path / "config.yml"
    config_path.write_text(content)
    return config_path


# ---------------------------------------------------------------------------
# Shape (B): dict mapping — project-name: {target: /target, subpath: [...]}
# ---------------------------------------------------------------------------


class TestRemovePlainStringEntry:
    """Removing a plain string entry from a subpath list.

    Requirements: 6.4
    """

    def test_removes_plain_string_entry_and_returns_true(self, tmp_path: Path) -> None:
        """Removing a present plain string entry returns True and updates the file.

        Requirements: 6.4
        """
        target = tmp_path / "target"
        content = f"my-project:\n  target: {target}\n  subpath:\n    - keep.txt\n    - remove.txt\n"
        config_path = write_raw_config(tmp_path, content)

        changed = ConfigUpdater(config_path).remove_subpath_entry("my-project", target.resolve(), "remove.txt")

        assert changed is True
        updated = config_path.read_text()
        assert "remove.txt" not in updated
        assert "keep.txt" in updated

    def test_removes_only_the_matching_entry(self, tmp_path: Path) -> None:
        """Only the targeted entry is removed; other entries are preserved.

        Requirements: 6.4
        """
        target = tmp_path / "target"
        content = f"my-project:\n  target: {target}\n  subpath:\n    - alpha.txt\n    - beta.txt\n    - gamma.txt\n"
        config_path = write_raw_config(tmp_path, content)

        ConfigUpdater(config_path).remove_subpath_entry("my-project", target.resolve(), "beta.txt")

        updated = config_path.read_text()
        assert "alpha.txt" in updated
        assert "beta.txt" not in updated
        assert "gamma.txt" in updated


class TestRemoveDictEntry:
    """Removing a {"path": entry_name, ...} dict entry from a subpath list.

    Requirements: 6.5
    """

    def test_removes_path_dict_entry_and_returns_true(self, tmp_path: Path) -> None:
        """Removing a present path-dict entry returns True and updates the file.

        Requirements: 6.5
        """
        target = tmp_path / "target"
        content = (
            f"my-project:\n  target: {target}\n  subpath:\n    - keep.txt\n    - path: rules.md\n      copy: true\n"
        )
        config_path = write_raw_config(tmp_path, content)

        changed = ConfigUpdater(config_path).remove_subpath_entry("my-project", target.resolve(), "rules.md")

        assert changed is True
        updated = config_path.read_text()
        assert "rules.md" not in updated
        assert "keep.txt" in updated

    def test_removes_path_dict_without_extra_keys(self, tmp_path: Path) -> None:
        """A path-dict with only the path key is also matched and removed.

        Requirements: 6.5
        """
        target = tmp_path / "target"
        content = f"my-project:\n  target: {target}\n  subpath:\n    - path: hooks\n    - plain.txt\n"
        config_path = write_raw_config(tmp_path, content)

        changed = ConfigUpdater(config_path).remove_subpath_entry("my-project", target.resolve(), "hooks")

        assert changed is True
        updated = config_path.read_text()
        assert "hooks" not in updated
        assert "plain.txt" in updated


class TestEntryAbsent:
    """Returns False when the entry is not present in the subpath list.

    Requirements: 6.3
    """

    def test_returns_false_when_entry_not_in_subpath_list(self, tmp_path: Path) -> None:
        """Attempting to remove an absent entry returns False without modifying the file.

        Requirements: 6.3
        """
        target = tmp_path / "target"
        content = f"my-project:\n  target: {target}\n  subpath:\n    - existing.txt\n"
        config_path = write_raw_config(tmp_path, content)
        original = config_path.read_text()

        changed = ConfigUpdater(config_path).remove_subpath_entry("my-project", target.resolve(), "absent.txt")

        assert changed is False
        assert config_path.read_text() == original

    def test_returns_false_for_empty_subpath_list(self, tmp_path: Path) -> None:
        """Attempting to remove from an already-empty subpath list returns False.

        Requirements: 6.3
        """
        target = tmp_path / "target"
        content = f"my-project:\n  target: {target}\n  subpath: []\n"
        config_path = write_raw_config(tmp_path, content)
        original = config_path.read_text()

        changed = ConfigUpdater(config_path).remove_subpath_entry("my-project", target.resolve(), "anything.txt")

        assert changed is False
        assert config_path.read_text() == original


class TestNoSubpathKey:
    """Returns False when the mapping has no subpath key.

    Requirements: 6.2
    """

    def test_dict_mapping_without_subpath_key_returns_false(self, tmp_path: Path) -> None:
        """A dict mapping with no subpath key is a sync-all mapping; returns False.

        Requirements: 6.2
        """
        target = tmp_path / "target"
        content = f"my-project:\n  target: {target}\n"
        config_path = write_raw_config(tmp_path, content)
        original = config_path.read_text()

        changed = ConfigUpdater(config_path).remove_subpath_entry("my-project", target.resolve(), "anything.txt")

        assert changed is False
        assert config_path.read_text() == original

    def test_string_mapping_returns_false(self, tmp_path: Path) -> None:
        """A plain string mapping (sync-all) returns False without modifying the file.

        Requirements: 6.2
        """
        target = tmp_path / "target"
        content = f"my-project: {target}\n"
        config_path = write_raw_config(tmp_path, content)
        original = config_path.read_text()

        changed = ConfigUpdater(config_path).remove_subpath_entry("my-project", target.resolve(), "anything.txt")

        assert changed is False
        assert config_path.read_text() == original


class TestEmptyListPreserved:
    """Leaves an empty subpath list in place when the last entry is removed.

    Requirements: 6.6
    """

    def test_empty_list_left_in_place_after_last_entry_removed(self, tmp_path: Path) -> None:
        """Removing the last entry leaves an empty subpath list, not a missing key.

        Requirements: 6.6
        """
        target = tmp_path / "target"
        content = f"my-project:\n  target: {target}\n  subpath:\n    - only.txt\n"
        config_path = write_raw_config(tmp_path, content)

        changed = ConfigUpdater(config_path).remove_subpath_entry("my-project", target.resolve(), "only.txt")

        assert changed is True
        updated = config_path.read_text()
        assert "only.txt" not in updated
        # The subpath key must still be present (empty list, not removed)
        assert "subpath" in updated

    def test_subpath_key_not_removed_when_list_becomes_empty(self, tmp_path: Path) -> None:
        """The subpath key is preserved even when the list is emptied.

        Removing the subpath key entirely would change the mapping semantics
        from selective sync to sync-all, which must not happen.

        Requirements: 6.6
        """
        target = tmp_path / "target"
        content = f"my-project:\n  target: {target}\n  subpath:\n    - sole-entry.txt\n"
        config_path = write_raw_config(tmp_path, content)

        ConfigUpdater(config_path).remove_subpath_entry("my-project", target.resolve(), "sole-entry.txt")

        yaml = YAML()
        data = yaml.load(config_path)
        assert "subpath" in data["my-project"], "subpath key must not be removed"
        assert data["my-project"]["subpath"] == [] or list(data["my-project"]["subpath"]) == []


# ---------------------------------------------------------------------------
# YAML comment and formatting preservation (round-trip)
# ---------------------------------------------------------------------------


class TestYamlRoundTrip:
    """YAML comments, blank lines, and indentation are preserved after removal.

    Requirements: 6.7
    """

    def test_inline_comments_preserved_after_removal(self, tmp_path: Path) -> None:
        """Inline YAML comments survive a remove_subpath_entry round-trip.

        Requirements: 6.7
        """
        target = tmp_path / "target"
        content = (
            f"# Top-level comment\n"
            f"my-project:\n"
            f"  target: {target}  # target comment\n"
            f"  subpath:\n"
            f"    - keep.txt  # keep this one\n"
            f"    - remove.txt\n"
        )
        config_path = write_raw_config(tmp_path, content)

        ConfigUpdater(config_path).remove_subpath_entry("my-project", target.resolve(), "remove.txt")

        updated = config_path.read_text()
        assert "# Top-level comment" in updated
        assert "# target comment" in updated
        assert "# keep this one" in updated
        assert "remove.txt" not in updated

    def test_block_comments_preserved_after_removal(self, tmp_path: Path) -> None:
        """Block comments above keys survive a remove_subpath_entry round-trip.

        Requirements: 6.7
        """
        target = tmp_path / "target"
        content = (
            f"my-project:\n  target: {target}\n  # selective sync list\n  subpath:\n    - alpha.txt\n    - beta.txt\n"
        )
        config_path = write_raw_config(tmp_path, content)

        ConfigUpdater(config_path).remove_subpath_entry("my-project", target.resolve(), "beta.txt")

        updated = config_path.read_text()
        assert "# selective sync list" in updated
        assert "alpha.txt" in updated
        assert "beta.txt" not in updated


# ---------------------------------------------------------------------------
# Shape (C): list of mappings
# ---------------------------------------------------------------------------


class TestRemoveFromListOfMappings:
    """remove_subpath_entry with a list-of-mappings project value.

    Requirements: 6.4, 6.5
    """

    def test_removes_entry_from_matching_mapping_in_list(self, tmp_path: Path) -> None:
        """Only the mapping whose target matches cwd is updated.

        Requirements: 6.4
        """
        t1 = tmp_path / "target1"
        t2 = tmp_path / "target2"
        content = (
            f"my-project:\n"
            f"  - target: {t1}\n"
            f"    subpath:\n"
            f"      - remove.txt\n"
            f"      - keep.txt\n"
            f"  - target: {t2}\n"
            f"    subpath:\n"
            f"      - other.txt\n"
        )
        config_path = write_raw_config(tmp_path, content)

        changed = ConfigUpdater(config_path).remove_subpath_entry("my-project", t1.resolve(), "remove.txt")

        assert changed is True
        updated = config_path.read_text()
        assert "remove.txt" not in updated
        assert "keep.txt" in updated
        assert "other.txt" in updated  # unrelated mapping untouched

    def test_non_matching_target_in_list_returns_false(self, tmp_path: Path) -> None:
        """When cwd does not match any target in the list, returns False.

        Requirements: 6.3
        """
        t1 = tmp_path / "target1"
        unrelated = tmp_path / "unrelated"
        content = f"my-project:\n  - target: {t1}\n    subpath:\n      - existing.txt\n"
        config_path = write_raw_config(tmp_path, content)
        original = config_path.read_text()

        changed = ConfigUpdater(config_path).remove_subpath_entry("my-project", unrelated.resolve(), "existing.txt")

        assert changed is False
        assert config_path.read_text() == original

    def test_list_matching_target_without_subpath_key_returns_false(self, tmp_path: Path) -> None:
        """A matching dict mapping in a list with no subpath key returns False.

        Requirements: 6.2
        """
        t1 = tmp_path / "target1"
        content = f"my-project:\n  - target: {t1}\n"
        config_path = write_raw_config(tmp_path, content)
        original = config_path.read_text()

        changed = ConfigUpdater(config_path).remove_subpath_entry("my-project", t1.resolve(), "anything.txt")

        assert changed is False
        assert config_path.read_text() == original


# ---------------------------------------------------------------------------
# Unknown project
# ---------------------------------------------------------------------------


class TestUnknownProject:
    """remove_subpath_entry with a project name not present in the config."""

    def test_unknown_project_returns_false_without_modifying_file(self, tmp_path: Path) -> None:
        """Requesting removal for a non-existent project returns False.

        ConfigUpdater must not raise and must not modify the file.
        """
        target = tmp_path / "target"
        content = f"my-project: {target}\n"
        config_path = write_raw_config(tmp_path, content)
        original = config_path.read_text()

        changed = ConfigUpdater(config_path).remove_subpath_entry("does-not-exist", target.resolve(), "file.txt")

        assert changed is False
        assert config_path.read_text() == original


# ---------------------------------------------------------------------------
# Zero-noise guarantee
#
# These tests use full file-content comparison (same style as add_subpath_entry
# tests in test_config.py) to verify that remove_subpath_entry is byte-for-byte
# identical outside the deleted line — no re-indentation, no blank-line loss.
# ---------------------------------------------------------------------------


class TestZeroNoise:
    """remove_subpath_entry must not alter any line except the one deleted.

    Full file content is compared in every test — no substring checks.
    """

    def test_removes_middle_entry_preserves_4space_indent_and_surrounding_content(self, tmp_path: Path) -> None:
        """Removing a middle entry preserves 4-space indentation and all other lines.

        The file uses 4-space indentation for subpath items.  After removal
        every remaining line must be byte-for-byte identical to the original.
        """
        config_path = tmp_path / "config.yml"
        config_path.write_text(
            """\
my-project:
  target: /tmp/ta
  subpath:
    - alpha.txt
    - beta.txt
    - gamma.txt
"""
        )

        ConfigUpdater(config_path).remove_subpath_entry("my-project", Path("/tmp/ta"), "beta.txt")

        assert config_path.read_text() == (
            """\
my-project:
  target: /tmp/ta
  subpath:
    - alpha.txt
    - gamma.txt
"""
        )

    def test_removes_entry_preserves_blank_line_between_projects(self, tmp_path: Path) -> None:
        """Removing an entry preserves the blank line separating two projects.

        Reproduces the noise observed in the wild: ruamel.yaml dump strips
        the blank line between projects.  The blank line must survive.
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

        ConfigUpdater(config_path).remove_subpath_entry("project-a", Path("/tmp/ta"), "bar")

        assert config_path.read_text() == (
            """\
project-a:
  target: /tmp/ta
  subpath:
    - foo

project-b:
  target: /tmp/tb
  subpath:
    - other
"""
        )

    def test_removes_last_entry_and_leaves_empty_inline_list(self, tmp_path: Path) -> None:
        """Removing the sole entry in a 4-space indented list leaves ``subpath: []``.

        The block sequence is collapsed back to an inline empty list so the
        mapping is still in selective-sync mode.  No re-indentation of
        surrounding keys.
        """
        config_path = tmp_path / "config.yml"
        config_path.write_text(
            """\
my-project:
  target: /tmp/ta
  subpath:
    - only.txt
"""
        )

        ConfigUpdater(config_path).remove_subpath_entry("my-project", Path("/tmp/ta"), "only.txt")

        assert config_path.read_text() == (
            """\
my-project:
  target: /tmp/ta
  subpath: []
"""
        )

    def test_removes_last_entry_with_blank_line_after_preserves_blank_line(self, tmp_path: Path) -> None:
        """Removing the sole entry when a blank line follows preserves that blank line.

        The blank line is a project separator and must not be consumed.
        """
        config_path = tmp_path / "config.yml"
        config_path.write_text(
            """\
project-a:
  target: /tmp/ta
  subpath:
    - only.txt

project-b:
  target: /tmp/tb
"""
        )

        ConfigUpdater(config_path).remove_subpath_entry("project-a", Path("/tmp/ta"), "only.txt")

        assert config_path.read_text() == (
            """\
project-a:
  target: /tmp/ta
  subpath: []

project-b:
  target: /tmp/tb
"""
        )

    def test_removes_path_dict_entry_full_content(self, tmp_path: Path) -> None:
        """Removing a path-dict entry leaves the file byte-for-byte correct.

        Shape (B) + variant (2): ``{path: rules.md, copy: true}`` spans two
        lines in the YAML source.  Both lines must be deleted; all other lines
        must be preserved with their original indentation.
        """
        config_path = tmp_path / "config.yml"
        config_path.write_text(
            """\
my-project:
  target: /tmp/ta
  subpath:
    - keep.txt
    - path: rules.md
      copy: true
"""
        )

        ConfigUpdater(config_path).remove_subpath_entry("my-project", Path("/tmp/ta"), "rules.md")

        assert config_path.read_text() == (
            """\
my-project:
  target: /tmp/ta
  subpath:
    - keep.txt
"""
        )

    def test_shape_c_removes_entry_preserves_blank_line_between_list_items(self, tmp_path: Path) -> None:
        """Shape (C): removing an entry in the matching mapping preserves the blank separator.

        The unrelated mapping and the blank line between the two list items
        must be preserved byte-for-byte.
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

        ConfigUpdater(config_path).remove_subpath_entry("my-project", t1, "bar")

        assert config_path.read_text() == (
            f"""\
my-project:
  - target: {t1}
    subpath:
      - foo

  - target: {t2}
    subpath:
      - other
"""
        )
