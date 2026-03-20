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
    assert "Manage symlinks between project directories" in result.output


def test_symlink_group_exists():
    """Test that the symlink command group exists."""
    runner = CliRunner()
    result = runner.invoke(cli, ["symlink", "--help"])
    assert result.exit_code == 0
    assert "Symlink management commands" in result.output


def test_symlink_sync_command_exists():
    """Test that 'beyond-local-file symlink sync' command exists."""
    runner = CliRunner()
    result = runner.invoke(cli, ["symlink", "sync", "--help"])
    assert result.exit_code == 0
    assert "Synchronize symlinks from project directory" in result.output


def test_symlink_check_command_exists():
    """Test that 'beyond-local-file symlink check' command exists."""
    runner = CliRunner()
    result = runner.invoke(cli, ["symlink", "check", "--help"])
    assert result.exit_code == 0
    assert "Check symlink status and Git exclude" in result.output


def test_sync_accepts_config_option():
    """Test that sync command accepts --config option."""
    runner = CliRunner()
    result = runner.invoke(cli, ["symlink", "sync", "--help"])
    assert result.exit_code == 0
    assert "--config" in result.output or "-c" in result.output
    assert "Path to config file" in result.output


def test_check_accepts_config_option():
    """Test that check command accepts --config option."""
    runner = CliRunner()
    result = runner.invoke(cli, ["symlink", "check", "--help"])
    assert result.exit_code == 0
    assert "--config" in result.output or "-c" in result.output
    assert "Path to config file" in result.output


def test_sync_accepts_project_name_argument():
    """Test that sync command accepts project_name argument."""
    runner = CliRunner()
    result = runner.invoke(cli, ["symlink", "sync", "--help"])
    assert result.exit_code == 0
    # Check that PROJECT_NAME is mentioned in the help output
    assert "PROJECT_NAME" in result.output or "project_name" in result.output.lower()


def test_check_accepts_project_name_argument():
    """Test that check command accepts project_name argument."""
    runner = CliRunner()
    result = runner.invoke(cli, ["symlink", "check", "--help"])
    assert result.exit_code == 0
    # Check that PROJECT_NAME is mentioned in the help output
    assert "PROJECT_NAME" in result.output or "project_name" in result.output.lower()


def test_check_accepts_extra_exclude_option():
    """Test that check command accepts --extra-exclude option."""
    runner = CliRunner()
    result = runner.invoke(cli, ["symlink", "check", "--help"])
    assert result.exit_code == 0
    assert "--extra-exclude" in result.output
    assert "Show extra entries" in result.output


def test_default_config_file_discovery(temp_dir: Path) -> None:
    """Test that tool finds config.yml in current directory without --config.

    Args:
        temp_dir: Temporary directory fixture (unused in this test).
    """
    runner = CliRunner()

    # Use CliRunner's isolated_filesystem to simulate running from a directory
    with runner.isolated_filesystem() as td:
        td_path = Path(td)

        # Create a test project directory
        project_dir = td_path / "test-project"
        project_dir.mkdir()
        (project_dir / "test-file.txt").write_text("test content")

        # Create a target directory
        target_dir = td_path / "target"
        target_dir.mkdir()

        # Create config.yml in the current directory (isolated filesystem root)
        config_path = td_path / "config.yml"
        config_path.write_text("test-project: target\n")

        # Run check command without --config option
        # The tool should find config.yml in the current directory
        result = runner.invoke(cli, ["symlink", "check"])

        # Verify the tool found and used config.yml
        assert result.exit_code == 0
        # Default output is table mode — project name appears as a table cell
        assert "test-project" in result.output


def test_error_message_when_config_not_found() -> None:
    """Test that tool displays error message when config file is not found."""
    runner = CliRunner()

    # Use CliRunner's isolated_filesystem to simulate running from a directory
    with runner.isolated_filesystem():
        # Run check command without creating config.yml
        # The tool should display an error message
        result = runner.invoke(cli, ["symlink", "check"])

        # Verify the tool displays an error message
        assert "Config file not found" in result.output
        # Verify the error message includes the path that was searched
        assert "config.yml" in result.output


def test_error_message_with_custom_config_not_found() -> None:
    """Test that tool displays error message when custom config file is not found."""
    runner = CliRunner()

    # Use CliRunner's isolated_filesystem to simulate running from a directory
    with runner.isolated_filesystem():
        # Run check command with a non-existent config file
        result = runner.invoke(cli, ["symlink", "check", "--config", "nonexistent.yml"])

        # Verify the tool displays an error message
        assert "Config file not found" in result.output
        # Verify the error message includes the path that was searched
        assert "nonexistent.yml" in result.output
