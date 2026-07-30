"""Tests for ConfigUpdater's atomic multi-mapping removal seam."""

from pathlib import Path
from unittest.mock import patch

import pytest

from beyond_local_file.config import Config, ConfigUpdater


def test_batch_removal_updates_all_selected_mappings_with_one_replace(tmp_path: Path) -> None:
    """One atomic write removes matching entries from every selected mapping."""
    first_target = tmp_path / "first"
    second_target = tmp_path / "second"
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"""# preserved header
managed:
  - target: {first_target}
    subpath:
      - keep.txt
      - item.txt

  - target: {second_target}
    subpath:
      - path: item.txt
        copy: true
"""
    )
    original_replace = Path.replace

    def replace_once(source: Path, destination: Path) -> Path:
        """Delegate the atomic replacement while recording its invocation."""
        return original_replace(source, destination)

    with patch.object(Path, "replace", autospec=True, side_effect=replace_once) as replace:
        changed = ConfigUpdater(config_path).remove_subpath_entries(
            "managed", {first_target, second_target}, "item.txt"
        )

    assert changed is True
    assert replace.call_count == 1
    assert config_path.read_text() == (
        f"""# preserved header
managed:
  - target: {first_target}
    subpath:
      - keep.txt

  - target: {second_target}
    subpath: []
"""
    )


def test_batch_removal_preserves_original_config_when_atomic_replace_fails(tmp_path: Path) -> None:
    """A failed staged replacement leaves the original configuration unchanged."""
    target = tmp_path / "target"
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"managed:\n  target: {target}\n  subpath:\n    - item.txt\n")
    original_content = config_path.read_bytes()

    with (
        patch.object(Path, "replace", autospec=True, side_effect=OSError("disk failure")),
        pytest.raises(OSError, match="disk failure"),
    ):
        ConfigUpdater(config_path).remove_subpath_entries("managed", {target}, "item.txt")

    assert config_path.read_bytes() == original_content


def test_batch_removal_preserves_empty_selective_mapping_after_reload(tmp_path: Path) -> None:
    """An emptied subpath list remains selective when the config is loaded again."""
    target = tmp_path / "target"
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"managed:\n  target: {target}\n  subpath:\n    - item.txt\n")

    changed = ConfigUpdater(config_path).remove_subpath_entries("managed", {target}, "item.txt")

    assert changed is True
    mapping = Config(config_path).get_config_projects()["managed"].mappings[0]
    assert mapping.subpaths == []


def test_batch_removal_converts_scalar_selective_subpath_to_empty_list(tmp_path: Path) -> None:
    """A scalar selective subpath is removable without changing mapping semantics."""
    target = tmp_path / "target"
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"managed:\n  target: {target}\n  subpath: item.txt\n")

    changed = ConfigUpdater(config_path).remove_subpath_entries("managed", {target}, "item.txt")

    assert changed is True
    assert config_path.read_text() == f"managed:\n  target: {target}\n  subpath: []\n"
