"""Test that synthetic names with suffixes don't break project path resolution."""

import tempfile
from pathlib import Path

import yaml

from beyond_local_file.config import Config


def test_mixed_format_project_path_resolution():
    """Test that synthetic names (#1, #2) don't corrupt project path resolution.
    
    This was a bug where synthetic names like "project#1" were passed to
    _resolve_project_path(), causing it to look for a directory named "project#1"
    instead of "project".
    """
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # Create config with mixed format (string + dict)
        config_content = {
            "my-project": [
                str(td_path / "target1"),  # Simple string
                {
                    "target": str(td_path / "target2"),  # Dict with subpath
                    "subpath": ["local-file/tasks"],
                },
            ],
        }

        config_path = td_path / "config.yml"
        config_path.write_text(yaml.dump(config_content))

        # Create project directory (without #1 or #2 suffix!)
        (td_path / "my-project").mkdir()
        (td_path / "target1").mkdir()
        (td_path / "target2").mkdir()

        # Load config
        cfg = Config(config_path)
        projects = cfg.get_projects()

        # Should create two configs with suffixes
        assert len(projects) == 2  # noqa: PLR2004
        assert "my-project#1" in projects
        assert "my-project#2" in projects

        # CRITICAL: Both should resolve to the same project directory (without suffix)
        expected_project_path = (td_path / "my-project").resolve()
        assert projects["my-project#1"].project_path == expected_project_path
        assert projects["my-project#2"].project_path == expected_project_path

        # Verify the project path exists (it should!)
        assert projects["my-project#1"].project_path.exists()
        assert projects["my-project#2"].project_path.exists()


def test_multiple_targets_project_path_resolution():
    """Test that splitting by targets doesn't corrupt project path resolution."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # Create config with multiple targets (simple list)
        config_content = {
            "another-project": [
                str(td_path / "target1"),
                str(td_path / "target2"),
            ],
        }

        config_path = td_path / "config.yml"
        config_path.write_text(yaml.dump(config_content))

        # Create project directory (without #1 or #2 suffix!)
        (td_path / "another-project").mkdir()
        (td_path / "target1").mkdir()
        (td_path / "target2").mkdir()

        # Load config
        cfg = Config(config_path)
        projects = cfg.get_projects()

        # Should create two configs with suffixes
        assert len(projects) == 2  # noqa: PLR2004
        assert "another-project#1" in projects
        assert "another-project#2" in projects

        # CRITICAL: Both should resolve to the same project directory (without suffix)
        expected_project_path = (td_path / "another-project").resolve()
        assert projects["another-project#1"].project_path == expected_project_path
        assert projects["another-project#2"].project_path == expected_project_path

        # Verify the project path exists
        assert projects["another-project#1"].project_path.exists()
        assert projects["another-project#2"].project_path.exists()
