"""Unit tests for mixed configuration format support.

Tests verify that configurations can mix simple string targets with
selective subpath targets for a single source.
"""

import tempfile
from pathlib import Path

import yaml

from beyond_local_file.config import Config


def test_mixed_format_basic():
    """Test basic mixed format with string and dict targets.

    Verifies that a single source can have both:
    - Simple string targets (sync everything)
    - Dict targets with subpath (sync only specific items)
    """
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # Create config with mixed format
        config_content = {
            "my-project": [
                str(td_path / "target1"),  # Simple string - sync everything
                {
                    "target": str(td_path / "target2"),  # Dict with subpath
                    "subpath": [".kiro/hooks", ".vscode"],
                },
            ],
        }

        config_path = td_path / "config.yml"
        config_path.write_text(yaml.dump(config_content))

        # Create project directory
        (td_path / "my-project").mkdir()
        (td_path / "target1").mkdir()
        (td_path / "target2").mkdir()

        # Load config
        cfg = Config(config_path)
        projects = cfg.get_projects()

        # Should create two separate ProjectConfiguration objects
        assert len(projects) == 2  # noqa: PLR2004 - test expects 2 configs

        # First config should be for the dict target with subpaths
        assert "my-project" in projects
        config1 = projects["my-project"]
        assert len(config1.targets) == 1
        assert config1.targets[0] == (td_path / "target2").resolve()
        assert config1.subpaths == [".kiro/hooks", ".vscode"]

        # Second config should be for the simple string target
        assert "my-project#1" in projects
        config2 = projects["my-project#1"]
        assert len(config2.targets) == 1
        assert config2.targets[0] == (td_path / "target1").resolve()
        assert config2.subpaths is None


def test_mixed_format_multiple_strings():
    """Test mixed format with multiple string targets and one dict target."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # Create config with multiple simple targets and one dict target
        config_content = {
            "project-a": [
                str(td_path / "target1"),
                str(td_path / "target2"),
                {
                    "target": str(td_path / "target3"),
                    "subpath": ["local-file/tasks/releases"],
                },
            ],
        }

        config_path = td_path / "config.yml"
        config_path.write_text(yaml.dump(config_content))

        # Create directories
        (td_path / "project-a").mkdir()
        (td_path / "target1").mkdir()
        (td_path / "target2").mkdir()
        (td_path / "target3").mkdir()

        # Load config
        cfg = Config(config_path)
        projects = cfg.get_projects()

        # Should create two configs
        assert len(projects) == 2  # noqa: PLR2004 - test expects 2 configs

        # First config for dict target
        assert "project-a" in projects
        config1 = projects["project-a"]
        assert len(config1.targets) == 1
        assert config1.subpaths == ["local-file/tasks/releases"]

        # Second config for simple string targets (combined)
        assert "project-a#1" in projects
        config2 = projects["project-a#1"]
        assert len(config2.targets) == 2  # noqa: PLR2004 - test expects 2 targets
        assert config2.subpaths is None


def test_mixed_format_multiple_dicts():
    """Test mixed format with multiple dict targets and string targets."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # Create config with multiple dict targets and string targets
        config_content = {
            "beyond-local-file": [
                str(td_path / "target1"),
                {
                    "target": str(td_path / "target2"),
                    "subpath": ["local-file/tasks/releases"],
                },
                {
                    "target": str(td_path / "target3"),
                    "subpath": [".kiro/hooks"],
                },
            ],
        }

        config_path = td_path / "config.yml"
        config_path.write_text(yaml.dump(config_content))

        # Create directories
        (td_path / "beyond-local-file").mkdir()
        (td_path / "target1").mkdir()
        (td_path / "target2").mkdir()
        (td_path / "target3").mkdir()

        # Load config
        cfg = Config(config_path)
        projects = cfg.get_projects()

        # Should create three configs
        assert len(projects) == 3  # noqa: PLR2004 - test expects 3 configs

        # First dict target
        assert "beyond-local-file" in projects
        config1 = projects["beyond-local-file"]
        assert config1.subpaths == ["local-file/tasks/releases"]

        # Second dict target
        assert "beyond-local-file#1" in projects
        config2 = projects["beyond-local-file#1"]
        assert config2.subpaths == [".kiro/hooks"]

        # String target
        assert "beyond-local-file#2" in projects
        config3 = projects["beyond-local-file#2"]
        assert config3.subpaths is None


def test_mixed_format_with_copy_strategy():
    """Test mixed format with copy strategy in dict targets."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # Create config with copy strategy
        config_content = {
            "my-app": [
                str(td_path / "target1"),
                {
                    "target": str(td_path / "target2"),
                    "subpath": [
                        ".kiro/hooks",
                        {"path": ".kiro/steering/rules.md", "copy": True},
                    ],
                },
            ],
        }

        config_path = td_path / "config.yml"
        config_path.write_text(yaml.dump(config_content))

        # Create directories
        (td_path / "my-app").mkdir()
        (td_path / "target1").mkdir()
        (td_path / "target2").mkdir()

        # Load config
        cfg = Config(config_path)
        projects = cfg.get_projects()

        # Should create two configs
        assert len(projects) == 2  # noqa: PLR2004 - test expects 2 configs

        # Dict target with copy strategy
        assert "my-app" in projects
        config1 = projects["my-app"]
        assert config1.subpaths == [".kiro/hooks", ".kiro/steering/rules.md"]
        assert config1.copy_paths == {".kiro/steering/rules.md"}

        # String target
        assert "my-app#1" in projects
        config2 = projects["my-app#1"]
        assert config2.subpaths is None
        assert config2.copy_paths is None


def test_non_mixed_formats_unchanged():
    """Test that non-mixed formats still work as before."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # Test simple string format
        config1 = {"project1": str(td_path / "target1")}
        config_path1 = td_path / "config1.yml"
        config_path1.write_text(yaml.dump(config1))
        (td_path / "project1").mkdir()
        (td_path / "target1").mkdir()

        cfg1 = Config(config_path1)
        projects1 = cfg1.get_projects()
        assert len(projects1) == 1
        assert "project1" in projects1

        # Test simple list format (all strings)
        config2 = {"project2": [str(td_path / "target2"), str(td_path / "target3")]}
        config_path2 = td_path / "config2.yml"
        config_path2.write_text(yaml.dump(config2))
        (td_path / "project2").mkdir()
        (td_path / "target2").mkdir()
        (td_path / "target3").mkdir()

        cfg2 = Config(config_path2)
        projects2 = cfg2.get_projects()
        assert len(projects2) == 1
        assert "project2" in projects2
        assert len(projects2["project2"].targets) == 2  # noqa: PLR2004 - test expects 2 targets

        # Test full dict format
        config3 = {
            "project3": {
                "target": str(td_path / "target4"),
                "subpath": [".kiro/hooks"],
            },
        }
        config_path3 = td_path / "config3.yml"
        config_path3.write_text(yaml.dump(config3))
        (td_path / "project3").mkdir()
        (td_path / "target4").mkdir()

        cfg3 = Config(config_path3)
        projects3 = cfg3.get_projects()
        assert len(projects3) == 1
        assert "project3" in projects3
        assert projects3["project3"].subpaths == [".kiro/hooks"]


def test_mixed_format_project_name_filter():
    """Test that project name filtering works with mixed format."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # Create config with mixed format
        config_content = {
            "project-a": [
                str(td_path / "target1"),
                {
                    "target": str(td_path / "target2"),
                    "subpath": [".kiro/hooks"],
                },
            ],
            "project-b": str(td_path / "target3"),
        }

        config_path = td_path / "config.yml"
        config_path.write_text(yaml.dump(config_content))

        # Create directories
        (td_path / "project-a").mkdir()
        (td_path / "project-b").mkdir()
        (td_path / "target1").mkdir()
        (td_path / "target2").mkdir()
        (td_path / "target3").mkdir()

        # Load config with project name filter
        cfg = Config(config_path)
        projects = cfg.get_projects(project_name="project-a")

        # Should only return configs for project-a
        assert len(projects) == 2  # noqa: PLR2004 - test expects 2 configs for project-a
        assert "project-a" in projects
        assert "project-a#1" in projects
        assert "project-b" not in projects
