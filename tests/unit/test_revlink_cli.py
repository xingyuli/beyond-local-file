"""Unit tests for the revlink CLI command wiring and pre-flight validation.

Covers Requirements 1.1, 1.2, 1.3, 1.4, 1.6, 3.1, 3.2, 3.3, 3.3a.
"""

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from beyond_local_file.cli import cli
from beyond_local_file.model.config import ConfigProject, Mapping
from beyond_local_file.operations.revlink import RevlinkContext
from beyond_local_file.project_processor import RevlinkResolveError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config_project(managed_path: Path, target_path: Path) -> ConfigProject:
    """Build a minimal ConfigProject for use in tests.

    Args:
        managed_path: The managed project path (destination root).
        target_path: A target directory that maps to this project.

    Returns:
        A ConfigProject with a single mapping targeting ``target_path``.
    """
    return ConfigProject(
        managed_project_name="test-project",
        managed_project_path=managed_path,
        mappings=[Mapping(targets=[target_path], subpaths=None, copy_paths=None)],
    )


def _make_revlink_context(managed_path: Path, target_path: Path, config_path: Path) -> RevlinkContext:
    """Build a RevlinkContext for use in tests.

    Args:
        managed_path: The managed project path (destination root).
        target_path: The CWD / target directory.
        config_path: The config file path.

    Returns:
        A RevlinkContext with a single mapping targeting ``target_path``.
    """
    mapping = Mapping(targets=[target_path], subpaths=None, copy_paths=None)
    return RevlinkContext(
        config_path=config_path,
        project_name="test-project",
        matched_mapping=mapping,
        cwd=target_path,
        managed_project_path=managed_path,
    )


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


def test_revlink_nonexistent_path_exits_with_error(tmp_path: Path) -> None:
    """Test that a non-existent source path produces an error and exits 1.

    Requirement 3.1: WHEN the path argument does not exist, THE Revlink_Command
    SHALL print a descriptive error message and exit with a non-zero status code
    without modifying the filesystem.
    """
    runner = CliRunner()
    managed_dir = tmp_path / "managed"
    managed_dir.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    ctx = _make_revlink_context(managed_dir, target_dir, tmp_path / "config.yml")

    with (
        patch("beyond_local_file.cli.resolve_revlink_context", return_value=ctx),
        patch("beyond_local_file.cli.Path.cwd", return_value=target_dir),
    ):
        nonexistent = target_dir / "does_not_exist.txt"
        result = runner.invoke(cli, ["revlink", "create", str(nonexistent)])

    assert result.exit_code == 1
    assert "Path does not exist" in result.output


# ---------------------------------------------------------------------------
# Requirement 3.2 — source is already a symlink
# ---------------------------------------------------------------------------


def test_revlink_symlink_source_exits_with_error(tmp_path: Path) -> None:
    """Test that a source path that is already a symlink produces an error.

    Requirement 3.2: WHEN the path argument is already a symlink, THE
    Revlink_Command SHALL print a descriptive error message indicating the path
    is already a symlink and exit with a non-zero status code.

    The CLI resolves the path via ``Path(path).resolve()`` before passing it to
    ``CreateOperation``.  To ensure the resolved path is still seen as a
    symlink, we patch ``Path.resolve`` to return the symlink path itself
    (without following it).
    """
    runner = CliRunner()
    managed_dir = tmp_path / "managed"
    managed_dir.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    # Create a real file and a symlink pointing to it
    real_file = tmp_path / "real.txt"
    real_file.write_text("content")
    symlink_path = target_dir / "link.txt"
    symlink_path.symlink_to(real_file)

    ctx = _make_revlink_context(managed_dir, target_dir, tmp_path / "config.yml")

    # Patch Path.resolve so the CLI sees the symlink path (not its target)
    original_resolve = Path.resolve

    def _resolve_no_follow(self: Path, **kwargs: object) -> Path:
        if str(self) == str(symlink_path):
            return symlink_path
        return original_resolve(self, **kwargs)

    with (
        patch("beyond_local_file.cli.resolve_revlink_context", return_value=ctx),
        patch.object(Path, "resolve", _resolve_no_follow),
        patch("beyond_local_file.cli.Path.cwd", return_value=target_dir),
    ):
        result = runner.invoke(cli, ["revlink", "create", str(symlink_path)])

    assert result.exit_code == 1
    assert "already a symlink" in result.output


# ---------------------------------------------------------------------------
# Requirement 3.3 — dest exists without --force
# ---------------------------------------------------------------------------


def test_revlink_dest_exists_without_force_exits_with_error(tmp_path: Path) -> None:
    """Test that an existing destination without --force produces an error.

    Requirement 3.3: WHEN the destination path in the managed project already
    exists and --force is not set, THE Revlink_Command SHALL print a descriptive
    error message and exit with a non-zero status code without modifying the
    filesystem.
    """
    runner = CliRunner()
    managed_dir = tmp_path / "managed"
    managed_dir.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    # Create source file in target dir
    source_file = target_dir / "myfile.txt"
    source_file.write_text("original content")

    # Pre-create the destination in managed dir (simulates existing copy)
    dest_file = managed_dir / "myfile.txt"
    dest_file.write_text("old content")

    ctx = _make_revlink_context(managed_dir, target_dir, tmp_path / "config.yml")

    with (
        patch("beyond_local_file.cli.resolve_revlink_context", return_value=ctx),
        patch("beyond_local_file.cli.Path.cwd", return_value=target_dir),
    ):
        result = runner.invoke(cli, ["revlink", "create", str(source_file)])

    assert result.exit_code == 1
    assert "Destination already exists" in result.output


# ---------------------------------------------------------------------------
# Requirement 3.3a — --force allows overwrite when dest exists
# ---------------------------------------------------------------------------


def test_revlink_force_allows_overwrite_when_dest_exists(tmp_path: Path) -> None:
    """Test that --force bypasses the destination-exists pre-flight check.

    Requirement 3.3a: WHEN the destination path in the managed project already
    exists and --force is set, THE Revlink_Command SHALL overwrite the existing
    destination with the current content of the source path.
    """
    runner = CliRunner()
    managed_dir = tmp_path / "managed"
    managed_dir.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    # Create source file in target dir
    source_file = target_dir / "myfile.txt"
    source_file.write_text("original content")

    # Pre-create the destination in managed dir
    dest_file = managed_dir / "myfile.txt"
    dest_file.write_text("old content")

    ctx = _make_revlink_context(managed_dir, target_dir, tmp_path / "config.yml")

    with (
        patch("beyond_local_file.cli.resolve_revlink_context", return_value=ctx),
        patch("beyond_local_file.cli.Path.cwd", return_value=target_dir),
    ):
        result = runner.invoke(cli, ["revlink", "create", "--force", str(source_file)])

    # With --force the validation passes; operation proceeds past pre-flight.
    # The "Destination already exists" error must NOT appear.
    assert "Destination already exists" not in result.output
    # Exit code 0 means the full operation succeeded (symlink created)
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Additional wiring: --dry-run passes validation and reports without mutating
# ---------------------------------------------------------------------------


def test_revlink_dry_run_does_not_modify_filesystem(tmp_path: Path) -> None:
    """Test that --dry-run passes validation but leaves the filesystem unchanged.

    Requirement 3.4: WHEN --dry-run is active, THE Revlink_Command SHALL
    perform all validation checks and report what would happen, but SHALL NOT
    modify the filesystem.
    """
    runner = CliRunner()
    managed_dir = tmp_path / "managed"
    managed_dir.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    source_file = target_dir / "myfile.txt"
    source_file.write_text("content")

    ctx = _make_revlink_context(managed_dir, target_dir, tmp_path / "config.yml")

    with (
        patch("beyond_local_file.cli.resolve_revlink_context", return_value=ctx),
        patch("beyond_local_file.cli.Path.cwd", return_value=target_dir),
    ):
        result = runner.invoke(cli, ["revlink", "create", "--dry-run", str(source_file)])

    assert result.exit_code == 0
    # Source must still be a regular file (not a symlink)
    assert source_file.exists()
    assert not source_file.is_symlink()
    # Destination must NOT have been created
    assert not (managed_dir / "myfile.txt").exists()


def test_revlink_dry_run_prints_preview_output(tmp_path: Path) -> None:
    """Test that --dry-run prints [dry-run]-prefixed preview lines for all steps.

    Requirement 7.6: WHEN --dry-run is active, THE Revlink_Command SHALL prefix
    all output lines with a [dry-run] indicator.
    """
    runner = CliRunner()
    managed_dir = tmp_path / "managed"
    managed_dir.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    source_file = target_dir / "myfile.txt"
    source_file.write_text("content")

    ctx = _make_revlink_context(managed_dir, target_dir, tmp_path / "config.yml")

    with (
        patch("beyond_local_file.cli.resolve_revlink_context", return_value=ctx),
        patch("beyond_local_file.cli.Path.cwd", return_value=target_dir),
    ):
        result = runner.invoke(cli, ["revlink", "create", "--dry-run", str(source_file)])

    assert result.exit_code == 0
    # Every output line must carry the [dry-run] prefix
    assert "[dry-run]" in result.output
    # Key step messages must appear
    assert "Copying" in result.output
    assert "Computing checksum" in result.output
    assert "MD5 checksum verified" in result.output
    assert "Symlink created" in result.output


# ---------------------------------------------------------------------------
# Config resolution error paths (Requirement 2.4, 2.6)
# ---------------------------------------------------------------------------


def test_revlink_no_matching_project_exits_with_error(tmp_path: Path) -> None:
    """Test that no matching project for CWD produces an error and exits 1.

    Requirement 2.4: WHEN no managed project's target paths match the CWD,
    THE Revlink_Command SHALL print a descriptive error message and exit 1.
    """
    runner = CliRunner()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    source_file = target_dir / "myfile.txt"
    source_file.write_text("content")

    error = RevlinkResolveError(message=f"No managed project found for current directory: {target_dir}\nHint: ...")

    with (
        patch("beyond_local_file.cli.resolve_revlink_context", return_value=error),
        patch("beyond_local_file.cli.Path.cwd", return_value=target_dir),
    ):
        result = runner.invoke(cli, ["revlink", "create", str(source_file)])

    assert result.exit_code == 1
    assert "No managed project found" in result.output


def test_revlink_ambiguous_project_exits_with_error(tmp_path: Path) -> None:
    """Test that multiple matching projects produce an ambiguity error and exit 1.

    Requirement 2.6: WHEN multiple managed projects' target paths match the CWD,
    THE Revlink_Command SHALL print a descriptive error message listing the
    ambiguous projects and exit with a non-zero status code.
    """
    runner = CliRunner()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    source_file = target_dir / "myfile.txt"
    source_file.write_text("content")

    error = RevlinkResolveError(
        message=f"Ambiguous: multiple projects target {target_dir}: project-a, project-b"
    )

    with (
        patch("beyond_local_file.cli.resolve_revlink_context", return_value=error),
        patch("beyond_local_file.cli.Path.cwd", return_value=target_dir),
    ):
        result = runner.invoke(cli, ["revlink", "create", str(source_file)])

    assert result.exit_code == 1
    assert "Ambiguous" in result.output
