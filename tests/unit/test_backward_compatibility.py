"""Unit tests for backward compatibility.

Tests verify that the refactored tool maintains backward compatibility with
existing configurations, command syntax, output format, and symlink behavior.
"""

import tempfile
from pathlib import Path

import yaml
from click.testing import CliRunner

from beyond_local_file.cli import cli
from beyond_local_file.config import Config
from beyond_local_file.models import Project
from beyond_local_file.symlink_manager import SymlinkManager


def test_existing_config_files_work():
    """Test that existing config files work without modification.

    This test verifies that config files in the existing YAML format
    continue to work correctly with the refactored tool.
    """
    runner = CliRunner()

    with runner.isolated_filesystem() as td:
        td_path = Path(td)

        # Create a config file in the existing format
        # Format: project-name: [list of target paths] or project-name: single-path
        config_content = {
            "project-a": [str(td_path / "target1"), str(td_path / "target2")],
            "project-b": str(td_path / "target3"),
        }

        config_path = td_path / "config.yml"
        config_path.write_text(yaml.dump(config_content))

        # Create project directories with test files
        project_a = td_path / "project-a"
        project_a.mkdir()
        (project_a / "file1.txt").write_text("content1")

        project_b = td_path / "project-b"
        project_b.mkdir()
        (project_b / "file2.txt").write_text("content2")

        # Create target directories
        (td_path / "target1").mkdir()
        (td_path / "target2").mkdir()
        (td_path / "target3").mkdir()

        # Load config and verify it works
        cfg = Config(config_path)
        projects = cfg.get_projects()

        # Verify projects are loaded with sequence suffixes for multiple targets
        # project-a has 2 targets, so it gets split into project-a#1 and project-a#2
        assert "project-a#1" in projects
        assert "project-a#2" in projects
        # project-b has 1 target, so it keeps the original name
        assert "project-b" in projects

        # Verify each project-a config has one target
        assert len(projects["project-a#1"].targets) == 1
        assert len(projects["project-a#2"].targets) == 1

        # Verify project-b has one target
        assert len(projects["project-b"].targets) == 1

        # Verify paths are resolved correctly
        assert projects["project-a#1"].project_path == (td_path / "project-a").resolve()
        assert projects["project-a#2"].project_path == (td_path / "project-a").resolve()
        assert projects["project-b"].project_path == (td_path / "project-b").resolve()


def test_same_output_format():
    """Test that the tool produces the same output format as before.

    This test verifies that the CLI output format remains consistent
    with the previous version, ensuring users see familiar messages.
    """
    runner = CliRunner()

    with runner.isolated_filesystem() as td:
        td_path = Path(td)

        # Create a simple project and target
        project_dir = td_path / "test-project"
        project_dir.mkdir()
        (project_dir / "test-file.txt").write_text("test content")

        target_dir = td_path / "target"
        target_dir.mkdir()

        # Create config file
        config_path = td_path / "config.yml"
        config_path.write_text(f"test-project: {target_dir}\n")

        # Run check command in verbose mode and verify output format
        result = runner.invoke(cli, ["symlink", "check", "--format", "verbose"])

        # Verify expected output elements
        assert result.exit_code == 0
        assert "Processing test-project" in result.output
        assert "target" in result.output.lower()

        # The output should mention symlink status
        assert "symlink" in result.output.lower() or "missing" in result.output.lower()


def test_same_symlink_behavior():
    """Test that symlink creation and checking behavior remains the same.

    This test verifies that the tool creates symlinks in the same way
    as before, with the same behavior for existing symlinks, missing
    symlinks, and git exclude file management.
    """
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # Create a project with multiple items
        project_dir = td_path / "test-project"
        project_dir.mkdir()
        (project_dir / "file1.txt").write_text("content1")
        (project_dir / "file2.txt").write_text("content2")
        (project_dir / "subdir").mkdir()
        (project_dir / "subdir" / "file3.txt").write_text("content3")

        target_dir = td_path / "target"
        target_dir.mkdir()

        # Create a Project instance
        project = Project.from_directory("test-project", project_dir)

        # Create SymlinkManager and sync
        manager = SymlinkManager(project.items, target_dir)
        result = manager.sync()

        # Verify symlink creation behavior
        # All items should be created (no existing symlinks)
        assert len(result.created) == 3  # noqa: PLR2004 - test expects 3 items (2 files + 1 dir)
        assert "file1.txt" in result.created
        assert "file2.txt" in result.created
        assert "subdir" in result.created

        # Verify no items were skipped or failed
        assert len(result.skipped) == 0
        assert len(result.failed) == 0
        assert not result.aborted

        # Verify symlinks exist and point to correct sources
        assert (target_dir / "file1.txt").is_symlink()
        assert (target_dir / "file2.txt").is_symlink()
        assert (target_dir / "subdir").is_symlink()

        assert (target_dir / "file1.txt").resolve() == (project_dir / "file1.txt").resolve()
        assert (target_dir / "file2.txt").resolve() == (project_dir / "file2.txt").resolve()
        assert (target_dir / "subdir").resolve() == (project_dir / "subdir").resolve()

        # Run sync again - all symlinks should be already_correct
        result2 = manager.sync()
        assert len(result2.already_correct) == 3  # noqa: PLR2004 - test expects 3 items
        assert len(result2.created) == 0

        # Run check to verify status
        check_result = manager.check()
        assert len(check_result.symlink_exists) == 3  # noqa: PLR2004 - test expects 3 items
        assert len(check_result.symlink_missing) == 0


def test_backward_compatible_config_format_variations():
    """Test various config format variations for backward compatibility.

    This test verifies that different valid config formats from the
    previous version continue to work correctly.
    """
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # Test 1: Single target as string
        config1 = {"project1": str(td_path / "target1")}
        config_path1 = td_path / "config1.yml"
        config_path1.write_text(yaml.dump(config1))

        (td_path / "project1").mkdir()
        (td_path / "target1").mkdir()

        cfg1 = Config(config_path1)
        projects1 = cfg1.get_projects()
        assert len(projects1["project1"].targets) == 1

        # Test 2: Multiple targets as list - now creates separate configs with suffixes
        config2 = {"project2": [str(td_path / "target2"), str(td_path / "target3")]}
        config_path2 = td_path / "config2.yml"
        config_path2.write_text(yaml.dump(config2))

        (td_path / "project2").mkdir()
        (td_path / "target2").mkdir()
        (td_path / "target3").mkdir()

        cfg2 = Config(config_path2)
        projects2 = cfg2.get_projects()
        # Multiple targets get split into separate configs with sequence suffixes
        assert len(projects2) == 2  # noqa: PLR2004 - test expects 2 configs
        assert "project2#1" in projects2
        assert "project2#2" in projects2
        assert len(projects2["project2#1"].targets) == 1
        assert len(projects2["project2#2"].targets) == 1

        # Test 3: Mixed absolute and relative paths
        config3 = {
            "project3": str(td_path / "target4"),
            "project4": ["target5", str(td_path / "target6")],
        }
        config_path3 = td_path / "config3.yml"
        config_path3.write_text(yaml.dump(config3))

        (td_path / "project3").mkdir()
        (td_path / "project4").mkdir()
        (td_path / "target4").mkdir()
        (td_path / "target5").mkdir()
        (td_path / "target6").mkdir()

        cfg3 = Config(config_path3)
        projects3 = cfg3.get_projects()
        assert "project3" in projects3
        # project4 has multiple targets, so it gets split with suffixes
        assert "project4#1" in projects3
        assert "project4#2" in projects3


def test_backward_compatible_cli_commands():
    """Test that all CLI commands work with global --config option.

    This test verifies that the command syntax uses global options correctly:
    - blf --config <path> symlink sync [project_name]
    - blf --config <path> symlink check [project_name] --extra-exclude
    """
    runner = CliRunner()

    with runner.isolated_filesystem() as td:
        td_path = Path(td)

        # Create test setup
        project_dir = td_path / "test-project"
        project_dir.mkdir()
        (project_dir / "file.txt").write_text("content")

        target_dir = td_path / "target"
        target_dir.mkdir()

        config_path = td_path / "test-config.yml"
        config_path.write_text(f"test-project: {target_dir}\n")

        # Test 1: sync with --config global option
        result1 = runner.invoke(cli, ["--config", str(config_path), "symlink", "sync"])
        assert result1.exit_code == 0

        # Test 2: sync with project name
        result2 = runner.invoke(cli, ["--config", str(config_path), "symlink", "sync", "test-project"])
        assert result2.exit_code == 0

        # Test 3: check with --config global option
        result3 = runner.invoke(cli, ["--config", str(config_path), "symlink", "check"])
        assert result3.exit_code == 0

        # Test 4: check with --extra-exclude option
        result4 = runner.invoke(cli, ["--config", str(config_path), "symlink", "check", "--extra-exclude"])
        assert result4.exit_code == 0

        # Test 5: check with project name
        result5 = runner.invoke(cli, ["--config", str(config_path), "symlink", "check", "test-project"])
        assert result5.exit_code == 0


def test_backward_compatible_relative_paths():
    """Test that relative paths in config files work as before.

    This test verifies that relative project paths are resolved
    relative to the config file location, maintaining backward
    compatibility with existing configurations.
    """
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # Create a config directory structure
        config_dir = td_path / "configs"
        config_dir.mkdir()

        # Create project directory relative to config
        projects_dir = config_dir / "projects"
        projects_dir.mkdir()
        project_dir = projects_dir / "my-project"
        project_dir.mkdir()
        (project_dir / "file.txt").write_text("content")

        # Create target directory
        target_dir = td_path / "target"
        target_dir.mkdir()

        # Create config with relative project path
        config_path = config_dir / "config.yml"
        config_content = {
            "projects/my-project": str(target_dir),
        }
        config_path.write_text(yaml.dump(config_content))

        # Load config and verify relative path resolution
        cfg = Config(config_path)
        projects = cfg.get_projects()

        # The project path should be resolved relative to config file
        expected_project_path = (config_dir / "projects" / "my-project").resolve()
        assert projects["projects/my-project"].project_path == expected_project_path
