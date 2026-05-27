"""End-to-end integration tests for the revlink restore command — happy paths.

Covers Requirements 3.2, 3.3, 4.3, 4.5, 4.6, 5.1, 5.3, 5.6.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from beyond_local_file.cli import cli
from beyond_local_file.operations.revlink import ChecksumVerifier

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
# Happy path — file restore
# ---------------------------------------------------------------------------


class TestRestoreHappyPathFile:
    """End-to-end tests for the basic file restore workflow.

    Requirements: 4.3, 4.5, 5.1, 5.3
    """

    def test_symlink_becomes_real_file_after_restore(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Test that a symlink is dissolved and replaced with the real file.

        Happy path: managed copy exists, symlink at target_dir → revlink restore
        → real file at target_dir, managed copy deleted, git exclude removed.

        Requirements 4.3, 4.5, 5.1, 5.3.
        """
        # Arrange
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        _make_fake_git_repo(target_dir)

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        # Set up the managed copy with content
        managed_copy = managed_dir / "myfile.txt"
        managed_copy.write_text("hello world")

        # Set up the symlink in target_dir pointing to the managed copy
        symlink_path = target_dir / "myfile.txt"
        symlink_path.symlink_to(managed_copy)

        # Pre-populate .git/info/exclude with the filename
        exclude_file = target_dir / ".git" / "info" / "exclude"
        exclude_file.write_text("myfile.txt\n")

        monkeypatch.chdir(target_dir)

        # Act
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "restore", "myfile.txt"],
            env=isolated_home,
        )

        # Assert
        assert result.exit_code == 0, result.output

        # The path is now a real file, not a symlink
        assert not symlink_path.is_symlink(), "path should no longer be a symlink"
        assert symlink_path.is_file(), "path should be a real file"

        # The file has the original content
        assert symlink_path.read_text() == "hello world"

        # The managed copy no longer exists
        assert not managed_copy.exists(), "managed copy should have been deleted"

        # .git/info/exclude no longer contains the filename
        assert "myfile.txt" not in exclude_file.read_text()

    def test_restore_exit_code_is_zero_on_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Test that a successful restore exits with code 0.

        Requirement 4.5: THE RestoreOperation SHALL proceed to delete the
        Managed_Copy when MD5 checksums match.
        """
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        managed_copy = managed_dir / "data.txt"
        managed_copy.write_text("some data content")

        symlink_path = target_dir / "data.txt"
        symlink_path.symlink_to(managed_copy)

        monkeypatch.chdir(target_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "restore", "data.txt"],
            env=isolated_home,
        )

        assert result.exit_code == 0, result.output

    def test_restore_file_content_matches_managed_copy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Test that the restored file has exactly the same content as the managed copy.

        Requirement 4.3: THE RestoreOperation SHALL copy the Managed_Copy to
        the CWD_Path using shutil.copy2 for files.
        """
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        original_content = "line 1\nline 2\nline 3\n"
        managed_copy = managed_dir / "notes.txt"
        managed_copy.write_text(original_content)

        symlink_path = target_dir / "notes.txt"
        symlink_path.symlink_to(managed_copy)

        monkeypatch.chdir(target_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "restore", "notes.txt"],
            env=isolated_home,
        )

        assert result.exit_code == 0, result.output
        assert symlink_path.read_text() == original_content

    def test_restore_removes_git_exclude_entry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Test that the git exclude entry is removed after a successful restore.

        Requirement 5.3: WHEN the restore succeeds and the CWD_Path is inside
        a Git repository, THE Git_Exclude_Manager SHALL remove the item name
        from .git/info/exclude.
        """
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        _make_fake_git_repo(target_dir)

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        managed_copy = managed_dir / "config.json"
        managed_copy.write_text('{"key": "value"}')

        symlink_path = target_dir / "config.json"
        symlink_path.symlink_to(managed_copy)

        # Pre-populate exclude with the entry plus another entry that should remain
        exclude_file = target_dir / ".git" / "info" / "exclude"
        exclude_file.write_text("other-file.txt\nconfig.json\n")

        monkeypatch.chdir(target_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "restore", "config.json"],
            env=isolated_home,
        )

        assert result.exit_code == 0, result.output

        exclude_content = exclude_file.read_text()
        assert "config.json" not in exclude_content
        # The other entry should still be present
        assert "other-file.txt" in exclude_content

    def test_restore_deletes_managed_copy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Test that the managed copy is deleted after a successful restore.

        Requirement 5.1: WHEN the MD5 checksums match, THE RestoreOperation
        SHALL attempt to delete the Managed_Copy.
        """
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        managed_copy = managed_dir / "script.sh"
        managed_copy.write_text("#!/bin/bash\necho hello\n")

        symlink_path = target_dir / "script.sh"
        symlink_path.symlink_to(managed_copy)

        monkeypatch.chdir(target_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "restore", "script.sh"],
            env=isolated_home,
        )

        assert result.exit_code == 0, result.output
        assert not managed_copy.exists(), "managed copy should be deleted after restore"


# ---------------------------------------------------------------------------
# Happy path — directory restore
# ---------------------------------------------------------------------------


class TestRestoreHappyPathDirectory:
    """End-to-end tests for the directory restore workflow.

    Requirements: 4.3, 4.5, 5.1, 5.6
    """

    def test_symlink_becomes_real_directory_after_restore(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Test that a directory symlink is dissolved and replaced with a real directory.

        Happy path: managed directory tree exists, symlink at target_dir →
        revlink restore → real directory at target_dir, managed copy deleted.

        Requirements 4.3, 4.5, 5.1.
        """
        # Arrange
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        # Set up the managed directory tree
        managed_copy = managed_dir / "mydir"
        managed_copy.mkdir()
        (managed_copy / "file_a.txt").write_text("content a")
        (managed_copy / "file_b.txt").write_text("content b")
        subdir = managed_copy / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("nested content")

        # Set up the symlink in target_dir pointing to the managed directory
        symlink_path = target_dir / "mydir"
        symlink_path.symlink_to(managed_copy)

        monkeypatch.chdir(target_dir)

        # Act
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "restore", "mydir"],
            env=isolated_home,
        )

        # Assert
        assert result.exit_code == 0, result.output

        # The path is now a real directory, not a symlink
        assert not symlink_path.is_symlink(), "path should no longer be a symlink"
        assert symlink_path.is_dir(), "path should be a real directory"

        # All files inside are accessible with correct content
        assert (symlink_path / "file_a.txt").read_text() == "content a"
        assert (symlink_path / "file_b.txt").read_text() == "content b"
        assert (symlink_path / "subdir" / "nested.txt").read_text() == "nested content"

        # The managed copy no longer exists
        assert not managed_copy.exists(), "managed directory copy should have been deleted"

    def test_directory_restore_preserves_nested_structure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Test that the full directory tree structure is preserved after restore.

        Requirement 4.3: THE RestoreOperation SHALL copy the Managed_Copy to
        the CWD_Path using shutil.copytree for directories.
        """
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        # Create a deeper nested structure
        managed_copy = managed_dir / "configs"
        managed_copy.mkdir()
        (managed_copy / "settings.json").write_text('{"key": "value"}')
        deep = managed_copy / "deep" / "nested"
        deep.mkdir(parents=True)
        (deep / "config.yaml").write_text("setting: true\n")

        symlink_path = target_dir / "configs"
        symlink_path.symlink_to(managed_copy)

        monkeypatch.chdir(target_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "restore", "configs"],
            env=isolated_home,
        )

        assert result.exit_code == 0, result.output
        assert symlink_path.is_dir()
        assert not symlink_path.is_symlink()
        assert (symlink_path / "settings.json").read_text() == '{"key": "value"}'
        assert (symlink_path / "deep" / "nested" / "config.yaml").read_text() == "setting: true\n"

    def test_directory_restore_deletes_managed_copy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Test that the managed directory is deleted after a successful restore.

        Requirement 5.1: WHEN the MD5 checksums match, THE RestoreOperation
        SHALL attempt to delete the Managed_Copy.
        """
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        managed_copy = managed_dir / "assets"
        managed_copy.mkdir()
        (managed_copy / "logo.png").write_bytes(b"\x89PNG\r\n")

        symlink_path = target_dir / "assets"
        symlink_path.symlink_to(managed_copy)

        monkeypatch.chdir(target_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "restore", "assets"],
            env=isolated_home,
        )

        assert result.exit_code == 0, result.output
        assert not managed_copy.exists(), "managed directory should be deleted after restore"

    def test_directory_restore_with_git_exclude_removal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Test that the git exclude entry is removed when restoring a directory.

        Requirement 5.3: WHEN the restore succeeds and the CWD_Path is inside
        a Git repository, THE Git_Exclude_Manager SHALL remove the item name
        from .git/info/exclude.
        """
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        _make_fake_git_repo(target_dir)

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        managed_copy = managed_dir / "mydir"
        managed_copy.mkdir()
        (managed_copy / "readme.md").write_text("# README\n")

        symlink_path = target_dir / "mydir"
        symlink_path.symlink_to(managed_copy)

        exclude_file = target_dir / ".git" / "info" / "exclude"
        exclude_file.write_text("mydir\n")

        monkeypatch.chdir(target_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "restore", "mydir"],
            env=isolated_home,
        )

        assert result.exit_code == 0, result.output
        assert "mydir" not in exclude_file.read_text()

    def test_directory_restore_managed_copy_not_in_target_after_restore(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Test that the managed copy directory is fully removed after restore.

        Requirement 5.6: WHEN the restore succeeds and the matched mapping uses
        selective sync, THE Config_Updater SHALL remove the item name from the
        config subpath list.

        This test verifies the managed copy is gone (no residual files).
        """
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        managed_copy = managed_dir / "workspace"
        managed_copy.mkdir()
        (managed_copy / "a.txt").write_text("alpha")
        (managed_copy / "b.txt").write_text("beta")

        symlink_path = target_dir / "workspace"
        symlink_path.symlink_to(managed_copy)

        monkeypatch.chdir(target_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "restore", "workspace"],
            env=isolated_home,
        )

        assert result.exit_code == 0, result.output

        # Managed copy is gone entirely
        assert not managed_copy.exists()
        assert not (managed_dir / "workspace" / "a.txt").exists()

        # Restored directory has all files
        assert (symlink_path / "a.txt").read_text() == "alpha"
        assert (symlink_path / "b.txt").read_text() == "beta"


# ---------------------------------------------------------------------------
# Error paths — task 9.2
# ---------------------------------------------------------------------------


def _write_subpath_config(config_path: Path, project_name: str, target_dir: Path, subpaths: list[str]) -> None:
    """Write a config with a dict-mapping that has a subpath list.

    Args:
        config_path: Destination path for the YAML config file.
        project_name: The project name key.
        target_dir: The target directory path to map to.
        subpaths: Initial list of subpath entries.
    """
    subpath_yaml = "\n".join(f"    - {s}" for s in subpaths)
    config_path.write_text(f"{project_name}:\n  target: {target_dir}\n  subpath:\n{subpath_yaml}\n")


class TestRestoreDanglingSymlink:
    """Integration tests for the dangling symlink error path.

    Requirements: 3.3
    """

    def test_dangling_symlink_exits_with_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Dangling symlink: managed copy missing → error, CWD symlink untouched.

        Set up a symlink pointing to a managed copy that does not exist.
        Restore should fail with exit code 1 and leave the symlink in place.

        Requirements 3.3.
        """
        # Arrange
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        # Create a symlink pointing to a non-existent managed copy
        nonexistent_managed = managed_dir / "myfile.txt"
        symlink_path = target_dir / "myfile.txt"
        symlink_path.symlink_to(nonexistent_managed)

        # Confirm setup: symlink exists but target does not
        assert symlink_path.is_symlink()
        assert not nonexistent_managed.exists()

        monkeypatch.chdir(target_dir)

        # Act
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "restore", "myfile.txt"],
            env=isolated_home,
        )

        # Assert
        assert result.exit_code == 1, result.output
        output_lower = result.output.lower()
        assert "dangling symlink" in output_lower or "managed copy does not exist" in output_lower, (
            f"Expected dangling symlink error in output, got: {result.output!r}"
        )

        # Symlink must still exist and still be a symlink
        assert symlink_path.is_symlink(), "symlink should remain untouched after error"


class TestRestoreNotASymlink:
    """Integration tests for the not-a-symlink error path.

    Requirements: 3.2
    """

    def test_real_file_exits_with_error_and_suggests_create(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Not a symlink: real file at path → error with revlink create suggestion.

        Set up a real file (not a symlink) at the target path.
        Restore should fail with exit code 1, mention "not a symlink",
        suggest "revlink create", and leave the file unchanged.

        Requirements 3.2.
        """
        # Arrange
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        # Create a real file (not a symlink)
        real_file = target_dir / "myfile.txt"
        original_content = "original content"
        real_file.write_text(original_content)

        assert not real_file.is_symlink()

        monkeypatch.chdir(target_dir)

        # Act
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "restore", "myfile.txt"],
            env=isolated_home,
        )

        # Assert
        assert result.exit_code == 1, result.output
        assert "not a symlink" in result.output.lower(), f"Expected 'not a symlink' in output, got: {result.output!r}"
        assert "revlink create" in result.output, (
            f"Expected 'revlink create' suggestion in output, got: {result.output!r}"
        )

        # File must be unchanged
        assert real_file.exists()
        assert not real_file.is_symlink()
        assert real_file.read_text() == original_content


class TestRestoreMd5Mismatch:
    """Integration tests for the MD5 mismatch error path.

    Requirements: 4.6
    """

    def test_md5_mismatch_deletes_restored_copy_preserves_managed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """MD5 mismatch: restored copy deleted, managed copy preserved, error reported.

        Set up a valid symlink, patch ChecksumVerifier.compute to return
        different digests for the two calls, then run restore.

        After the test:
        - exit code is 1
        - "mismatch" appears in output
        - the restored copy at source path is deleted
        - the managed copy is preserved

        Requirements 4.6.
        """
        # Arrange
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_config(config_path, "my-project", target_dir)

        managed_copy = managed_dir / "myfile.txt"
        managed_copy.write_text("hello world")

        symlink_path = target_dir / "myfile.txt"
        symlink_path.symlink_to(managed_copy)

        monkeypatch.chdir(target_dir)

        # Patch ChecksumVerifier.compute to return different digests on successive calls
        call_count = {"n": 0}

        def fake_compute(path: Path) -> str:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            return "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

        with patch.object(ChecksumVerifier, "compute", staticmethod(fake_compute)):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["--config", str(config_path), "revlink", "restore", "myfile.txt"],
                env=isolated_home,
            )

        # Assert
        assert result.exit_code == 1, result.output
        assert "mismatch" in result.output.lower(), f"Expected 'mismatch' in output, got: {result.output!r}"

        # Restored copy at source path should be deleted
        assert not symlink_path.exists(), "restored copy at source path should have been deleted after mismatch"

        # Managed copy must still exist
        assert managed_copy.exists(), "managed copy must be preserved after mismatch"
        assert managed_copy.read_text() == "hello world"


class TestRestoreConfigSubpathRemoval:
    """Integration tests for config subpath entry removal.

    Requirements: 5.6
    """

    def test_subpath_entry_removed_from_config_after_restore(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: dict
    ) -> None:
        """Config subpath removal: entry removed from config when mapping uses selective sync.

        Set up a config with subpath: [myfile.txt, other.txt] and a valid
        symlink for myfile.txt. After restore, myfile.txt should be removed
        from the subpath list while other.txt remains.

        Requirements 5.6.
        """
        # Arrange
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        managed_dir = tmp_path / "my-project"
        managed_dir.mkdir()

        config_path = tmp_path / "config.yml"
        _write_subpath_config(config_path, "my-project", target_dir, ["myfile.txt", "other.txt"])

        # Create managed copy and symlink
        managed_copy = managed_dir / "myfile.txt"
        managed_copy.write_text("hello world")

        symlink_path = target_dir / "myfile.txt"
        symlink_path.symlink_to(managed_copy)

        monkeypatch.chdir(target_dir)

        # Act
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "revlink", "restore", "myfile.txt"],
            env=isolated_home,
        )

        # Assert
        assert result.exit_code == 0, result.output

        updated_config = config_path.read_text()
        assert "myfile.txt" not in updated_config, "myfile.txt should have been removed from the config subpath list"
        assert "other.txt" in updated_config, "other.txt should still be present in the config subpath list"
