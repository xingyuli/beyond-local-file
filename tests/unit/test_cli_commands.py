"""Unit tests for CLI commands and options.

Tests verify that all CLI commands, options, and arguments are properly
exposed and functional.
"""

from pathlib import Path

from click.testing import CliRunner

from beyond_local_file.cli import cli
from tests.daemon_support import daemon_running


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


def test_link_sync_is_not_a_command():
    """Test that 'beyond-local-file link sync' is not a command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["link", "sync", "--help"])
    assert result.exit_code != 0
    assert "no such command" in result.output.lower()


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


def test_default_config_file_discovery(temp_dir: Path, isolated_home) -> None:
    """Test that tool finds config.yml in current directory without --config.

    Args:
        temp_dir: Temporary directory fixture (unused in this test).
        isolated_home: Env dict that bypasses the real ~/.blfrc.
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

        with daemon_running(config_path, isolated_home):
            result = runner.invoke(cli, ["link", "check"], env=isolated_home)

        assert result.exit_code == 0
        assert "test-project" in result.output


def test_error_message_when_config_not_found(isolated_home) -> None:
    """Test that tool displays error message when config file is not found."""
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["link", "check"], env=isolated_home)

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


def test_link_sync_rejects_copy_true_and_names_project_mapping_and_key(
    isolated_home,
) -> None:
    """Config load fails if copy: true is present, naming project, mapping, and key."""
    runner = CliRunner()

    with runner.isolated_filesystem() as td:
        td_path = Path(td)
        project_dir = td_path / "my-project"
        project_dir.mkdir()
        (project_dir / "rules.md").write_text("rules")
        target_dir = td_path / "target"
        target_dir.mkdir()
        (td_path / "config.yml").write_text(
            f"""my-project:
  target: {target_dir}
  subpath:
    - path: rules.md
      copy: true
"""
        )

        result = runner.invoke(cli, ["daemon", "start"], env=isolated_home)

        assert result.exit_code != 0
        assert "project: my-project" in result.output
        assert "mapping: 1" in result.output
        assert "key: copy" in result.output


def test_link_sync_projects_mapping_without_copy_flag_as_copies(isolated_home) -> None:
    """New and existing mappings without copy: true project as copies."""
    runner = CliRunner()

    with runner.isolated_filesystem() as td:
        td_path = Path(td)
        project_dir = td_path / "my-project"
        project_dir.mkdir()
        (project_dir / "file1.txt").write_text("content1")
        hooks = project_dir / ".kiro" / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "hook.json").write_text("{}")
        target_dir = td_path / "target"
        target_dir.mkdir()
        (td_path / "config.yml").write_text(
            f"""my-project:
  target: {target_dir}
  subpath:
    - file1.txt
    - .kiro/hooks
"""
        )

        config_path = td_path / "config.yml"
        with daemon_running(config_path, isolated_home):
            pass

        file_projection = target_dir / "file1.txt"
        dir_projection = target_dir / ".kiro" / "hooks"
        assert file_projection.is_file()
        assert not file_projection.is_symlink()
        assert file_projection.read_text() == "content1"
        assert dir_projection.is_dir()
        assert not dir_projection.is_symlink()
        assert (dir_projection / "hook.json").read_text() == "{}"


def test_remove_is_destructive_top_level_command_with_required_path() -> None:
    """The top-level non-interactive remove command documents PATH and dry-run.

    ``Click`` supplies usage and a non-zero exit when the required positional
    path is omitted, so scripts cannot accidentally invoke an unspecified
    removal operation.
    """
    runner = CliRunner()

    help_result = runner.invoke(cli, ["remove", "--help"])
    missing_path_result = runner.invoke(cli, ["remove"])

    assert help_result.exit_code == 0
    assert "PATH" in help_result.output
    assert "--dry-run" in help_result.output
    assert "permanently" in help_result.output.lower()
    assert missing_path_result.exit_code != 0
    assert "Usage:" in missing_path_result.output
