"""Unit tests for the revlink CLI command wiring and pre-flight validation.

Covers Requirements 1.1, 1.2, 1.3, 1.4, 1.6, 3.1, 3.2, 3.3, 3.3a.
"""

from pathlib import Path

from click.testing import CliRunner

from beyond_local_file.cli import cli
from tests.daemon_support import invoke_with_daemon


def _write_mapping(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a managed project, target, and config mapping."""
    managed = tmp_path / "managed"
    target = tmp_path / "target"
    managed.mkdir()
    target.mkdir()
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"managed:\n  target: {target}\n  subpath: []\n")
    return config_path, managed, target


# ---------------------------------------------------------------------------
# Requirement 1.1 — revlink is a top-level command (not under `link`)
# ---------------------------------------------------------------------------


def test_revlink_is_top_level_command() -> None:
    """Test that revlink is registered directly under the cli group.

    Requirement 1.1: THE Revlink_Command SHALL be registered as a top-level
    subcommand of the blf CLI group (not under the link subgroup).
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "revlink" in result.output


def test_revlink_not_under_link_group() -> None:
    """Test that revlink is NOT listed under the link subgroup.

    Requirement 1.1: revlink must not appear under the link group.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["link", "--help"])
    assert result.exit_code == 0
    assert "revlink" not in result.output


# ---------------------------------------------------------------------------
# Requirement 1.2, 1.3, 1.4, 1.6 — --help shows path, --dry-run, --force
# ---------------------------------------------------------------------------


def test_revlink_help_shows_path_argument() -> None:
    """Test that --help displays the PATH positional argument.

    Requirement 1.2: THE Create_Command SHALL accept exactly one required
    positional argument: the path of the file or directory to convert.
    Requirement 1.6: WHEN blf revlink create --help is invoked, the command SHALL
    display the path argument and all supported options.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["revlink", "create", "--help"])
    assert result.exit_code == 0
    assert "PATH" in result.output


def test_revlink_help_shows_dry_run_option() -> None:
    """Test that --help displays the --dry-run flag.

    Requirement 1.3: THE Create_Command SHALL accept a --dry-run flag.
    Requirement 1.6: --help SHALL display all supported options.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["revlink", "create", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output


def test_revlink_help_shows_force_option() -> None:
    """Test that --help displays the --force flag.

    Requirement 1.4: THE Create_Command SHALL accept a --force flag.
    Requirement 1.6: --help SHALL display all supported options.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["revlink", "create", "--help"])
    assert result.exit_code == 0
    assert "--force" in result.output


def test_revlink_help_shows_description() -> None:
    """Test that --help shows a concise description of the command.

    Requirement 1.6: WHEN blf revlink create --help is invoked, THE Create_Command
    SHALL display a concise description.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["revlink", "create", "--help"])
    assert result.exit_code == 0
    # The docstring mentions converting to a managed symlink
    assert "symlink" in result.output.lower() or "managed" in result.output.lower()


# ---------------------------------------------------------------------------
# Requirement 3.1 — non-existent source path
# ---------------------------------------------------------------------------


def test_revlink_nonexistent_path_exits_with_error(tmp_path: Path, monkeypatch, isolated_home: dict[str, str]) -> None:
    """Test that a non-existent source path produces an error and exits 1.

    Requirement 3.1: WHEN the path argument does not exist, THE Revlink_Command
    SHALL print a descriptive error message and exit with a non-zero status code
    without modifying the filesystem.
    """
    config_path, _managed, target = _write_mapping(tmp_path)
    monkeypatch.chdir(target)
    result = invoke_with_daemon(config_path, ["revlink", "create", "does_not_exist.txt"], isolated_home)

    assert result.exit_code == 1
    assert "Path does not exist" in result.output


# ---------------------------------------------------------------------------
# Requirement 3.2 — source is already a symlink
# ---------------------------------------------------------------------------


def test_revlink_symlink_source_outside_cwd_exits_with_error(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """A symlink whose target is outside CWD is rejected before adoption."""
    config_path, _managed, target = _write_mapping(tmp_path)
    real_file = tmp_path / "real.txt"
    real_file.write_text("content")
    symlink_path = target / "link.txt"
    symlink_path.symlink_to(real_file)
    monkeypatch.chdir(target)

    result = invoke_with_daemon(config_path, ["revlink", "create", "link.txt"], isolated_home)

    assert result.exit_code == 1
    assert "inside the current directory" in result.output.lower() or "already a symlink" in result.output.lower()


# ---------------------------------------------------------------------------
# Requirement 3.3 — dest exists without --force
# ---------------------------------------------------------------------------


def test_revlink_dest_exists_without_force_exits_with_error(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Test that an existing destination without --force produces an error.

    Requirement 3.3: WHEN the destination path in the managed project already
    exists and --force is not set, THE Revlink_Command SHALL print a descriptive
    error message and exit with a non-zero status code without modifying the
    filesystem.
    """
    config_path, managed, target = _write_mapping(tmp_path)
    (target / "myfile.txt").write_text("original content")
    (managed / "myfile.txt").write_text("old content")
    monkeypatch.chdir(target)

    result = invoke_with_daemon(config_path, ["revlink", "create", "myfile.txt"], isolated_home)

    assert result.exit_code == 1
    assert "Destination already exists" in result.output


# ---------------------------------------------------------------------------
# Requirement 3.3a — --force allows overwrite when dest exists
# ---------------------------------------------------------------------------


def test_revlink_force_allows_overwrite_when_dest_exists(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Test that --force bypasses the destination-exists pre-flight check.

    Requirement 3.3a: WHEN the destination path in the managed project already
    exists and --force is set, THE Revlink_Command SHALL overwrite the existing
    destination with the current content of the source path.
    """
    config_path, managed, target = _write_mapping(tmp_path)
    (target / "myfile.txt").write_text("original content")
    (managed / "myfile.txt").write_text("old content")
    monkeypatch.chdir(target)

    result = invoke_with_daemon(config_path, ["revlink", "create", "--force", "myfile.txt"], isolated_home)

    assert "Destination already exists" not in result.output
    assert result.exit_code == 0, result.output
    assert (managed / "myfile.txt").read_text() == "original content"


# ---------------------------------------------------------------------------
# Additional wiring: --dry-run passes validation and reports without mutating
# ---------------------------------------------------------------------------


def test_revlink_dry_run_does_not_modify_filesystem(tmp_path: Path, monkeypatch, isolated_home: dict[str, str]) -> None:
    """Test that --dry-run passes validation but leaves the filesystem unchanged.

    Requirement 3.4: WHEN --dry-run is active, THE Revlink_Command SHALL
    perform all validation checks and report what would happen, but SHALL NOT
    modify the filesystem.
    """
    config_path, managed, target = _write_mapping(tmp_path)
    source_file = target / "myfile.txt"
    source_file.write_text("content")
    monkeypatch.chdir(target)

    result = invoke_with_daemon(config_path, ["revlink", "create", "--dry-run", "myfile.txt"], isolated_home)

    assert result.exit_code == 0, result.output
    assert source_file.exists()
    assert not source_file.is_symlink()
    assert not (managed / "myfile.txt").exists()


def test_revlink_dry_run_prints_preview_output(tmp_path: Path, monkeypatch, isolated_home: dict[str, str]) -> None:
    """Test that --dry-run prints [dry-run]-prefixed preview lines for all steps.

    Requirement 7.6: WHEN --dry-run is active, THE Revlink_Command SHALL prefix
    all output lines with a [dry-run] indicator.
    """
    config_path, _managed, target = _write_mapping(tmp_path)
    (target / "myfile.txt").write_text("content")
    monkeypatch.chdir(target)

    result = invoke_with_daemon(config_path, ["revlink", "create", "--dry-run", "myfile.txt"], isolated_home)

    assert result.exit_code == 0, result.output
    assert "[dry-run]" in result.output
    assert "Copying" in result.output
    assert "Computing checksum" in result.output
    assert "MD5 checksum verified" in result.output
    assert "Target path left in place" in result.output


# ---------------------------------------------------------------------------
# Config resolution error paths (Requirement 2.4, 2.6)
# ---------------------------------------------------------------------------


def test_revlink_no_matching_project_exits_with_error(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Test that no matching project for CWD produces an error and exits 1.

    Requirement 2.4: WHEN no managed project's target paths match the CWD,
    THE Revlink_Command SHALL print a descriptive error message and exit 1.
    """
    config_path, _managed, _target = _write_mapping(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    (other / "myfile.txt").write_text("content")
    monkeypatch.chdir(other)

    result = invoke_with_daemon(config_path, ["revlink", "create", "myfile.txt"], isolated_home)

    assert result.exit_code == 1
    assert "No managed project found" in result.output


def test_revlink_ambiguous_project_exits_with_error(tmp_path: Path, monkeypatch, isolated_home: dict[str, str]) -> None:
    """A new path on a multi-hub target without a TTY choice lists names and exits 1.

    Create cannot pick a hub without an interview. Restore/remove resolve by
    PATH owner instead of this CWD-level failure.
    """
    first = tmp_path / "project-a"
    second = tmp_path / "project-b"
    target = tmp_path / "target"
    first.mkdir()
    second.mkdir()
    target.mkdir()
    (first / "a-only.txt").write_text("a\n")
    (second / "b-only.txt").write_text("b\n")
    (target / "a-only.txt").write_text("a\n")
    (target / "b-only.txt").write_text("b\n")
    (target / "myfile.txt").write_text("content")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"project-a:\n  target: {target}\n  subpath:\n    - a-only.txt\n"
        f"project-b:\n  target: {target}\n  subpath:\n    - b-only.txt\n"
    )
    monkeypatch.chdir(target)

    result = invoke_with_daemon(config_path, ["revlink", "create", "myfile.txt"], isolated_home)

    assert result.exit_code == 1
    assert "project-a" in result.output
    assert "project-b" in result.output
    assert not (first / "myfile.txt").exists()
    assert not (second / "myfile.txt").exists()
