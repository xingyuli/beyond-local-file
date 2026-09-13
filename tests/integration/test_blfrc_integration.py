"""Integration tests for ~/.blf/config pointer-list support."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from beyond_local_file.cli import cli
from tests.daemon_support import daemon_running, invoke_cli


def _write_pointer(home: Path, mapping_files: list[Path] | str) -> Path:
    path = home / ".blf" / "config"
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(mapping_files, str):
        path.write_text(mapping_files)
        return path
    lines = ["config_file:"]
    lines.extend(f"  - {mapping}" for mapping in mapping_files)
    path.write_text("\n".join(lines) + "\n")
    return path


def _assert_copy_projection(path: Path) -> None:
    """A projection is a real copy, not a symlink."""
    assert path.exists(), path
    assert not path.is_symlink(), path


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
    home_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("BLF_HOME", str(home_dir))
    yield home_dir, {"BLF_HOME": str(home_dir)}


class TestGlobalConfigIntegration:
    """Integration tests for ~/.blf/config support."""

    def test_uses_config_from_global_pointer_single_file(self, temp_home, tmp_path):
        """Test that config is loaded from ~/.blf/config with single file."""
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

        _write_pointer(home_dir, [config])

        started = invoke_cli(["daemon", "start"], env=env)
        assert started.exit_code == 0, started.output
        invoke_cli(["daemon", "stop"], env=env)

        _assert_copy_projection(target / "file1.txt")
        _assert_copy_projection(target / "file2.txt")

    def test_uses_config_from_global_pointer_multiple_files(self, temp_home, tmp_path):
        """Test that one daemon loads every mapping file in ~/.blf/config."""
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

        _write_pointer(home_dir, [config1, config2])

        try:
            started = invoke_cli(["daemon", "start"], env=env)
            assert started.exit_code == 0, started.output
        finally:
            invoke_cli(["daemon", "stop"], env=env)

        _assert_copy_projection(target1 / "file1.txt")
        _assert_copy_projection(target2 / "file2.txt")

    def test_explicit_config_flag_overrides_global_config(self, temp_home, tmp_path):
        """Test that explicit --config flag overrides ~/.blf/config."""
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

        _write_pointer(home_dir, [blfrc_config])

        with daemon_running(explicit_config, env):
            pass

        _assert_copy_projection(right_target / "file1.txt")
        assert not (wrong_target / "file1.txt").exists()

    def test_falls_back_to_default_when_global_config_missing(self, temp_home):
        """Test that default config.yml is used when ~/.blf/config doesn't exist."""
        _home_dir, env = temp_home

        # No ~/.blf/config — build everything inside isolated_filesystem so config.yml
        # is in the CWD that the CLI will use
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            td_path = Path(td)
            managed = td_path / "test-project"
            managed.mkdir()
            (managed / "file1.txt").write_text("content1")
            target = td_path / "target"
            target.mkdir()

            config_path = td_path / "config.yml"
            config_path.write_text(f"test-project: {target}\n")

            with daemon_running(config_path, env):
                pass

            _assert_copy_projection(target / "file1.txt")

    def test_falls_back_when_config_file_field_missing(self, temp_home):
        """Test fallback to default when ~/.blf/config exists but config_file is missing."""
        home_dir, env = temp_home

        _write_pointer(home_dir, "other_field: value\n")

        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            td_path = Path(td)
            managed = td_path / "test-project"
            managed.mkdir()
            (managed / "file1.txt").write_text("content1")
            target = td_path / "target"
            target.mkdir()

            config_path = td_path / "config.yml"
            config_path.write_text(f"test-project: {target}\n")

            with daemon_running(config_path, env):
                pass

            _assert_copy_projection(target / "file1.txt")

    def test_error_on_invalid_global_config(self, temp_home, tmp_path):
        """Test that error is shown when ~/.blf/config is invalid."""
        home_dir, env = temp_home

        _write_pointer(home_dir, "config_file: [\n")

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["daemon", "status"], env=env)

        assert result.exit_code != 0
        assert "Error:" in result.output
        assert "Invalid YAML" in result.output

    def test_error_on_config_file_not_found(self, temp_home, tmp_path):
        """Test that error is shown when config file from ~/.blf/config doesn't exist."""
        home_dir, env = temp_home

        _write_pointer(home_dir, "config_file: /nonexistent/config.yml\n")

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["daemon", "status"], env=env)

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

        _write_pointer(home_dir, [config1, config2])

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["daemon", "status"], env=env)

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

        _write_pointer(home_dir, [config1, config2])

        try:
            started = invoke_cli(["daemon", "start"], env=env)
            assert started.exit_code == 0, started.output
        finally:
            invoke_cli(["daemon", "stop"], env=env)

        _assert_copy_projection(target1 / "file1.txt")
        _assert_copy_projection(target2 / "file2.txt")
