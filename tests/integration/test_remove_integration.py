"""End-to-end coverage for the destructive top-level ``blf remove`` command."""

from pathlib import Path

from click.testing import CliRunner

from beyond_local_file.cli import cli
from beyond_local_file.git_manager import GitExcludeManager


def _write_project_config(config_path: Path, managed: Path, first_target: Path, second_target: Path) -> None:
    """Write a project with one sync-all and one selective mapping.

    Args:
        config_path: Destination YAML configuration path.
        managed: Authoritative managed-project directory.
        first_target: Target for the invocation's sync-all mapping.
        second_target: Target for the participating selective mapping.
    """
    config_path.write_text(
        f"""managed:
  - target: {first_target}
  - target: {second_target}
    subpath:
      - item.txt
"""
    )


def _make_git_repository(target: Path, entry: str) -> Path:
    """Create a minimal Git exclude file containing an item entry.

    Args:
        target: Target directory that acts as the repository root.
        entry: Relative item path to add to the exclude file.

    Returns:
        The created exclude file path.
    """
    exclude_file = target / ".git" / "info" / "exclude"
    exclude_file.parent.mkdir(parents=True)
    exclude_file.write_text(f"# preserved\n{entry}\nother-entry\n")
    return exclude_file


def test_remove_deletes_every_validated_projection_and_updates_selective_config(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Remove a managed item from every participating mapping after preflight.

    A successful command removes both target symlinks and their Git-exclude
    entries, permanently deletes the managed copy, and removes the selective
    mapping's exact subpath while preserving unrelated configuration content.
    """
    managed = tmp_path / "managed"
    first_target = tmp_path / "target-one"
    second_target = tmp_path / "target-two"
    for directory in (managed, first_target, second_target):
        directory.mkdir()

    managed_item = managed / "item.txt"
    managed_item.write_text("authoritative content")
    first_item = first_target / "item.txt"
    second_item = second_target / "item.txt"
    first_item.symlink_to(managed_item)
    second_item.symlink_to(managed_item)
    first_exclude = _make_git_repository(first_target, "item.txt")
    second_exclude = _make_git_repository(second_target, "item.txt")

    config_path = tmp_path / "config.yml"
    _write_project_config(config_path, managed, first_target, second_target)
    original_config = config_path.read_text()

    monkeypatch.chdir(first_target)
    result = CliRunner().invoke(cli, ["--config", str(config_path), "remove", "item.txt"], env=isolated_home)

    assert result.exit_code == 0, result.output
    assert not first_item.exists()
    assert not second_item.exists()
    assert not managed_item.exists()
    assert "item.txt" not in first_exclude.read_text()
    assert "item.txt" not in second_exclude.read_text()
    updated_config = config_path.read_text()
    assert "subpath: []" in updated_config
    assert "item.txt" not in updated_config
    assert updated_config != original_config


def test_remove_dry_run_validates_every_projection_without_mutation(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Preview valid removal without touching projections, config, or excludes."""
    managed = tmp_path / "managed"
    first_target = tmp_path / "target-one"
    second_target = tmp_path / "target-two"
    for directory in (managed, first_target, second_target):
        directory.mkdir()

    managed_item = managed / "item.txt"
    managed_item.write_text("authoritative content")
    first_item = first_target / "item.txt"
    second_item = second_target / "item.txt"
    first_item.symlink_to(managed_item)
    second_item.symlink_to(managed_item)
    first_exclude = _make_git_repository(first_target, "item.txt")
    second_exclude = _make_git_repository(second_target, "item.txt")
    config_path = tmp_path / "config.yml"
    _write_project_config(config_path, managed, first_target, second_target)

    before = {
        "config": config_path.read_bytes(),
        "first_exclude": first_exclude.read_bytes(),
        "second_exclude": second_exclude.read_bytes(),
    }
    monkeypatch.chdir(first_target)
    result = CliRunner().invoke(
        cli,
        ["--config", str(config_path), "remove", "--dry-run", "item.txt"],
        env=isolated_home,
    )

    assert result.exit_code == 0, result.output
    assert all(line.startswith("[dry-run]") for line in result.output.splitlines())
    assert first_item.is_symlink()
    assert second_item.is_symlink()
    assert managed_item.exists()
    assert config_path.read_bytes() == before["config"]
    assert first_exclude.read_bytes() == before["first_exclude"]
    assert second_exclude.read_bytes() == before["second_exclude"]


def test_remove_rejects_mismatched_copy_without_mutation(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """A divergent copy projection blocks removal and leaves all state unchanged."""
    managed = tmp_path / "managed"
    target = tmp_path / "target"
    managed.mkdir()
    target.mkdir()
    managed_item = managed / "item.txt"
    target_item = target / "item.txt"
    managed_item.write_text("authoritative content")
    target_item.write_text("edited target content")
    exclude_file = _make_git_repository(target, "item.txt")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"""managed:
  target: {target}
  subpath:
    - path: item.txt
      copy: true
"""
    )
    before = {
        "config": config_path.read_bytes(),
        "exclude": exclude_file.read_bytes(),
        "managed": managed_item.read_bytes(),
        "target": target_item.read_bytes(),
    }

    monkeypatch.chdir(target)
    result = CliRunner().invoke(cli, ["--config", str(config_path), "remove", "item.txt"], env=isolated_home)

    assert result.exit_code == 1
    assert "checksum mismatch" in result.output.lower()
    assert config_path.read_bytes() == before["config"]
    assert exclude_file.read_bytes() == before["exclude"]
    assert managed_item.read_bytes() == before["managed"]
    assert target_item.read_bytes() == before["target"]


def test_remove_rejects_misdirected_participating_symlink_without_mutation(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """A bad secondary target blocks removal before its valid sibling changes."""
    managed = tmp_path / "managed"
    first_target = tmp_path / "target-one"
    second_target = tmp_path / "target-two"
    for directory in (managed, first_target, second_target):
        directory.mkdir()
    managed_item = managed / "item.txt"
    wrong_item = tmp_path / "wrong.txt"
    managed_item.write_text("authoritative content")
    wrong_item.write_text("different item")
    first_item = first_target / "item.txt"
    second_item = second_target / "item.txt"
    first_item.symlink_to(managed_item)
    second_item.symlink_to(wrong_item)
    first_exclude = _make_git_repository(first_target, "item.txt")
    second_exclude = _make_git_repository(second_target, "item.txt")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"""managed:
  target: [{first_target}, {second_target}]
  subpath:
    - item.txt
"""
    )
    before = {
        "config": config_path.read_bytes(),
        "first_exclude": first_exclude.read_bytes(),
        "second_exclude": second_exclude.read_bytes(),
    }

    monkeypatch.chdir(first_target)
    result = CliRunner().invoke(cli, ["--config", str(config_path), "remove", "item.txt"], env=isolated_home)

    assert result.exit_code == 1
    assert "points somewhere other" in result.output
    assert first_item.is_symlink()
    assert second_item.is_symlink()
    assert managed_item.exists()
    assert config_path.read_bytes() == before["config"]
    assert first_exclude.read_bytes() == before["first_exclude"]
    assert second_exclude.read_bytes() == before["second_exclude"]


def test_remove_leaves_incidental_artifact_in_nonparticipating_selective_mapping(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Only mappings that explicitly manage the exact item take part in removal."""
    managed = tmp_path / "managed"
    participating = tmp_path / "participating"
    ignored = tmp_path / "ignored"
    for directory in (managed, participating, ignored):
        directory.mkdir()
    managed_item = managed / "item.txt"
    managed_item.write_text("authoritative content")
    participating_item = participating / "item.txt"
    participating_item.symlink_to(managed_item)
    incidental_item = ignored / "item.txt"
    incidental_item.write_text("unmanaged local content")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"""managed:
  - target: {participating}
    subpath:
      - item.txt
  - target: {ignored}
    subpath:
      - other.txt
"""
    )

    monkeypatch.chdir(participating)
    result = CliRunner().invoke(cli, ["--config", str(config_path), "remove", "item.txt"], env=isolated_home)

    assert result.exit_code == 0, result.output
    assert not participating_item.exists()
    assert not managed_item.exists()
    assert incidental_item.read_text() == "unmanaged local content"
    updated_config = config_path.read_text()
    assert "subpath: []" in updated_config
    assert "- other.txt" in updated_config


def test_remove_rejects_path_that_traverses_a_directory_symlink(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """A child reached through a directory symlink is not a removable artifact."""
    managed = tmp_path / "managed"
    target = tmp_path / "target"
    managed.mkdir()
    target.mkdir()
    managed_directory = managed / "nested"
    managed_directory.mkdir()
    managed_item = managed_directory / "item.txt"
    managed_item.write_text("authoritative content")
    (target / "nested").symlink_to(managed_directory, target_is_directory=True)
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"managed: {target}\n")
    before = config_path.read_bytes()

    monkeypatch.chdir(target)
    result = CliRunner().invoke(cli, ["--config", str(config_path), "remove", "nested/item.txt"], env=isolated_home)

    assert result.exit_code == 1
    assert "traverses directory symlink" in result.output
    assert managed_item.read_text() == "authoritative content"
    assert (target / "nested").is_symlink()
    assert config_path.read_bytes() == before


def test_remove_rejects_lexically_normalized_path_outside_cwd(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Lexical ``..`` traversal is rejected before resolver or cleanup work."""
    target = tmp_path / "target"
    target.mkdir()
    outside_item = tmp_path / "outside.txt"
    outside_item.write_text("must remain")

    monkeypatch.chdir(target)
    result = CliRunner().invoke(cli, ["remove", "../outside.txt"], env=isolated_home)

    assert result.exit_code == 1
    assert "inside the current directory" in result.output
    assert outside_item.read_text() == "must remain"


def test_remove_retains_managed_copy_and_config_after_target_cleanup_failure(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """A target unlink failure preserves later destructive phases for retry."""
    managed = tmp_path / "managed"
    target = tmp_path / "target"
    managed.mkdir()
    target.mkdir()
    managed_item = managed / "item.txt"
    managed_item.write_text("authoritative content")
    target_item = target / "item.txt"
    target_item.symlink_to(managed_item)
    exclude_file = _make_git_repository(target, "item.txt")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"managed: {target}\n")
    config_before = config_path.read_bytes()
    original_unlink = Path.unlink

    def fail_target_unlink(path: Path, missing_ok: bool = False) -> None:
        """Fail only removal of the configured target artifact."""
        if path == target_item:
            raise OSError("permission denied")
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.chdir(target)
    monkeypatch.setattr(Path, "unlink", fail_target_unlink)
    result = CliRunner().invoke(cli, ["--config", str(config_path), "remove", "item.txt"], env=isolated_home)

    assert result.exit_code == 1
    assert "managed copy and configuration were retained" in result.output
    assert target_item.is_symlink()
    assert managed_item.exists()
    assert config_path.read_bytes() == config_before
    assert "item.txt" not in exclude_file.read_text()


def test_remove_rejects_inaccessible_participating_target_without_mutation(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """An inaccessible participating target blocks cleanup across the project."""
    managed = tmp_path / "managed"
    first_target = tmp_path / "target-one"
    blocked_target = tmp_path / "target-two"
    for directory in (managed, first_target, blocked_target):
        directory.mkdir()
    managed_item = managed / "item.txt"
    managed_item.write_text("authoritative content")
    first_item = first_target / "item.txt"
    blocked_item = blocked_target / "item.txt"
    first_item.symlink_to(managed_item)
    blocked_item.symlink_to(managed_item)
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"""managed:
  target: [{first_target}, {blocked_target}]
  subpath:
    - item.txt
"""
    )
    config_before = config_path.read_bytes()

    monkeypatch.chdir(first_target)
    monkeypatch.setattr("beyond_local_file.operations.remove.os.access", lambda path, mode: path != blocked_target)
    result = CliRunner().invoke(cli, ["--config", str(config_path), "remove", "item.txt"], env=isolated_home)

    assert result.exit_code == 1
    assert "inaccessible" in result.output
    assert first_item.is_symlink()
    assert blocked_item.is_symlink()
    assert managed_item.exists()
    assert config_path.read_bytes() == config_before


def test_remove_reports_manual_repair_when_config_update_fails_after_deletion(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """A post-deletion config failure reports the irreversible recovery state."""
    managed = tmp_path / "managed"
    target = tmp_path / "target"
    managed.mkdir()
    target.mkdir()
    managed_item = managed / "item.txt"
    managed_item.write_text("authoritative content")
    target_item = target / "item.txt"
    target_item.symlink_to(managed_item)
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"managed:\n  target: {target}\n  subpath:\n    - item.txt\n")
    config_before = config_path.read_bytes()

    def fail_config_write(*args: object, **kwargs: object) -> bool:
        """Simulate an OS failure after target and managed cleanup succeeded."""
        raise OSError("disk failure")

    monkeypatch.chdir(target)
    monkeypatch.setattr(
        "beyond_local_file.operations.remove.ConfigUpdater.remove_subpath_entries",
        fail_config_write,
    )
    result = CliRunner().invoke(cli, ["--config", str(config_path), "remove", "item.txt"], env=isolated_home)

    assert result.exit_code == 1
    assert not target_item.exists()
    assert not managed_item.exists()
    assert config_path.read_bytes() == config_before
    assert "was deleted" in result.output
    assert "manually" in result.output


def test_remove_continues_cleanup_and_retains_later_phases_after_exclude_read_failure(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """An unreadable exclude file triggers recovery output after other cleanup attempts."""
    managed = tmp_path / "managed"
    first_target = tmp_path / "target-one"
    second_target = tmp_path / "target-two"
    for directory in (managed, first_target, second_target):
        directory.mkdir()
    managed_item = managed / "item.txt"
    managed_item.write_text("authoritative content")
    first_item = first_target / "item.txt"
    second_item = second_target / "item.txt"
    first_item.symlink_to(managed_item)
    second_item.symlink_to(managed_item)
    first_exclude = _make_git_repository(first_target, "item.txt")
    second_exclude = _make_git_repository(second_target, "item.txt")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"""managed:
  target: [{first_target}, {second_target}]
  subpath:
    - item.txt
"""
    )
    config_before = config_path.read_bytes()

    original_read_entries = GitExcludeManager.read_entries

    def fail_first_exclude_read(manager: GitExcludeManager) -> set[str]:
        """Simulate an I/O failure for only the first target's exclude file."""
        if manager.repo_root == first_target:
            raise OSError("exclude read failed")
        return original_read_entries(manager)

    monkeypatch.chdir(first_target)
    monkeypatch.setattr(GitExcludeManager, "read_entries", fail_first_exclude_read)
    result = CliRunner().invoke(cli, ["--config", str(config_path), "remove", "item.txt"], env=isolated_home)

    assert result.exit_code == 1
    assert "managed copy and configuration were retained" in result.output
    assert not first_item.exists()
    assert not second_item.exists()
    assert managed_item.exists()
    assert config_path.read_bytes() == config_before
    assert "item.txt" in first_exclude.read_text()
    assert "item.txt" not in second_exclude.read_text()


def test_remove_dry_run_prefixes_config_resolution_errors(isolated_home: dict[str, str]) -> None:
    """Every dry-run config-resolution error line is clearly marked as preview output."""
    with CliRunner().isolated_filesystem():
        result = CliRunner().invoke(cli, ["remove", "--dry-run", "item.txt"], env=isolated_home)

    assert result.exit_code == 1
    assert result.output
    assert all(line.startswith("[dry-run]") for line in result.output.splitlines())
