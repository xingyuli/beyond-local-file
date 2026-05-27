"""Unit tests for the revlink CLI group structure and subcommand wiring.

Covers Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7.

Tests in this module are split into two sections:
- Tests for the revlink group and create subcommand.
- Tests for the restore subcommand.
"""

import pytest  # noqa: F401 -- kept for potential future use
from click.testing import CliRunner

from beyond_local_file.cli import cli

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _invoke_help(*args: str) -> tuple[int, str]:
    """Invoke the CLI with the given args plus --help and return (exit_code, output).

    Args:
        *args: CLI arguments to pass before --help.

    Returns:
        A tuple of (exit_code, output_text).
    """
    runner = CliRunner()
    result = runner.invoke(cli, [*args, "--help"])
    return result.exit_code, result.output


# ===========================================================================
# Section 1: Tests that pass now
# (revlink group + create subcommand are already implemented)
# ===========================================================================


class TestRevlinkGroupHelp:
    """Tests for `blf revlink --help` — Requirement 1.5."""

    def test_revlink_group_help_exits_zero(self) -> None:
        """Test that `blf revlink --help` exits with code 0.

        Requirement 1.5: WHEN `blf revlink --help` is invoked, THE Revlink_Group
        SHALL display the group description and list both subcommands.
        """
        exit_code, _ = _invoke_help("revlink")
        assert exit_code == 0

    def test_revlink_group_help_lists_create(self) -> None:
        """Test that `blf revlink --help` lists the `create` subcommand.

        Requirement 1.5: THE Revlink_Group SHALL list both `create` and `restore`.
        """
        _, output = _invoke_help("revlink")
        assert "create" in output

    def test_revlink_group_help_lists_restore(self) -> None:
        """Test that `blf revlink --help` lists the `restore` subcommand.

        Requirement 1.5: THE Revlink_Group SHALL list both `create` and `restore`.
        """
        _, output = _invoke_help("revlink")
        assert "restore" in output

    def test_revlink_group_has_description(self) -> None:
        """Test that `blf revlink --help` shows a group description.

        Requirement 1.5: THE Revlink_Group SHALL display the group description.
        """
        _, output = _invoke_help("revlink")
        # The group docstring mentions lifecycle / managed project
        assert any(keyword in output.lower() for keyword in ("lifecycle", "managed", "adopt"))


class TestRevlinkCreateHelp:
    """Tests for `blf revlink create --help` — Requirements 1.2, 1.3, 1.6."""

    def test_create_help_exits_zero(self) -> None:
        """Test that `blf revlink create --help` exits with code 0.

        Requirement 1.6: WHEN `blf revlink create --help` is invoked, THE
        Create_Command SHALL display its description and all supported options.
        """
        exit_code, _ = _invoke_help("revlink", "create")
        assert exit_code == 0

    def test_create_help_shows_path_argument(self) -> None:
        """Test that `blf revlink create --help` shows the PATH argument.

        Requirement 1.2: THE Create_Command SHALL accept one required positional
        argument (the path).
        """
        _, output = _invoke_help("revlink", "create")
        assert "PATH" in output

    def test_create_help_shows_dry_run_option(self) -> None:
        """Test that `blf revlink create --help` shows the --dry-run flag.

        Requirement 1.3: THE Create_Command SHALL accept a --dry-run flag.
        """
        _, output = _invoke_help("revlink", "create")
        assert "--dry-run" in output

    def test_create_help_shows_force_option(self) -> None:
        """Test that `blf revlink create --help` shows the --force flag.

        Requirement 1.3: THE Create_Command SHALL accept a --force flag.
        """
        _, output = _invoke_help("revlink", "create")
        assert "--force" in output

    def test_create_help_shows_description(self) -> None:
        """Test that `blf revlink create --help` shows a command description.

        Requirement 1.6: THE Create_Command SHALL display its description.
        """
        _, output = _invoke_help("revlink", "create")
        assert any(keyword in output.lower() for keyword in ("symlink", "managed", "convert", "copies"))


# ===========================================================================
# Section 2: Tests for `restore` subcommand
# ===========================================================================


class TestRevlinkRestoreHelp:
    """Tests for `blf revlink restore --help` — Requirements 1.4, 1.7."""

    def test_restore_help_exits_zero(self) -> None:
        """Test that `blf revlink restore --help` exits with code 0.

        Requirement 1.7: WHEN `blf revlink restore --help` is invoked, THE
        Restore_Command SHALL display its description and all supported options.
        """
        exit_code, _ = _invoke_help("revlink", "restore")
        assert exit_code == 0

    def test_restore_help_shows_path_argument(self) -> None:
        """Test that `blf revlink restore --help` shows the PATH argument.

        Requirement 1.4: THE Restore_Command SHALL accept one required positional
        argument (the path).
        """
        _, output = _invoke_help("revlink", "restore")
        assert "PATH" in output

    def test_restore_help_shows_dry_run_option(self) -> None:
        """Test that `blf revlink restore --help` shows the --dry-run flag.

        Requirement 1.4: THE Restore_Command SHALL accept a --dry-run flag.
        """
        _, output = _invoke_help("revlink", "restore")
        assert "--dry-run" in output

    def test_restore_help_does_not_show_force_option(self) -> None:
        """Test that `blf revlink restore --help` does NOT show --force.

        Requirement 1.4: THE Restore_Command SHALL NOT accept a --force flag.
        """
        exit_code, output = _invoke_help("revlink", "restore")
        assert exit_code == 0
        assert "--force" not in output

    def test_restore_help_shows_description(self) -> None:
        """Test that `blf revlink restore --help` shows a command description.

        Requirement 1.7: THE Restore_Command SHALL display its description.
        """
        exit_code, output = _invoke_help("revlink", "restore")
        assert exit_code == 0
        assert any(keyword in output.lower() for keyword in ("symlink", "managed", "dissolve", "recover"))
