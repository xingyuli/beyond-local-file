"""Integration tests for .blfrc configuration file support."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from beyond_local_file.cli import cli


@pytest.fixture
def temp_home(tmp_path, monkeypatch):
    """Create a temporary home directory for testing.

    Args:
        tmp_path: Pytest temporary directory fixture.
        monkeypatch: Pytest monkeypatch fixture.

    Yields:
        Tuple of (Path to temporary home directory, env dict for CliRunner).
    """
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("BLF_HOME", str(home_dir))
    yield home_dir, {"BLF_HOME": str(home_dir)}


class TestBlfrcIntegration:
    """Integration tests for .blfrc support."""

    def test_uses_config_from_blfrc_single_file(self, temp_home, tmp_path):
        """Test that config is loaded from .blfrc with single file."""
        home_dir, env = temp_home

        # Create managed project and target
        managed = tmp_path / "test-project"
        managed.mkdir()
        (managed / "file1.txt").write_text("content1")
        (managed / "file2.txt").write_text("content2")
        target = tmp_path / "target"
        target.mkdir()

        # Config lives next to managed dir, so project name resolves correctly
        config = tmp_path / "my-config.yml"
        config.write_text(f"test-project: {target}\n")

        blfrc = home_dir / ".blfrc"
        blfrc.write_text(f"config_file: {config}\n")

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["link", "sync"], env=env)

        assert result.exit_code == 0, result.output
        assert (target / "file1.txt").is_symlink()
        assert (target / "file2.txt").is_symlink()

    def test_uses_config_from_blfrc_multiple_files(self, temp_home, tmp_path):
        """Test that multiple configs are combined from .blfrc."""
        home_dir, env = temp_home

        # Two separate directories each with their own managed project and config
        group1 = tmp_path / "group1"
        group2 = tmp_path / "group2"
        (group1 / "project1").mkdir(parents=True)
        (group2 / "project2").mkdir(parents=True)
        (group1 / "project1" / "file1.txt").write_text("content1")
        (group2 / "project2" / "file2.txt").write_text("content2")

        target1 = tmp_path / "target1"
        target2 = tmp_path / "target2"
        target1.mkdir()
        target2.mkdir()

        # Each config lives next to its managed dir so project names resolve correctly
        config1 = group1 / "config.yml"
        config2 = group2 / "config.yml"
        config1.write_text(f"project1: {target1}\n")
        config2.write_text(f"project2: {target2}\n")

        blfrc = home_dir / ".blfrc"
        blfrc.write_text(f"config_file:\n  - {config1}\n  - {config2}\n")

        runner = CliRunner()
        # CWD doesn't matter here since config paths are absolute in .blfrc
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["link", "sync"], env=env)

        assert result.exit_code == 0, result.output
        assert (target1 / "file1.txt").is_symlink()
        assert (target2 / "file2.txt").is_symlink()

    def test_explicit_config_flag_overrides_blfrc(self, temp_home, tmp_path):
        """Test that explicit --config flag overrides .blfrc."""
        home_dir, env = temp_home

        managed = tmp_path / "test-project"
        managed.mkdir()
        (managed / "file1.txt").write_text("content1")
        right_target = tmp_path / "right-target"
        wrong_target = tmp_path / "wrong-target"
        right_target.mkdir()
        wrong_target.mkdir()

        blfrc_config = tmp_path / "blfrc-config.yml"
        explicit_config = tmp_path / "explicit-config.yml"
        blfrc_config.write_text(f"test-project: {wrong_target}\n")
        explicit_config.write_text(f"test-project: {right_target}\n")

        blfrc = home_dir / ".blfrc"
        blfrc.write_text(f"config_file: {blfrc_config}\n")

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["--config", str(explicit_config), "link", "sync"], env=env)

        assert result.exit_code == 0, result.output
        assert (right_target / "file1.txt").is_symlink()
        assert not (wrong_target / "file1.txt").exists()

    def test_falls_back_to_default_when_blfrc_missing(self, temp_home):
        """Test that default config.yml is used when .blfrc doesn't exist."""
        _home_dir, env = temp_home

        # No .blfrc — build everything inside isolated_filesystem so config.yml
        # is in the CWD that the CLI will use
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            td_path = Path(td)
            managed = td_path / "test-project"
            managed.mkdir()
            (managed / "file1.txt").write_text("content1")
            target = td_path / "target"
            target.mkdir()

            (td_path / "config.yml").write_text(f"test-project: {target}\n")

            result = runner.invoke(cli, ["link", "sync"], env=env)

            assert result.exit_code == 0, result.output
            assert (target / "file1.txt").is_symlink()

    def test_falls_back_when_config_file_field_missing(self, temp_home):
        """Test fallback to default when .blfrc exists but config_file is missing."""
        home_dir, env = temp_home

        blfrc = home_dir / ".blfrc"
        blfrc.write_text("other_field: value\n")

        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            td_path = Path(td)
            managed = td_path / "test-project"
            managed.mkdir()
            (managed / "file1.txt").write_text("content1")
            target = td_path / "target"
            target.mkdir()

            (td_path / "config.yml").write_text(f"test-project: {target}\n")

            result = runner.invoke(cli, ["link", "sync"], env=env)

            assert result.exit_code == 0, result.output
            assert (target / "file1.txt").is_symlink()

    def test_error_on_invalid_blfrc(self, temp_home, tmp_path):
        """Test that error is shown when .blfrc is invalid."""
        home_dir, env = temp_home

        blfrc = home_dir / ".blfrc"
        blfrc.write_text("config_file: [\n")  # Invalid YAML

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["link", "sync"], env=env)

        assert result.exit_code != 0
        assert "Error:" in result.output
        assert "Invalid YAML" in result.output

    def test_error_on_config_file_not_found(self, temp_home, tmp_path):
        """Test that error is shown when config file from .blfrc doesn't exist."""
        home_dir, env = temp_home

        blfrc = home_dir / ".blfrc"
        blfrc.write_text("config_file: /nonexistent/config.yml\n")

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["link", "sync"], env=env)

        assert result.exit_code != 0
        assert "Error:" in result.output
        assert "Config file not found" in result.output

    def test_error_on_duplicate_managed_project_paths(self, temp_home, tmp_path):
        """Test that error is shown when same managed project path in multiple configs."""
        home_dir, env = temp_home

        # Both configs live in the same dir, so same project name = same managed path
        managed = tmp_path / "test-project"
        managed.mkdir()
        (managed / "file.txt").write_text("content")

        config1 = tmp_path / "config1.yml"
        config2 = tmp_path / "config2.yml"
        config1.write_text(f"test-project: {tmp_path / 'target1'}\n")
        config2.write_text(f"test-project: {tmp_path / 'target2'}\n")

        blfrc = home_dir / ".blfrc"
        blfrc.write_text(f"config_file:\n  - {config1}\n  - {config2}\n")

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["link", "sync"], env=env)

        assert result.exit_code != 0
        assert "Error:" in result.output
        assert "defined in multiple config files" in result.output

    def test_same_project_name_different_managed_locations_allowed(self, temp_home, tmp_path):
        """Test that same project name is allowed if managed locations differ."""
        home_dir, env = temp_home

        # Two separate directories each with a "my-project" subdirectory
        group1 = tmp_path / "group1"
        group2 = tmp_path / "group2"
        (group1 / "my-project").mkdir(parents=True)
        (group2 / "my-project").mkdir(parents=True)
        (group1 / "my-project" / "file1.txt").write_text("content1")
        (group2 / "my-project" / "file2.txt").write_text("content2")

        target1 = tmp_path / "target1"
        target2 = tmp_path / "target2"
        target1.mkdir()
        target2.mkdir()

        # Each config lives in its own group dir → different managed project paths
        config1 = group1 / "config.yml"
        config2 = group2 / "config.yml"
        config1.write_text(f"my-project: {target1}\n")
        config2.write_text(f"my-project: {target2}\n")

        blfrc = home_dir / ".blfrc"
        blfrc.write_text(f"config_file:\n  - {config1}\n  - {config2}\n")

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["link", "sync"], env=env)

        assert result.exit_code == 0, result.output
        assert (target1 / "file1.txt").is_symlink()
        assert (target2 / "file2.txt").is_symlink()
