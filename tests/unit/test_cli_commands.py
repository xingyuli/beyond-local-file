"""Unit tests for CLI commands and options.

Tests verify that all CLI commands, options, and arguments are properly
exposed and functional.
"""

from pathlib import Path

from click.testing import CliRunner

from beyond_local_file.cli import cli


def test_cli_help_command():
    """Test that the main CLI help command works."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Manage links between project directories" in result.output


def test_link_group_exists():
    """Test that the link command group exists."""
    runner = CliRunner()
    result = runner.invoke(cli, ["link", "--help"])
    assert result.exit_code == 0
    assert "Link management commands" in result.output


def test_symlink_alias_exists():
    """Test that the symlink alias still works for backward compatibility."""
    runner = CliRunner()
    result = runner.invoke(cli, ["symlink", "--help"])
    assert result.exit_code == 0


def test_link_sync_command_exists():
    """Test that 'beyond-local-file link sync' command exists."""
    runner = CliRunner()
    result = runner.invoke(cli, ["link", "sync", "--help"])
    assert result.exit_code == 0
    assert "Synchronize links from project directory" in result.output


def test_link_check_command_exists():
    """Test that 'beyond-local-file link check' command exists."""
    runner = CliRunner()
    result = runner.invoke(cli, ["link", "check", "--help"])
    assert result.exit_code == 0
    assert "Check link status and Git exclude" in result.output


def test_sync_accepts_config_option():
    """Test that --config global option is available for sync command."""
    runner = CliRunner()
    # --config is a global option, so it appears in root help
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "--config" in result.output or "-c" in result.output
    assert "Path to config file" in result.output


def test_check_accepts_config_option():
    """Test that --config global option is available for check command."""
    runner = CliRunner()
    # --config is a global option, so it appears in root help
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "--config" in result.output or "-c" in result.output
    assert "Path to config file" in result.output


def test_sync_accepts_project_name_argument():
    """Test that sync command accepts project_name argument."""
    runner = CliRunner()
    result = runner.invoke(cli, ["link", "sync", "--help"])
    assert result.exit_code == 0
    assert "PROJECT_NAME" in result.output or "project_name" in result.output.lower()


def test_check_accepts_project_name_argument():
    """Test that check command accepts project_name argument."""
    runner = CliRunner()
    result = runner.invoke(cli, ["link", "check", "--help"])
    assert result.exit_code == 0
    assert "PROJECT_NAME" in result.output or "project_name" in result.output.lower()


def test_check_accepts_extra_exclude_option():
    """Test that check command accepts --extra-exclude option."""
    runner = CliRunner()
    result = runner.invoke(cli, ["link", "check", "--help"])
    assert result.exit_code == 0
    assert "--extra-exclude" in result.output
    assert "Show extra entries" in result.output


def test_default_config_file_discovery(temp_dir: Path) -> None:
    """Test that tool finds config.yml in current directory without --config.

    Args:
        temp_dir: Temporary directory fixture (unused in this test).
    """
    runner = CliRunner()

    with runner.isolated_filesystem() as td:
        td_path = Path(td)

        project_dir = td_path / "test-project"
        project_dir.mkdir()
        (project_dir / "test-file.txt").write_text("test content")

        target_dir = td_path / "target"
        target_dir.mkdir()

        config_path = td_path / "config.yml"
        config_path.write_text("test-project: target\n")

        result = runner.invoke(cli, ["link", "check"])

        assert result.exit_code == 0
        assert "test-project" in result.output


def test_error_message_when_config_not_found() -> None:
    """Test that tool displays error message when config file is not found."""
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["link", "check"])

        assert "Config file not found" in result.output
        assert "config.yml" in result.output


def test_error_message_with_custom_config_not_found() -> None:
    """Test that tool displays error message when custom config file is not found."""
    runner = CliRunner()

    with runner.isolated_filesystem():
        # Use correct global option syntax: --config before subcommand
        result = runner.invoke(cli, ["--config", "nonexistent.yml", "link", "check"])

        assert "Config file not found" in result.output
        assert "nonexistent.yml" in result.output


def test_symlink_alias_sync_works():
    """Test that 'symlink sync' alias still works."""
    runner = CliRunner()
    result = runner.invoke(cli, ["symlink", "sync", "--help"])
    assert result.exit_code == 0
    assert "Synchronize links" in result.output


def test_symlink_alias_check_works():
    """Test that 'symlink check' alias still works."""
    runner = CliRunner()
    result = runner.invoke(cli, ["symlink", "check", "--help"])
    assert result.exit_code == 0
    assert "Check link status" in result.output
