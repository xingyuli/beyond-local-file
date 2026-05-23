"""End-to-end integration tests for the revlink command.

Covers Requirements 1.5, 4.1, 4.5, 5.2, 5.3, 6.1.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from beyond_local_file.cli import cli

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_config(config_path: Path, project_name: str, target_dir: Path) -> None:
    """Write a minimal revlink config file.

    The config format is ``project-name: /path/to/target``.  The managed
    project directory is resolved as ``config_dir / project-name``, so the
    caller must create that directory separately.

    Args:
        config_path: Destination path for the YAML config file.
        project_name: The project name key (also the managed dir name).
        target_dir: The target directory path to map to.
    """
    config_path.write_text(f"{project_name}: {target_dir}\n")


def _make_fake_git_repo(directory: Path) -> None:
    """Create a minimal fake git repository structure inside *directory*.

    Creates ``.git/`` and ``.git/info/`` so that ``GitExcludeManager``
    recognises the directory as a git repository.

    Args:
        directory: The directory to initialise as a fake git repo.
    """
    git_info = directory / ".git" / "info"
    git_info.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Happy path — file in a git repo
# ---------------------------------------------------------------------------


class TestRevlinkHappyPathFile:
    """End-to-end tests for the basic file revlink workflow.

    Requirements: 4.1, 5.2, 5.3, 6.1
    """

    def test_file_becomes_symlink_pointing_to_managed_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Test that a regular file is converted to a symlink in a git repo.

        Happy path: file in a temp git repo → revlink → symlink created,
        git exclude updated.

        Requirements 4.1, 5.2, 5.3, 6.1.
        """
        # Arrange
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        _make_fake_git_repo(target_dir)

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        source_file = target_dir / "myfile.txt"
        source_file.write_text("hello world")

        monkeypatch.chdir(target_dir)

        # Act
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "myfile.txt"],
            env=isolated_home,
        )

        # Assert
        assert result.exit_code == 0, result.output

        # The original path is now a symlink
        assert source_file.is_symlink(), "source path should be a symlink"

        # The symlink points to the managed dir copy
        managed_copy = managed_dir / "myfile.txt"
        assert source_file.resolve() == managed_copy.resolve()

        # The managed copy exists with the original content
        assert managed_copy.exists()
        assert managed_copy.read_text() == "hello world"

        # .git/info/exclude contains the filename
        exclude_file = target_dir / ".git" / "info" / "exclude"
        assert exclude_file.exists()
        assert "myfile.txt" in exclude_file.read_text()

    def test_symlink_target_is_absolute_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Test that the created symlink points to an absolute path.

        Requirement 5.2: THE Revlink_Command SHALL create a symlink at the
        original path pointing to the managed project copy.
        """
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        _make_fake_git_repo(target_dir)

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        source_file = target_dir / "data.txt"
        source_file.write_text("data")

        monkeypatch.chdir(target_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "data.txt"],
            env=isolated_home,
        )

        assert result.exit_code == 0, result.output
        assert source_file.is_symlink()
        # The symlink target should be an absolute path
        assert source_file.readlink().is_absolute()


# ---------------------------------------------------------------------------
# Directory tree
# ---------------------------------------------------------------------------


class TestRevlinkDirectoryTree:
    """End-to-end tests for directory revlink.

    Requirements: 4.1, 5.2, 5.3
    """

    def test_directory_becomes_symlink(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Test that a directory is converted to a symlink pointing to managed dir.

        Directory tree: directory → revlink → symlink created.

        Requirements 4.1, 5.2, 5.3.
        """
        # Arrange
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        # Create a directory with files inside the target dir
        source_dir = target_dir / "mydir"
        source_dir.mkdir()
        (source_dir / "file_a.txt").write_text("content a")
        (source_dir / "file_b.txt").write_text("content b")
        subdir = source_dir / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("nested content")

        monkeypatch.chdir(target_dir)

        # Act
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "mydir"],
            env=isolated_home,
        )

        # Assert
        assert result.exit_code == 0, result.output

        # The original path is now a symlink
        assert source_dir.is_symlink(), "source directory should be a symlink"

        # The symlink points to the managed dir copy
        managed_copy = managed_dir / "mydir"
        assert source_dir.resolve() == managed_copy.resolve()

        # The managed copy exists with all original files
        assert managed_copy.is_dir()
        assert (managed_copy / "file_a.txt").read_text() == "content a"
        assert (managed_copy / "file_b.txt").read_text() == "content b"
        assert (managed_copy / "subdir" / "nested.txt").read_text() == "nested content"

    def test_directory_original_content_preserved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Test that directory contents are accessible via the symlink after revlink.

        Requirement 4.1: THE Revlink_Command SHALL copy the source directory
        tree to the destination path, preserving all file contents and
        directory structure.
        """
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        source_dir = target_dir / "configs"
        source_dir.mkdir()
        (source_dir / "settings.json").write_text('{"key": "value"}')

        monkeypatch.chdir(target_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "configs"],
            env=isolated_home,
        )

        assert result.exit_code == 0, result.output

        # Content accessible through the symlink
        assert (source_dir / "settings.json").read_text() == '{"key": "value"}'


# ---------------------------------------------------------------------------
# --force end-to-end
# ---------------------------------------------------------------------------


class TestRevlinkForce:
    """End-to-end tests for the --force flag.

    Requirements: 4.5
    """

    def test_force_overwrites_existing_managed_copy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Test that --force overwrites an existing destination in the managed dir.

        --force end-to-end: existing destination overwritten, symlink created.

        Requirement 4.5: WHEN --force is set and the destination already exists,
        THE Revlink_Command SHALL overwrite it before copying, then apply MD5
        verification as normal.
        """
        # Arrange
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        # Create source file in target dir
        source_file = target_dir / "myfile.txt"
        source_file.write_text("new content")

        # Pre-create destination in managed dir with different content
        dest_file = managed_dir / "myfile.txt"
        dest_file.write_text("old content")

        monkeypatch.chdir(target_dir)

        # Act
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "--force", "myfile.txt"],
            env=isolated_home,
        )

        # Assert
        assert result.exit_code == 0, result.output

        # Symlink created at original location
        assert source_file.is_symlink()

        # Managed copy has the new content (old content was overwritten)
        assert dest_file.read_text() == "new content"

    def test_force_without_existing_dest_still_works(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Test that --force works even when no existing destination is present.

        Requirement 4.5: --force should not fail when the destination does not
        already exist.
        """
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        source_file = target_dir / "fresh.txt"
        source_file.write_text("fresh content")

        monkeypatch.chdir(target_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "--force", "fresh.txt"],
            env=isolated_home,
        )

        assert result.exit_code == 0, result.output
        assert source_file.is_symlink()
        assert (managed_dir / "fresh.txt").read_text() == "fresh content"


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------


class TestRevlinkConfigResolution:
    """End-to-end tests for config resolution paths.

    Requirements: 1.5
    """

    def test_explicit_config_flag_resolves_correctly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Test that --config flag resolves the config from a non-default path.

        Requirement 1.5: THE Revlink_Command SHALL accept a -c / --config option
        to specify a custom config file path.
        """
        # Config at a non-default path
        config_dir = tmp_path / "configs"
        config_dir.mkdir()
        config_path = config_dir / "custom.yml"

        target_dir = tmp_path / "target"
        target_dir.mkdir()

        # Managed dir must be relative to config file's directory
        managed_dir = config_dir / "my-project"
        managed_dir.mkdir()

        config_path.write_text(f"my-project: {target_dir}\n")

        source_file = target_dir / "file.txt"
        source_file.write_text("content")

        monkeypatch.chdir(target_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "file.txt"],
            env=isolated_home,
        )

        assert result.exit_code == 0, result.output
        assert source_file.is_symlink()

    def test_default_config_yml_in_cwd_resolves_correctly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Test that config.yml in the CWD is used when no --config flag is given.

        Requirement 2.1: THE Revlink_Command SHALL load the config using the
        same resolution order as other BLF commands: explicit --config flag,
        then ~/.blfrc, then config.yml in the current directory.
        """
        # Place config.yml in the target dir (which will be the CWD)
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        # Managed dir must be relative to config file's directory (target_dir)
        managed_dir = target_dir / "my-project"
        managed_dir.mkdir()

        config_path = target_dir / "config.yml"
        config_path.write_text(f"my-project: {target_dir}\n")

        source_file = target_dir / "notes.txt"
        source_file.write_text("my notes")

        # CWD is the target dir — config.yml is found there automatically
        monkeypatch.chdir(target_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["revlink", "notes.txt"],
            env=isolated_home,
        )

        assert result.exit_code == 0, result.output
        assert source_file.is_symlink()
        assert (managed_dir / "notes.txt").read_text() == "my notes"

    def test_blfrc_config_resolves_correctly(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that config referenced via ~/.blfrc is used for revlink.

        Requirement 2.1: THE Revlink_Command SHALL load the config using the
        same resolution order as other BLF commands, including ~/.blfrc.
        """
        # Set up isolated home with a .blfrc pointing to our config
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        monkeypatch.setenv("BLF_HOME", str(home_dir))
        env = {"BLF_HOME": str(home_dir)}

        target_dir = tmp_path / "target"
        target_dir.mkdir()

        # Config lives next to managed dir
        config_path = tmp_path / "config.yml"
        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()
        config_path.write_text(f"my-project: {target_dir}\n")

        # Write .blfrc pointing to our config
        blfrc = home_dir / ".blfrc"
        blfrc.write_text(f"config_file: {config_path}\n")

        source_file = target_dir / "readme.txt"
        source_file.write_text("readme content")

        monkeypatch.chdir(target_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["revlink", "readme.txt"],
            env=env,
        )

        assert result.exit_code == 0, result.output
        assert source_file.is_symlink()
        assert (managed_dir / "readme.txt").read_text() == "readme content"
