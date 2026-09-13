"""Copy-only revlink create, restore, and remove at the public command seams."""

import hashlib
from pathlib import Path

from beyond_local_file.daemon.process import state_dir
from beyond_local_file.sync_state import compute_item_hash
from tests.daemon_support import invoke_with_daemon, start_daemon, stop_daemon


def _expected_held_dir(managed: Path, home: Path) -> Path:
    """Return ``<home>/.blf/held/<sha256 of the resolved managed project path>``."""
    digest = hashlib.sha256(str(managed.resolve()).encode("utf-8")).hexdigest()
    return home / ".blf" / "held" / digest


def _write_selective_config(config_path: Path, managed_name: str, *targets: Path) -> None:
    """Write a selective-sync mapping with an empty subpath list for each target.

    Args:
        config_path: YAML config path. The managed directory is a sibling named
            ``managed_name``.
        managed_name: Project key and managed-directory name.
        targets: Target directories that receive adopted items.
    """
    mappings = "\n".join(f"  - target: {target}\n    subpath: []\n" for target in targets)
    config_path.write_text(f"{managed_name}:\n{mappings}")


def _make_git_repo(directory: Path) -> Path:
    """Create a fake Git repository root and return its exclude file path.

    Args:
        directory: Directory that should act as a Git root.

    Returns:
        Path to ``.git/info/exclude``.
    """
    exclude = directory / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True)
    exclude.write_text("# preserved\n")
    return exclude


def test_revlink_create_leaves_target_as_regular_file_and_copies_into_hub(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """After create, the target path is a regular file and the hub has a copy."""
    managed = tmp_path / "managed"
    target = tmp_path / "target"
    managed.mkdir()
    target.mkdir()
    exclude = _make_git_repo(target)
    source = target / "item.txt"
    source.write_text("adopt me")
    config_path = tmp_path / "config.yml"
    _write_selective_config(config_path, "managed", target)

    monkeypatch.chdir(target)
    result = invoke_with_daemon(config_path, ["revlink", "create", "item.txt"], isolated_home)

    assert result.exit_code == 0, result.output
    assert source.is_file()
    assert not source.is_symlink()
    assert source.read_text() == "adopt me"
    hub_copy = managed / "item.txt"
    assert hub_copy.is_file()
    assert not hub_copy.is_symlink()
    assert hub_copy.read_text() == "adopt me"
    assert "item.txt" in exclude.read_text()
    assert "- item.txt" in config_path.read_text()


def test_revlink_create_records_pair_as_in_sync(tmp_path: Path, monkeypatch, isolated_home: dict[str, str]) -> None:
    """Create records hashes so a later catch-up does not see a phantom change."""
    managed = tmp_path / "managed"
    target = tmp_path / "target"
    managed.mkdir()
    target.mkdir()
    source = target / "item.txt"
    source.write_text("adopt me")
    config_path = tmp_path / "config.yml"
    _write_selective_config(config_path, "managed", target)

    monkeypatch.chdir(target)
    result = invoke_with_daemon(config_path, ["revlink", "create", "item.txt"], isolated_home)

    assert result.exit_code == 0, result.output
    hub_copy = managed / "item.txt"
    assert compute_item_hash(hub_copy) == compute_item_hash(source)
    assert not (state_dir(config_path) / "sync-state.yml").exists()

    start_daemon(config_path, isolated_home)
    try:
        assert source.read_text() == "adopt me"
        assert hub_copy.read_text() == "adopt me"
        assert not source.is_symlink()
    finally:
        stop_daemon(config_path, isolated_home)


def test_revlink_create_fans_out_to_other_replicas(tmp_path: Path, monkeypatch, isolated_home: dict[str, str]) -> None:
    """Create copies the new item onto every other target of the managed project."""
    managed = tmp_path / "managed"
    first_target = tmp_path / "target-one"
    second_target = tmp_path / "target-two"
    for directory in (managed, first_target, second_target):
        directory.mkdir()
    _make_git_repo(first_target)
    second_exclude = _make_git_repo(second_target)
    source = first_target / "item.txt"
    source.write_text("adopt me")
    config_path = tmp_path / "config.yml"
    _write_selective_config(config_path, "managed", first_target, second_target)

    monkeypatch.chdir(first_target)
    result = invoke_with_daemon(config_path, ["revlink", "create", "item.txt"], isolated_home)

    assert result.exit_code == 0, result.output
    replica = second_target / "item.txt"
    assert replica.is_file()
    assert not replica.is_symlink()
    assert replica.read_text() == "adopt me"
    assert "item.txt" in second_exclude.read_text()
    updated = config_path.read_text()
    assert updated.count("- item.txt") == updated.count("target:")
    assert compute_item_hash(managed / "item.txt") == compute_item_hash(replica)
    assert not (state_dir(config_path) / "sync-state.yml").exists()


def test_revlink_create_holds_divergent_replica_then_overwrites(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Different bytes on another replica are held, then overwritten from the hub."""
    managed = tmp_path / "managed"
    first_target = tmp_path / "target-one"
    second_target = tmp_path / "target-two"
    for directory in (managed, first_target, second_target):
        directory.mkdir()
    (first_target / "item.txt").write_text("adopt me")
    (second_target / "item.txt").write_text("other bytes")
    config_path = tmp_path / "config.yml"
    _write_selective_config(config_path, "managed", first_target, second_target)

    monkeypatch.chdir(first_target)
    result = invoke_with_daemon(config_path, ["revlink", "create", "item.txt"], isolated_home)

    assert result.exit_code == 0, result.output
    assert (second_target / "item.txt").read_text() == "adopt me"
    held_root = _expected_held_dir(managed, Path(isolated_home["BLF_HOME"]))
    slots = list(held_root.iterdir())
    assert len(slots) == 1
    content = slots[0] / "content"
    assert content.read_text() == "other bytes"
    meta = (slots[0] / "reason.yml").read_text()
    assert "create-overwrite" in meta
    assert "reason: create-overwrite" in result.output
    assert "WARNING" in result.output
    assert str(held_root) in result.output
    assert not (managed / ".blf-held").exists()


def test_revlink_create_leaves_directory_as_real_tree(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """After create, a directory item stays a real tree and the hub has a copy."""
    managed = tmp_path / "managed"
    target = tmp_path / "target"
    managed.mkdir()
    target.mkdir()
    source_dir = target / "hooks"
    source_dir.mkdir()
    (source_dir / "hook.json").write_text('{"on": "save"}')
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"managed:\n  target: {target}\n  subpath: []\n")

    monkeypatch.chdir(target)
    result = invoke_with_daemon(config_path, ["revlink", "create", "hooks"], isolated_home)

    assert result.exit_code == 0, result.output
    assert source_dir.is_dir()
    assert not source_dir.is_symlink()
    assert (source_dir / "hook.json").read_text() == '{"on": "save"}'
    hub_copy = managed / "hooks"
    assert hub_copy.is_dir()
    assert not hub_copy.is_symlink()
    assert (hub_copy / "hook.json").read_text() == '{"on": "save"}'
    assert "- hooks" in config_path.read_text()


def _write_item_on_two_targets(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, Path, Path]:
    """Create a hub copy and two target copies of item.txt.

    Args:
        tmp_path: Test root.

    Returns:
        ``(config_path, managed_item, first_item, second_item, first_target, second_target)``.
    """
    managed = tmp_path / "managed"
    first_target = tmp_path / "target-one"
    second_target = tmp_path / "target-two"
    for directory in (managed, first_target, second_target):
        directory.mkdir()
    managed_item = managed / "item.txt"
    first_item = first_target / "item.txt"
    second_item = second_target / "item.txt"
    managed_item.write_text("shared content")
    first_item.write_text("shared content")
    second_item.write_text("shared content")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"""managed:
  target: [{first_target}, {second_target}]
  subpath:
    - item.txt
"""
    )
    return config_path, managed_item, first_item, second_item, first_target, second_target


def test_revlink_restore_deletes_hub_and_leaves_other_targets_unmanaged(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Restore deletes the hub copy, keeps this target's file, and leaves other copies."""
    config_path, managed_item, first_item, second_item, first_target, _second_target = _write_item_on_two_targets(
        tmp_path
    )

    monkeypatch.chdir(first_target)
    result = invoke_with_daemon(config_path, ["revlink", "restore", "item.txt"], isolated_home)

    assert result.exit_code == 0, result.output
    assert not managed_item.exists()
    assert first_item.is_file()
    assert not first_item.is_symlink()
    assert first_item.read_text() == "shared content"
    assert second_item.is_file()
    assert not second_item.is_symlink()
    assert second_item.read_text() == "shared content"
    assert "subpath: []" in config_path.read_text()


def test_revlink_restore_unregisters_item_from_every_participating_mapping(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Restore drops the subpath from every mapping so leftover copies are unmanaged."""
    managed = tmp_path / "managed"
    first_target = tmp_path / "target-one"
    second_target = tmp_path / "target-two"
    for directory in (managed, first_target, second_target):
        directory.mkdir()
    (managed / "item.txt").write_text("shared content")
    (first_target / "item.txt").write_text("shared content")
    (second_target / "item.txt").write_text("shared content")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"""managed:
  - target: {first_target}
    subpath:
      - item.txt
  - target: {second_target}
    subpath:
      - item.txt
"""
    )

    monkeypatch.chdir(first_target)
    result = invoke_with_daemon(config_path, ["revlink", "restore", "item.txt"], isolated_home)

    assert result.exit_code == 0, result.output
    assert not (managed / "item.txt").exists()
    assert (first_target / "item.txt").read_text() == "shared content"
    assert (second_target / "item.txt").read_text() == "shared content"
    updated = config_path.read_text()
    assert "subpath: []" in updated
    assert "- item.txt" not in updated


def test_revlink_restore_leaves_directory_in_this_target(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Restore deletes a hub directory and leaves this target's real tree."""
    managed = tmp_path / "managed"
    target = tmp_path / "target"
    managed.mkdir()
    target.mkdir()
    hub_dir = managed / "hooks"
    target_dir = target / "hooks"
    hub_dir.mkdir()
    target_dir.mkdir()
    (hub_dir / "hook.json").write_text('{"on": "save"}')
    (target_dir / "hook.json").write_text('{"on": "save"}')
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"""managed:
  target: {target}
  subpath:
    - hooks
"""
    )

    monkeypatch.chdir(target)
    result = invoke_with_daemon(config_path, ["revlink", "restore", "hooks"], isolated_home)

    assert result.exit_code == 0, result.output
    assert not hub_dir.exists()
    assert target_dir.is_dir()
    assert not target_dir.is_symlink()
    assert (target_dir / "hook.json").read_text() == '{"on": "save"}'


def test_remove_deletes_hub_copy_and_every_projection(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Remove deletes the hub copy and every target projection of that item."""
    config_path, managed_item, first_item, second_item, first_target, _second_target = _write_item_on_two_targets(
        tmp_path
    )
    first_exclude = _make_git_repo(first_target)
    first_exclude.write_text("# preserved\nitem.txt\n")
    second_exclude = _make_git_repo(_second_target)
    second_exclude.write_text("# preserved\nitem.txt\n")

    monkeypatch.chdir(first_target)
    result = invoke_with_daemon(config_path, ["remove", "item.txt"], isolated_home)

    assert result.exit_code == 0, result.output
    assert not managed_item.exists()
    assert not first_item.exists()
    assert not second_item.exists()
    assert "item.txt" not in first_exclude.read_text()
    assert "item.txt" not in second_exclude.read_text()
    assert "subpath: []" in config_path.read_text()


def test_remove_deletes_directory_hub_and_projections(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Remove deletes a hub directory tree and every target copy of it."""
    managed = tmp_path / "managed"
    first_target = tmp_path / "target-one"
    second_target = tmp_path / "target-two"
    for directory in (managed, first_target, second_target):
        directory.mkdir()
    for root in (managed, first_target, second_target):
        hooks = root / "hooks"
        hooks.mkdir()
        (hooks / "hook.json").write_text('{"on": "save"}')
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"""managed:
  target: [{first_target}, {second_target}]
  subpath:
    - hooks
"""
    )

    monkeypatch.chdir(first_target)
    result = invoke_with_daemon(config_path, ["remove", "hooks"], isolated_home)

    assert result.exit_code == 0, result.output
    assert not (managed / "hooks").exists()
    assert not (first_target / "hooks").exists()
    assert not (second_target / "hooks").exists()
