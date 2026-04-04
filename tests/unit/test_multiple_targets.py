"""Test that multiple targets always get sequence suffixes."""

import tempfile
from pathlib import Path

import yaml

from beyond_local_file.config import Config


def test_simple_list_multiple_targets():
    """Test that a simple list of targets creates separate configs with sequence suffixes."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # Create config with simple list of multiple targets
        config_content = {
            "my-project": [
                str(td_path / "target1"),
                str(td_path / "target2"),
            ],
        }

        config_path = td_path / "config.yml"
        config_path.write_text(yaml.dump(config_content))

        # Create directories
        (td_path / "my-project").mkdir()
        (td_path / "target1").mkdir()
        (td_path / "target2").mkdir()

        # Load config
        cfg = Config(config_path)
        projects = cfg.get_projects()

        # Should create two separate configs with sequence suffixes
        print(f"Projects: {list(projects.keys())}")
        for name, proj in projects.items():
            print(f"  {name}: {len(proj.targets)} targets -> {proj.targets}")

        # Currently this test will fail because the current implementation
        # creates a single config with multiple targets
        assert len(projects) == 2  # noqa: PLR2004
        assert "my-project#1" in projects
        assert "my-project#2" in projects


def test_single_target_no_suffix():
    """Test that a single target does NOT get a sequence suffix."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # Create config with single target
        config_content = {
            "my-project": str(td_path / "target1"),
        }

        config_path = td_path / "config.yml"
        config_path.write_text(yaml.dump(config_content))

        # Create directories
        (td_path / "my-project").mkdir()
        (td_path / "target1").mkdir()

        # Load config
        cfg = Config(config_path)
        projects = cfg.get_projects()

        # Should create a single config without suffix
        assert len(projects) == 1
        assert "my-project" in projects
        assert "my-project#1" not in projects
