"""Unit tests for the revlink restore CLI wiring and pre-flight validation.

Covers Requirements 1.4, 1.7, 3.1, 3.2, 3.3, 3.4.
"""

from pathlib import Path

from click.testing import CliRunner

from beyond_local_file.cli import cli
from tests.daemon_support import invoke_with_daemon

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_mapping(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a managed project, target, and selective mapping."""
    managed = tmp_path / "managed"
    target = tmp_path / "target"
    managed.mkdir()
    target.mkdir()
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"managed:\n  target: {target}\n  subpath: []\n")
    return config_path, managed, target


# ---------------------------------------------------------------------------
# Requirement 1.5 — revlink group lists both create and restore
# ---------------------------------------------------------------------------


def test_revlink_group_help_lists_restore() -> None:
    """Test that blf revlink --help lists restore as a subcommand.

    Requirement 1.5: WHEN blf revlink --help is invoked, THE Revlink_Group
    SHALL display the group description and list both create and restore
    subcommands.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["revlink", "--help"])
    assert result.exit_code == 0
    assert "restore" in result.output


def test_revlink_group_help_lists_create() -> None:
    """Test that blf revlink --help lists create as a subcommand.

    Requirement 1.5: WHEN blf revlink --help is invoked, THE Revlink_Group
    SHALL display the group description and list both create and restore
    subcommands.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["revlink", "--help"])
    assert result.exit_code == 0
    assert "create" in result.output


# ---------------------------------------------------------------------------
# Requirement 1.7 — revlink restore --help shows PATH and --dry-run, no --force
# ---------------------------------------------------------------------------


def test_restore_help_shows_path_argument() -> None:
    """Test that blf revlink restore --help displays the PATH positional argument.

    Requirement 1.7: WHEN blf revlink restore --help is invoked, THE
    Restore_Command SHALL display its description and all supported options.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["revlink", "restore", "--help"])
    assert result.exit_code == 0
    assert "PATH" in result.output


def test_restore_help_shows_dry_run_option() -> None:
    """Test that blf revlink restore --help displays the --dry-run flag.

    Requirement 1.7: THE Restore_Command SHALL display all supported options.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["revlink", "restore", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output


def test_restore_help_does_not_show_force_option() -> None:
    """Test that blf revlink restore --help does NOT display --force.

    Requirement 1.4: THE Restore_Command SHALL NOT accept a --force flag.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["revlink", "restore", "--help"])
    assert result.exit_code == 0
    assert "--force" not in result.output


# ---------------------------------------------------------------------------
# Requirement 1.4 — --force flag is rejected by restore
# ---------------------------------------------------------------------------


def test_restore_rejects_force_flag(tmp_path: Path) -> None:
    """Test that passing --force to revlink restore causes Click to error.

    Requirement 1.4: THE Restore_Command SHALL NOT accept a --force flag.
    Click should report an unknown option error.
    """
    runner = CliRunner()
    managed_dir = tmp_path / "managed"
    managed_dir.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    # Create a real file and a symlink to it
    real_file = managed_dir / "myfile.txt"
    real_file.write_text("content")
    symlink_path = target_dir / "myfile.txt"
    symlink_path.symlink_to(real_file)

    result = runner.invoke(cli, ["revlink", "restore", "--force", str(symlink_path)])

    # Click should reject the unknown option with a non-zero exit code
    assert result.exit_code != 0
    assert "no such option" in result.output.lower() or "error" in result.output.lower()


# ---------------------------------------------------------------------------
# Requirement 3.1 — non-existent path → error + exit 1
# ---------------------------------------------------------------------------


def test_restore_nonexistent_path_exits_with_error(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Test that a non-existent path produces an error message and exits 1.

    Requirement 3.1: WHEN the path argument does not exist, THE Restore_Command
    SHALL print a descriptive error message and exit with a non-zero status code
    without modifying the filesystem.
    """
    config_path, _managed, target = _write_mapping(tmp_path)
    monkeypatch.chdir(target)
    result = invoke_with_daemon(config_path, ["revlink", "restore", "does_not_exist.txt"], isolated_home)

    assert result.exit_code == 1
    assert "Path does not exist" in result.output
    assert not (target / "does_not_exist.txt").exists()


# ---------------------------------------------------------------------------
# Requirement 3.2 — path exists but is not a symlink → error + exit 1
# ---------------------------------------------------------------------------


def test_restore_real_file_without_hub_copy_exits_with_error(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """A real file with no managed copy is not restorable.

    Restore leaves a real projection in place, but only when the hub copy
    exists. A lone target file is rejected without modifying the filesystem.
    """
    config_path, _managed, target = _write_mapping(tmp_path)
    real_file = target / "myfile.txt"
    real_file.write_text("original content")
    monkeypatch.chdir(target)

    result = invoke_with_daemon(config_path, ["revlink", "restore", "myfile.txt"], isolated_home)

    assert result.exit_code == 1
    assert "managed copy does not exist" in result.output.lower()
    assert real_file.read_text() == "original content"


# ---------------------------------------------------------------------------
# Requirement 3.3 — dangling symlink (managed copy missing) → error + exit 1
# ---------------------------------------------------------------------------


def test_restore_dangling_symlink_exits_with_error(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Test that a symlink whose managed copy is missing produces an error.

    Requirement 3.3: WHEN the path is a symlink but its target (the
    Managed_Copy) does not exist, THE Restore_Command SHALL print a descriptive
    error message indicating a dangling symlink, and exit with a non-zero
    status code without modifying the filesystem.
    """
    config_path, managed, target = _write_mapping(tmp_path)
    missing_managed = managed / "myfile.txt"
    symlink_path = target / "myfile.txt"
    symlink_path.symlink_to(missing_managed)
    monkeypatch.chdir(target)

    result = invoke_with_daemon(config_path, ["revlink", "restore", "myfile.txt"], isolated_home)

    assert result.exit_code == 1
    assert "dangling symlink" in result.output.lower() or "managed copy does not exist" in result.output.lower()
    assert symlink_path.is_symlink()


# ---------------------------------------------------------------------------
# Requirement 3.4 — --dry-run is accepted; exit 0, no filesystem changes
# ---------------------------------------------------------------------------


def test_restore_dry_run_accepted_and_exits_zero(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Test that --dry-run is accepted, exits 0, and makes no filesystem changes.

    Requirement 3.4: WHEN --dry-run is active, THE Restore_Command SHALL
    perform all validation checks and report what would happen, but SHALL NOT
    modify the filesystem.
    """
    config_path, managed, target = _write_mapping(tmp_path)
    managed_file = managed / "myfile.txt"
    managed_file.write_text("managed content")
    symlink_path = target / "myfile.txt"
    symlink_path.symlink_to(managed_file)
    monkeypatch.chdir(target)

    result = invoke_with_daemon(config_path, ["revlink", "restore", "--dry-run", "myfile.txt"], isolated_home)

    assert result.exit_code == 0, result.output
    assert symlink_path.is_symlink()
    assert managed_file.exists()
    assert managed_file.read_text() == "managed content"


def test_restore_dry_run_prints_dry_run_prefixed_output(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Test that --dry-run prints [dry-run]-prefixed preview lines.

    Requirement 3.4 / Requirement 7.10: WHEN --dry-run is active, THE
    Restore_Command SHALL prefix all output lines with [dry-run].
    """
    config_path, managed, target = _write_mapping(tmp_path)
    managed_file = managed / "myfile.txt"
    managed_file.write_text("managed content")
    symlink_path = target / "myfile.txt"
    symlink_path.symlink_to(managed_file)
    monkeypatch.chdir(target)

    result = invoke_with_daemon(config_path, ["revlink", "restore", "--dry-run", "myfile.txt"], isolated_home)

    assert result.exit_code == 0, result.output
    assert "[dry-run]" in result.output
    assert symlink_path.is_symlink()
