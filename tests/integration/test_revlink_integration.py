"""End-to-end integration tests for the revlink command.

Covers Requirements 1.5, 2.1, 2.2, 4.1, 4.5, 5.2, 5.3, 6.1.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from beyond_local_file.cli import cli
from beyond_local_file.model.config import ConfigProject, Mapping
from beyond_local_file.project_processor import ConfigLoadResult

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
            ["--config", str(config_path), "revlink", "create", "myfile.txt"],
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
            ["--config", str(config_path), "revlink", "create", "data.txt"],
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
            ["--config", str(config_path), "revlink", "create", "mydir"],
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
            ["--config", str(config_path), "revlink", "create", "configs"],
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
            ["--config", str(config_path), "revlink", "create", "--force", "myfile.txt"],
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
            ["--config", str(config_path), "revlink", "create", "--force", "fresh.txt"],
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
            ["--config", str(config_path), "revlink", "create", "file.txt"],
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
            ["revlink", "create", "notes.txt"],
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
            ["revlink", "create", "readme.txt"],
            env=env,
        )

        assert result.exit_code == 0, result.output
        assert source_file.is_symlink()
        assert (managed_dir / "readme.txt").read_text() == "readme content"


# ---------------------------------------------------------------------------
# Config subpath update
# ---------------------------------------------------------------------------


class TestRevlinkConfigUpdate:
    """Integration tests for automatic config subpath update.

    When the matched mapping uses selective sync (subpath list), revlink must
    add the adopted item to that list so link sync and link check will manage
    it going forward.
    """

    def _write_subpath_config(
        self, config_path: Path, project_name: str, target_dir: Path, subpaths: list[str]
    ) -> None:
        """Write a config with a dict-mapping that has a subpath list.

        Args:
            config_path: Destination path for the YAML config file.
            project_name: The project name key.
            target_dir: The target directory path to map to.
            subpaths: Initial list of subpath entries.
        """
        subpath_yaml = "\n".join(f"    - {s}" for s in subpaths)
        # fmt: off
        config_path.write_text(
            f"{project_name}:\n"
            f"  target: {target_dir}\n"
            f"  subpath:\n"
            f"{subpath_yaml}\n"
        )
        # fmt: on

    def test_subpath_entry_added_when_mapping_has_subpath_list(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """revlink adds the adopted item to the config subpath list.

        When the matched mapping already has a subpath list, the new item must
        be appended so that link sync will manage it.
        """
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        self._write_subpath_config(config_path, "my-project", target_dir, [".kiro/hooks"])

        source_file = target_dir / "newfile.txt"
        source_file.write_text("content")

        monkeypatch.chdir(target_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "create", "newfile.txt"],
            env=isolated_home,
        )

        assert result.exit_code == 0, result.output
        assert source_file.is_symlink()

        # Config must now contain the new entry
        updated = config_path.read_text()
        assert "newfile.txt" in updated

    def test_no_config_update_when_mapping_has_no_subpath(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """revlink does not modify the config when the mapping syncs everything.

        A string mapping (no subpath) already covers all items — no update needed.
        """
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)
        original_content = config_path.read_text()

        source_file = target_dir / "newfile.txt"
        source_file.write_text("content")

        monkeypatch.chdir(target_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "create", "newfile.txt"],
            env=isolated_home,
        )

        assert result.exit_code == 0, result.output
        assert config_path.read_text() == original_content, "config must not be modified for sync-all mapping"

    def test_subpath_entry_not_duplicated_when_already_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """revlink rejects create when the path is already a declared subpath.

        Rule 5 detects that ``newfile.txt`` is already in the subpath list and
        exits 1 with an informative error.  The config must remain unchanged.
        """
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        self._write_subpath_config(config_path, "my-project", target_dir, [".kiro/hooks", "newfile.txt"])
        original_content = config_path.read_text()

        source_file = target_dir / "newfile.txt"
        source_file.write_text("content")

        monkeypatch.chdir(target_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "create", "newfile.txt"],
            env=isolated_home,
        )

        # Rule 5: path already declared as a subpath → exit 1 with error
        assert result.exit_code == 1, result.output
        assert "already a declared subpath" in result.output

        # Config must remain unchanged — no duplication, no removal
        assert config_path.read_text() == original_content

    def test_comments_and_blank_lines_preserved_after_update(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Comments and blank lines in the config file survive a subpath update."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        config_path.write_text(
            f"# Shared dev configs\n"
            f"my-project:\n"
            f"  target: {target_dir}\n"
            f"  subpath:\n"
            f"    - .kiro/hooks  # AI hooks\n"
            f"\n"
            f"    - .vscode\n"
        )

        source_file = target_dir / "newfile.txt"
        source_file.write_text("content")

        monkeypatch.chdir(target_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "create", "newfile.txt"],
            env=isolated_home,
        )

        assert result.exit_code == 0, result.output
        updated = config_path.read_text()
        assert "# Shared dev configs" in updated, "top-level comment must be preserved"
        assert "# AI hooks" in updated, "inline comment must be preserved"
        assert "newfile.txt" in updated, "new entry must be present"


# ---------------------------------------------------------------------------
# Nested path handling
# ---------------------------------------------------------------------------


class TestRevlinkNestedPath:
    """Integration tests for nested path handling in revlink create.

    Validates that a path like ``.kiro/specs/foo`` is managed at the correct
    nested location inside the managed project directory, not at the basename.

    Requirements: 1.2, 1.3, 1.4, 4.2
    """

    def _make_config_project(self, managed_path: Path, target_path: Path) -> ConfigProject:
        """Build a ConfigProject with a selective sync mapping (empty subpath list).

        Args:
            managed_path: The managed project path (destination root).
            target_path: A target directory that maps to this project.

        Returns:
            A ConfigProject with a single selective-sync mapping targeting
            ``target_path`` and an empty subpath list.
        """
        return ConfigProject(
            managed_project_name="test-project",
            managed_project_path=managed_path,
            mappings=[Mapping(targets=[target_path], subpaths=[], copy_paths=None)],
        )

    def test_nested_path_managed_copy_at_correct_location(self, tmp_path: Path) -> None:
        """revlink create with a nested path places the managed copy at the full rel_path.

        Given a source at ``target/.kiro/specs/foo``, the managed copy must land
        at ``managed/.kiro/specs/foo``, not ``managed/foo``.

        Requirements 1.2, 1.3, 1.4.
        """
        # Arrange
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "managed"
        managed_dir.mkdir()

        # Write a real config file so the config update step can read it
        config_path = tmp_path / "config.yml"
        config_path.write_text(f"test-project:\n  target: {target_dir}\n  subpath: []\n")

        # Create a minimal git repo structure so GitExcludeManager can write the exclude entry
        _make_fake_git_repo(target_dir)

        # Create the nested source file
        source_dir = target_dir / ".kiro" / "specs"
        source_dir.mkdir(parents=True)
        source_file = source_dir / "foo"
        source_file.write_text("spec content")

        project = self._make_config_project(managed_dir, target_dir)

        runner = CliRunner()
        with (
            patch("beyond_local_file.cli.load_config_projects") as mock_load,
            patch("beyond_local_file.cli.resolve_project_from_cwd") as mock_resolve,
            patch("beyond_local_file.cli.Path.cwd", return_value=target_dir),
        ):
            mock_load.return_value = ConfigLoadResult(
                projects={"test-project": project},
                config_file=config_path,
            )
            mock_resolve.return_value = project

            # Act — invoke with the absolute path (Path.cwd is mocked, so
            # Path(path).resolve() in cli.py will resolve against the real OS
            # CWD; passing the absolute path avoids that ambiguity)
            result = runner.invoke(cli, ["revlink", "create", str(source_file)])

        # Assert: exit code 0
        assert result.exit_code == 0, result.output

        # Assert: managed copy at managed/.kiro/specs/foo (not managed/foo)
        managed_copy = managed_dir / ".kiro" / "specs" / "foo"
        assert managed_copy.exists(), f"managed copy not found at {managed_copy}"
        assert managed_copy.read_text() == "spec content"

        # Assert: symlink at target/.kiro/specs/foo pointing to managed/.kiro/specs/foo
        assert source_file.is_symlink(), "source path should be a symlink after revlink create"
        assert source_file.resolve() == managed_copy.resolve()

        # Assert: config subpath list contains .kiro/specs/foo
        updated_config = config_path.read_text()
        assert ".kiro/specs/foo" in updated_config

    def test_nested_path_config_subpath_entry_uses_full_rel_path(self, tmp_path: Path) -> None:
        """revlink create adds the full rel_path to the config subpath list.

        The config entry must be ``.kiro/specs/foo``, not ``foo``.

        Requirement 4.2.
        """
        # Arrange
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "managed"
        managed_dir.mkdir()

        # Write a real config file so the config update can be verified
        config_path = tmp_path / "config.yml"
        config_path.write_text(f"test-project:\n  target: {target_dir}\n  subpath: []\n")

        source_dir = target_dir / ".kiro" / "specs"
        source_dir.mkdir(parents=True)
        source_file = source_dir / "foo"
        source_file.write_text("spec content")

        project = ConfigProject(
            managed_project_name="test-project",
            managed_project_path=managed_dir,
            mappings=[Mapping(targets=[target_dir], subpaths=[], copy_paths=None)],
        )

        runner = CliRunner()
        with (
            patch("beyond_local_file.cli.load_config_projects") as mock_load,
            patch("beyond_local_file.cli.resolve_project_from_cwd") as mock_resolve,
            patch("beyond_local_file.cli.Path.cwd", return_value=target_dir),
        ):
            mock_load.return_value = ConfigLoadResult(
                projects={"test-project": project},
                config_file=config_path,
            )
            mock_resolve.return_value = project

            # Act — pass the absolute path (same reason as the first test)
            result = runner.invoke(cli, ["revlink", "create", str(source_file)])

        assert result.exit_code == 0, result.output

        # Assert: config subpath list contains the full rel_path, not just the basename
        updated_config = config_path.read_text()
        assert ".kiro/specs/foo" in updated_config, f"Expected '.kiro/specs/foo' in config, got:\n{updated_config}"
        assert updated_config.count("foo") == 1, (
            "Only the full path entry should appear — basename 'foo' must not be added separately"
        )


# ---------------------------------------------------------------------------
# Nested path handling — revlink restore
# ---------------------------------------------------------------------------


class TestRevlinkRestoreNestedPath:
    """Integration tests for ``revlink restore`` with a nested path argument.

    Verifies that the managed copy is looked up at the full relative path
    (e.g. ``managed/.kiro/specs/foo``) rather than just the basename
    (``managed/foo``), and that the real file is restored at the correct
    location in the target directory.

    Requirements: 2.1, 2.2
    """

    def _write_subpath_config(
        self,
        config_path: Path,
        project_name: str,
        target_dir: Path,
        subpaths: list[str],
    ) -> None:
        """Write a config with a dict-mapping that has a subpath list.

        Args:
            config_path: Destination path for the YAML config file.
            project_name: The project name key.
            target_dir: The target directory path to map to.
            subpaths: Initial list of subpath entries.
        """
        subpath_yaml = "\n".join(f"    - {s}" for s in subpaths)
        config_path.write_text(f"{project_name}:\n  target: {target_dir}\n  subpath:\n{subpath_yaml}\n")

    def test_restore_nested_path_real_file_at_target(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Real file is restored at ``target/.kiro/specs/foo`` after restore.

        Set up a managed copy at ``managed/.kiro/specs/foo`` and a symlink at
        ``target/.kiro/specs/foo`` pointing to it.  Run ``revlink restore
        .kiro/specs/foo`` from the target directory.  The symlink must be
        replaced with a real file containing the original content.

        Requirements 2.1, 2.2.
        """
        # Arrange
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        self._write_subpath_config(config_path, "my-project", target_dir, [".kiro/specs/foo"])

        # Set up the managed copy at the full nested path
        managed_copy = managed_dir / ".kiro" / "specs" / "foo"
        managed_copy.parent.mkdir(parents=True, exist_ok=True)
        managed_copy.write_text("spec content")

        # Set up the symlink at the nested path inside target_dir
        symlink_path = target_dir / ".kiro" / "specs" / "foo"
        symlink_path.parent.mkdir(parents=True, exist_ok=True)
        symlink_path.symlink_to(managed_copy)

        monkeypatch.chdir(target_dir)

        # Act
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "restore", ".kiro/specs/foo"],
            env=isolated_home,
        )

        # Assert
        assert result.exit_code == 0, result.output

        # The path is now a real file, not a symlink
        assert not symlink_path.is_symlink(), "path should no longer be a symlink"
        assert symlink_path.is_file(), "path should be a real file"
        assert symlink_path.read_text() == "spec content"

    def test_restore_nested_path_managed_copy_deleted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Managed copy at ``managed/.kiro/specs/foo`` is deleted after restore.

        Requirements 2.1, 2.2.
        """
        # Arrange
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        self._write_subpath_config(config_path, "my-project", target_dir, [".kiro/specs/foo"])

        managed_copy = managed_dir / ".kiro" / "specs" / "foo"
        managed_copy.parent.mkdir(parents=True, exist_ok=True)
        managed_copy.write_text("spec content")

        symlink_path = target_dir / ".kiro" / "specs" / "foo"
        symlink_path.parent.mkdir(parents=True, exist_ok=True)
        symlink_path.symlink_to(managed_copy)

        monkeypatch.chdir(target_dir)

        # Act
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "restore", ".kiro/specs/foo"],
            env=isolated_home,
        )

        # Assert
        assert result.exit_code == 0, result.output
        assert not managed_copy.exists(), "managed copy at nested path should have been deleted"


# ---------------------------------------------------------------------------
# Git exclude — nested path bug condition
# ---------------------------------------------------------------------------


class TestRevlinkGitExcludeNestedPath:
    """Bug condition exploration tests for nested path git exclude handling.

    These tests surface the bug where ``_git_exclude`` and
    ``_git_exclude_preview`` silently skip the git exclude step when the
    source path is nested (e.g. ``docs/agent``).  The root cause is that all
    three affected methods pass ``self.source.parent`` (an intermediate
    subdirectory without ``.git``) to ``GitExcludeManager`` instead of
    ``self.context.cwd`` (the project root).

    All three tests are EXPECTED TO FAIL on unfixed code — failure confirms
    the bug exists.

    Requirements: 1.1, 1.2, 1.3
    """

    def _write_subpath_config(
        self,
        config_path: Path,
        project_name: str,
        target_dir: Path,
        subpaths: list[str],
    ) -> None:
        """Write a selective-sync config with the given subpath list.

        Args:
            config_path: Destination path for the YAML config file.
            project_name: The project name key.
            target_dir: The target directory path to map to.
            subpaths: Initial list of subpath entries.
        """
        subpath_yaml = "\n".join(f"    - {s}" for s in subpaths)
        config_path.write_text(f"{project_name}:\n  target: {target_dir}\n  subpath:\n{subpath_yaml}\n")

    def test_create_nested_path_git_exclude(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """``create docs/agent`` writes ``docs/agent`` to ``.git/info/exclude``.

        Bug condition: ``source.parent`` is ``<cwd>/docs/`` which has no
        ``.git``, so ``is_git_repo()`` returns ``False`` and the entry is
        never written.

        EXPECTED TO FAIL on unfixed code — the entry will NOT be present in
        ``.git/info/exclude``.

        Requirements: 1.1, 2.1
        """
        # Arrange
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        _make_fake_git_repo(target_dir)

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        # Use a pre-existing subpath entry so the mapping is recognised as
        # selective-sync (subpaths is not None).  An empty YAML list parses as
        # None (sync-all), which triggers Rule 4 before we reach the git-exclude step.
        self._write_subpath_config(config_path, "my-project", target_dir, [".placeholder"])

        # Create the nested source directory: docs/agent inside target_dir
        source_dir = target_dir / "docs" / "agent"
        source_dir.mkdir(parents=True)
        (source_dir / "readme.md").write_text("agent docs")

        monkeypatch.chdir(target_dir)

        # Act
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "create", "docs/agent"],
            env=isolated_home,
        )

        # Assert: command succeeds
        assert result.exit_code == 0, result.output

        # Assert: docs/agent appears in .git/info/exclude
        # This WILL FAIL on unfixed code — the entry is not written because
        # GitExcludeManager is called with source.parent (docs/) which has no .git
        exclude_file = target_dir / ".git" / "info" / "exclude"
        exclude_contents = exclude_file.read_text() if exclude_file.exists() else ""
        assert "docs/agent" in exclude_contents, (
            f"Expected 'docs/agent' in .git/info/exclude, but got:\n{exclude_contents!r}"
        )

    def test_create_nested_path_dry_run_git_exclude(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """``create --dry-run docs/agent`` includes a git exclude message in output.

        Bug condition: ``_git_exclude_preview`` uses ``source.parent`` (the
        ``docs/`` subdirectory) which has no ``.git``, so no git exclude
        preview line is emitted at all.

        EXPECTED TO FAIL on unfixed code — the output will contain no mention
        of the git exclude action.

        Requirements: 1.2, 2.2
        """
        # Arrange
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        _make_fake_git_repo(target_dir)

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        # Use a pre-existing subpath entry so the mapping is recognised as
        # selective-sync (subpaths is not None).  An empty YAML list parses as
        # None (sync-all), which triggers Rule 4 before we reach the git-exclude step.
        self._write_subpath_config(config_path, "my-project", target_dir, [".placeholder"])

        source_dir = target_dir / "docs" / "agent"
        source_dir.mkdir(parents=True)
        (source_dir / "readme.md").write_text("agent docs")

        monkeypatch.chdir(target_dir)

        # Act
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "create", "--dry-run", "docs/agent"],
            env=isolated_home,
        )

        # Assert: command succeeds
        assert result.exit_code == 0, result.output

        # Assert: output contains a git exclude message
        # This WILL FAIL on unfixed code — the preview silently skips the git
        # exclude step because source.parent (docs/) has no .git
        output = result.output
        assert "exclude" in output.lower(), f"Expected git exclude message in dry-run output, but got:\n{output!r}"

    def test_restore_nested_path_git_exclude(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """``restore docs/agent`` removes ``docs/agent`` from ``.git/info/exclude``.

        Bug condition: ``RestoreOperation._git_exclude`` uses ``source.parent``
        (the ``docs/`` subdirectory) which has no ``.git``, so ``is_git_repo()``
        returns ``False`` and the entry is never removed.

        EXPECTED TO FAIL on unfixed code — the entry will still be present in
        ``.git/info/exclude`` after restore.

        Requirements: 1.3, 2.3
        """
        # Arrange
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        _make_fake_git_repo(target_dir)

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        self._write_subpath_config(config_path, "my-project", target_dir, ["docs/agent"])

        # Set up the managed copy at the full nested path
        managed_copy = managed_dir / "docs" / "agent"
        managed_copy.parent.mkdir(parents=True, exist_ok=True)
        managed_copy.mkdir()
        (managed_copy / "readme.md").write_text("agent docs")

        # Set up the symlink at the nested path inside target_dir
        symlink_dir = target_dir / "docs"
        symlink_dir.mkdir(parents=True, exist_ok=True)
        symlink_path = target_dir / "docs" / "agent"
        symlink_path.symlink_to(managed_copy)

        # Pre-populate .git/info/exclude with the entry
        exclude_file = target_dir / ".git" / "info" / "exclude"
        exclude_file.write_text("docs/agent\n")

        monkeypatch.chdir(target_dir)

        # Act
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "restore", "docs/agent"],
            env=isolated_home,
        )

        # Assert: command succeeds
        assert result.exit_code == 0, result.output

        # Assert: docs/agent is NO LONGER in .git/info/exclude
        # This WILL FAIL on unfixed code — the entry is not removed because
        # GitExcludeManager is called with source.parent (docs/) which has no .git
        exclude_contents = exclude_file.read_text() if exclude_file.exists() else ""
        assert "docs/agent" not in exclude_contents, (
            f"Expected 'docs/agent' to be removed from .git/info/exclude, but got:\n{exclude_contents!r}"
        )

    # ------------------------------------------------------------------
    # Preservation property-based tests (Property 2)
    # EXPECTED TO PASS on unfixed code — confirms baseline behavior.
    # ------------------------------------------------------------------

    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(filename=st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,15}", fullmatch=True))
    def test_create_top_level_path_git_exclude_preserved(self, filename: str) -> None:
        """``create <name>`` writes ``<name>`` to ``.git/info/exclude`` for any top-level path.

        Preservation property: top-level path git exclude behavior must be
        identical before and after the fix.  Generates valid single-component
        filenames (no slashes, no leading dot, reasonable length) and verifies
        that each is written into ``.git/info/exclude`` after a successful
        ``create`` run.

        **Validates: Requirements 3.1**

        EXPECTED TO PASS on unfixed code — this is the preserved baseline.
        """
        with tempfile.TemporaryDirectory() as _base:
            base = Path(_base)

            target_dir = base / "target"
            target_dir.mkdir()
            _make_fake_git_repo(target_dir)

            managed_dir = base / "my-project"
            managed_dir.mkdir()

            # Isolated home so .blfrc is not used
            home_dir = base / "home"
            home_dir.mkdir()
            env = {"BLF_HOME": str(home_dir)}

            config_path = base / "config.yml"
            config_path.write_text(f"my-project:\n  target: {target_dir}\n  subpath:\n    - .placeholder\n")

            source_file = target_dir / filename
            source_file.write_text("content")

            original_cwd = os.getcwd()
            try:
                os.chdir(target_dir)
                runner = CliRunner()
                result = runner.invoke(
                    cli,
                    ["--config", str(config_path), "revlink", "create", filename],
                    env=env,
                    catch_exceptions=False,
                )
            finally:
                os.chdir(original_cwd)

            assert result.exit_code == 0, f"create failed for filename={filename!r}:\n{result.output}"

            exclude_file = target_dir / ".git" / "info" / "exclude"
            exclude_contents = exclude_file.read_text() if exclude_file.exists() else ""
            assert filename in exclude_contents, (
                f"Expected {filename!r} in .git/info/exclude after create, but got:\n{exclude_contents!r}"
            )

    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(filename=st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,15}", fullmatch=True))
    def test_restore_top_level_path_git_exclude_preserved(self, filename: str) -> None:
        """``restore <name>`` removes ``<name>`` from ``.git/info/exclude`` for any top-level path.

        Preservation property: top-level path git exclude removal behavior
        must be identical before and after the fix.  Generates valid
        single-component filenames and verifies that each is removed from
        ``.git/info/exclude`` after a successful ``restore`` run.

        **Validates: Requirements 3.3**

        EXPECTED TO PASS on unfixed code — this is the preserved baseline.
        """
        with tempfile.TemporaryDirectory() as _base:
            base = Path(_base)

            target_dir = base / "target"
            target_dir.mkdir()
            _make_fake_git_repo(target_dir)

            managed_dir = base / "my-project"
            managed_dir.mkdir()

            # Isolated home so .blfrc is not used
            home_dir = base / "home"
            home_dir.mkdir()
            env = {"BLF_HOME": str(home_dir)}

            config_path = base / "config.yml"
            config_path.write_text(f"my-project:\n  target: {target_dir}\n  subpath:\n    - {filename}\n")

            # Set up managed copy
            managed_copy = managed_dir / filename
            managed_copy.write_text("content")

            # Set up symlink in target_dir pointing to managed copy
            symlink_path = target_dir / filename
            symlink_path.symlink_to(managed_copy)

            # Pre-populate .git/info/exclude with the entry
            exclude_file = target_dir / ".git" / "info" / "exclude"
            exclude_file.write_text(f"{filename}\n")

            original_cwd = os.getcwd()
            try:
                os.chdir(target_dir)
                runner = CliRunner()
                result = runner.invoke(
                    cli,
                    ["--config", str(config_path), "revlink", "restore", filename],
                    env=env,
                    catch_exceptions=False,
                )
            finally:
                os.chdir(original_cwd)

            assert result.exit_code == 0, f"restore failed for filename={filename!r}:\n{result.output}"

            exclude_contents = exclude_file.read_text() if exclude_file.exists() else ""
            assert filename not in exclude_contents, (
                f"Expected {filename!r} to be removed from .git/info/exclude after restore, "
                f"but it is still present:\n{exclude_contents!r}"
            )
