"""Unit tests for the revlink restore CLI wiring and pre-flight validation.

Covers Requirements 1.4, 1.7, 3.1, 3.2, 3.3, 3.4.
"""

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from beyond_local_file.cli import cli
from beyond_local_file.model.config import ConfigProject, Mapping
from beyond_local_file.operations.revlink import RevlinkContext

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


def test_restore_nonexistent_path_exits_with_error(tmp_path: Path) -> None:
    """Test that a non-existent path produces an error message and exits 1.

    Requirement 3.1: WHEN the path argument does not exist, THE Restore_Command
    SHALL print a descriptive error message and exit with a non-zero status code
    without modifying the filesystem.
    """
    runner = CliRunner()
    managed_dir = tmp_path / "managed"
    managed_dir.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    nonexistent = target_dir / "does_not_exist.txt"
    ctx = _make_revlink_context(managed_dir, target_dir, tmp_path / "config.yml")

    with (
        patch("beyond_local_file.cli.resolve_revlink_context", return_value=ctx),
        patch("beyond_local_file.cli.Path.cwd", return_value=target_dir),
    ):
        result = runner.invoke(cli, ["revlink", "restore", str(nonexistent)])

    assert result.exit_code == 1
    assert "Path does not exist" in result.output
    # Filesystem must be unchanged — no files created
    assert not nonexistent.exists()


# ---------------------------------------------------------------------------
# Requirement 3.2 — path exists but is not a symlink → error + exit 1
# ---------------------------------------------------------------------------


def test_restore_real_file_exits_with_error_and_suggests_create(tmp_path: Path) -> None:
    """Test that a real file (not a symlink) produces an error suggesting revlink create.

    Requirement 3.2: WHEN the path argument exists but is not a symlink, THE
    Restore_Command SHALL print a descriptive error message suggesting
    ``revlink create`` instead, and exit with a non-zero status code without
    modifying the filesystem.
    """
    runner = CliRunner()
    managed_dir = tmp_path / "managed"
    managed_dir.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    # A plain file — not a symlink
    real_file = target_dir / "myfile.txt"
    real_file.write_text("original content")

    ctx = _make_revlink_context(managed_dir, target_dir, tmp_path / "config.yml")

    with (
        patch("beyond_local_file.cli.resolve_revlink_context", return_value=ctx),
        patch("beyond_local_file.cli.Path.cwd", return_value=target_dir),
    ):
        result = runner.invoke(cli, ["revlink", "restore", str(real_file)])

    assert result.exit_code == 1
    assert "not a symlink" in result.output.lower()
    assert "revlink create" in result.output
    # File must be untouched
    assert real_file.read_text() == "original content"


# ---------------------------------------------------------------------------
# Requirement 3.3 — dangling symlink (managed copy missing) → error + exit 1
# ---------------------------------------------------------------------------


def test_restore_dangling_symlink_exits_with_error(tmp_path: Path) -> None:
    """Test that a symlink whose managed copy is missing produces an error.

    Requirement 3.3: WHEN the path is a symlink but its target (the
    Managed_Copy) does not exist, THE Restore_Command SHALL print a descriptive
    error message indicating a dangling symlink, and exit with a non-zero
    status code without modifying the filesystem.

    The CLI resolves the path via ``Path(path).resolve()`` which follows
    symlinks.  For a dangling symlink the resolved path is the non-existent
    target, so we patch ``Path.resolve`` to return the symlink path itself
    (without following it), matching the intent of the restore operation.
    """
    runner = CliRunner()
    managed_dir = tmp_path / "managed"
    managed_dir.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    # Create a symlink pointing to a non-existent managed copy
    missing_managed = managed_dir / "myfile.txt"
    symlink_path = target_dir / "myfile.txt"
    symlink_path.symlink_to(missing_managed)  # dangling — target doesn't exist

    ctx = _make_revlink_context(managed_dir, target_dir, tmp_path / "config.yml")

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
        result = runner.invoke(cli, ["revlink", "restore", str(symlink_path)])

    assert result.exit_code == 1
    assert "dangling symlink" in result.output.lower() or "managed copy does not exist" in result.output.lower()
    # The symlink must still be in place — no filesystem changes
    assert symlink_path.is_symlink()


# ---------------------------------------------------------------------------
# Requirement 3.4 — --dry-run is accepted; exit 0, no filesystem changes
# ---------------------------------------------------------------------------


def test_restore_dry_run_accepted_and_exits_zero(tmp_path: Path) -> None:
    """Test that --dry-run is accepted, exits 0, and makes no filesystem changes.

    Requirement 3.4: WHEN --dry-run is active, THE Restore_Command SHALL
    perform all validation checks and report what would happen, but SHALL NOT
    modify the filesystem.

    The CLI resolves the path via ``Path(path).resolve()`` which follows
    symlinks.  We patch ``Path.resolve`` to return the symlink path itself so
    that ``RestoreOperation._validate`` sees a symlink, not the managed copy.
    """
    runner = CliRunner()
    managed_dir = tmp_path / "managed"
    managed_dir.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    # Set up a valid symlink pointing to an existing managed copy
    managed_file = managed_dir / "myfile.txt"
    managed_file.write_text("managed content")
    symlink_path = target_dir / "myfile.txt"
    symlink_path.symlink_to(managed_file)

    ctx = _make_revlink_context(managed_dir, target_dir, tmp_path / "config.yml")

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
        result = runner.invoke(cli, ["revlink", "restore", "--dry-run", str(symlink_path)])

    assert result.exit_code == 0
    # Symlink must still be in place — no filesystem changes
    assert symlink_path.is_symlink()
    # Managed copy must still exist
    assert managed_file.exists()
    assert managed_file.read_text() == "managed content"


def test_restore_dry_run_prints_dry_run_prefixed_output(tmp_path: Path) -> None:
    """Test that --dry-run prints [dry-run]-prefixed preview lines.

    Requirement 3.4 / Requirement 7.10: WHEN --dry-run is active, THE
    Restore_Command SHALL prefix all output lines with [dry-run].

    The CLI resolves the path via ``Path(path).resolve()`` which follows
    symlinks.  We patch ``Path.resolve`` to return the symlink path itself so
    that ``RestoreOperation._validate`` sees a symlink, not the managed copy.
    """
    runner = CliRunner()
    managed_dir = tmp_path / "managed"
    managed_dir.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    managed_file = managed_dir / "myfile.txt"
    managed_file.write_text("managed content")
    symlink_path = target_dir / "myfile.txt"
    symlink_path.symlink_to(managed_file)

    ctx = _make_revlink_context(managed_dir, target_dir, tmp_path / "config.yml")

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
        result = runner.invoke(cli, ["revlink", "restore", "--dry-run", str(symlink_path)])

    assert result.exit_code == 0
    assert "[dry-run]" in result.output
