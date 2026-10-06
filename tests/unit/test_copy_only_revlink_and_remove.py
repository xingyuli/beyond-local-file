"""Copy-only revlink create, restore, and remove at the public command seams."""

import hashlib
from pathlib import Path

from beyond_local_file.configuration_set import ConfigurationSet
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
    assert not (ConfigurationSet(config_path).run_directory / "sync-state.yml").exists()

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
    assert not (ConfigurationSet(config_path).run_directory / "sync-state.yml").exists()


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
        ``(config_path, hub_item, alpha_item, example_item, alpha, example)``.
    """
    hub = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    example = tmp_path / "example"
    for directory in (hub, alpha, example):
        directory.mkdir()
    hub_item = hub / "item.txt"
    alpha_item = alpha / "item.txt"
    example_item = example / "item.txt"
    hub_item.write_text("shared content")
    alpha_item.write_text("shared content")
    example_item.write_text("shared content")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"""lab-app:
  target: [{alpha}, {example}]
  subpath:
    - item.txt
"""
    )
    return config_path, hub_item, alpha_item, example_item, alpha, example


def test_revlink_restore_from_alpha_deletes_example_projection(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Restore from alpha deletes the hub and example copies; alpha's file remains."""
    hub = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    example = tmp_path / "example"
    for directory in (hub, alpha, example):
        directory.mkdir()
    (hub / "notes.md").write_text("shared notes")
    (alpha / "notes.md").write_text("shared notes")
    (example / "notes.md").write_text("shared notes")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"""lab-app:
  target: [{alpha}, {example}]
  subpath:
    - notes.md
"""
    )

    monkeypatch.chdir(alpha)
    result = invoke_with_daemon(config_path, ["revlink", "restore", "notes.md"], isolated_home)

    assert result.exit_code == 0, result.output
    assert not (hub / "notes.md").exists()
    assert (alpha / "notes.md").is_file()
    assert not (alpha / "notes.md").is_symlink()
    assert (alpha / "notes.md").read_text() == "shared notes"
    assert not (example / "notes.md").exists()
    assert "subpath: []" in config_path.read_text()


def test_revlink_restore_strips_git_exclude_on_every_replica(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Restore removes the git exclude on alpha (file remains) and example (file gone)."""
    config_path, hub_item, alpha_item, example_item, alpha, example = _write_item_on_two_targets(tmp_path)
    alpha_exclude = _make_git_repo(alpha)
    alpha_exclude.write_text("# preserved\nitem.txt\n")
    example_exclude = _make_git_repo(example)
    example_exclude.write_text("# preserved\nitem.txt\n")

    monkeypatch.chdir(alpha)
    result = invoke_with_daemon(config_path, ["revlink", "restore", "item.txt"], isolated_home)

    assert result.exit_code == 0, result.output
    assert not hub_item.exists()
    assert alpha_item.is_file()
    assert not example_item.exists()
    assert "item.txt" not in alpha_exclude.read_text()
    assert "# preserved" in alpha_exclude.read_text()
    assert "item.txt" not in example_exclude.read_text()
    assert "# preserved" in example_exclude.read_text()


def test_revlink_restore_unregisters_item_from_every_participating_mapping(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Restore drops the subpath from every mapping and deletes other replicas' copies."""
    hub = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    example = tmp_path / "example"
    for directory in (hub, alpha, example):
        directory.mkdir()
    (hub / "item.txt").write_text("shared content")
    (alpha / "item.txt").write_text("shared content")
    (example / "item.txt").write_text("shared content")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"""lab-app:
  - target: {alpha}
    subpath:
      - item.txt
  - target: {example}
    subpath:
      - item.txt
"""
    )

    monkeypatch.chdir(alpha)
    result = invoke_with_daemon(config_path, ["revlink", "restore", "item.txt"], isolated_home)

    assert result.exit_code == 0, result.output
    assert not (hub / "item.txt").exists()
    assert (alpha / "item.txt").read_text() == "shared content"
    assert not (example / "item.txt").exists()
    updated = config_path.read_text()
    assert "subpath: []" in updated
    assert "- item.txt" not in updated


def test_revlink_restore_leaves_directory_in_this_target(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Restore deletes a hub directory and leaves this target's real tree."""
    hub = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    hub.mkdir()
    alpha.mkdir()
    hub_dir = hub / "hooks"
    alpha_dir = alpha / "hooks"
    hub_dir.mkdir()
    alpha_dir.mkdir()
    (hub_dir / "hook.json").write_text('{"on": "save"}')
    (alpha_dir / "hook.json").write_text('{"on": "save"}')
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"""lab-app:
  target: {alpha}
  subpath:
    - hooks
"""
    )

    monkeypatch.chdir(alpha)
    result = invoke_with_daemon(config_path, ["revlink", "restore", "hooks"], isolated_home)

    assert result.exit_code == 0, result.output
    assert not hub_dir.exists()
    assert alpha_dir.is_dir()
    assert not alpha_dir.is_symlink()
    assert (alpha_dir / "hook.json").read_text() == '{"on": "save"}'


def test_revlink_restore_deletes_other_replica_directory(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Restore from alpha deletes example's directory projection of the item."""
    hub = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    example = tmp_path / "example"
    for directory in (hub, alpha, example):
        directory.mkdir()
    for root in (hub, alpha, example):
        hooks = root / "hooks"
        hooks.mkdir()
        (hooks / "hook.json").write_text('{"on": "save"}')
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"""lab-app:
  target: [{alpha}, {example}]
  subpath:
    - hooks
"""
    )

    monkeypatch.chdir(alpha)
    result = invoke_with_daemon(config_path, ["revlink", "restore", "hooks"], isolated_home)

    assert result.exit_code == 0, result.output
    assert not (hub / "hooks").exists()
    assert (alpha / "hooks" / "hook.json").read_text() == '{"on": "save"}'
    assert not (example / "hooks").exists()


def test_revlink_restore_dry_run_previews_other_replica_without_touching_disks(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Dry-run restore previews example's delete and exclude strip without mutating."""
    config_path, hub_item, alpha_item, example_item, alpha, example = _write_item_on_two_targets(tmp_path)
    alpha_exclude = _make_git_repo(alpha)
    alpha_exclude.write_text("# preserved\nitem.txt\n")
    example_exclude = _make_git_repo(example)
    example_exclude.write_text("# preserved\nitem.txt\n")
    hub_bytes = hub_item.read_text()
    example_bytes = example_item.read_text()

    monkeypatch.chdir(alpha)
    result = invoke_with_daemon(config_path, ["revlink", "restore", "--dry-run", "item.txt"], isolated_home)

    assert result.exit_code == 0, result.output
    assert "[dry-run]" in result.output
    assert "Deleted replica copy:" in result.output
    assert str(example_item) in result.output
    assert hub_item.read_text() == hub_bytes
    assert alpha_item.read_text() == "shared content"
    assert example_item.read_text() == example_bytes
    assert "item.txt" in alpha_exclude.read_text()
    assert "item.txt" in example_exclude.read_text()
    assert "- item.txt" in config_path.read_text()


def test_revlink_restore_leftover_symlink_still_deletes_other_replica(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Leftover symlink at alpha is materialized; example's fan-out copy is deleted."""
    hub = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    example = tmp_path / "example"
    for directory in (hub, alpha, example):
        directory.mkdir()
    hub_item = hub / "notes.md"
    hub_item.write_text("shared notes")
    (alpha / "notes.md").symlink_to(hub_item)
    (example / "notes.md").write_text("shared notes")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"""lab-app:
  target: [{alpha}, {example}]
  subpath:
    - notes.md
"""
    )

    monkeypatch.chdir(alpha)
    result = invoke_with_daemon(config_path, ["revlink", "restore", "notes.md"], isolated_home)

    assert result.exit_code == 0, result.output
    assert not hub_item.exists()
    alpha_item = alpha / "notes.md"
    assert alpha_item.is_file()
    assert not alpha_item.is_symlink()
    assert alpha_item.read_text() == "shared notes"
    assert not (example / "notes.md").exists()


def test_remove_deletes_hub_copy_and_every_projection(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Remove deletes the hub copy and every target projection of that item."""
    config_path, hub_item, alpha_item, example_item, alpha, example = _write_item_on_two_targets(tmp_path)
    alpha_exclude = _make_git_repo(alpha)
    alpha_exclude.write_text("# preserved\nitem.txt\n")
    example_exclude = _make_git_repo(example)
    example_exclude.write_text("# preserved\nitem.txt\n")

    monkeypatch.chdir(alpha)
    result = invoke_with_daemon(config_path, ["remove", "item.txt"], isolated_home)

    assert result.exit_code == 0, result.output
    assert not hub_item.exists()
    assert not alpha_item.exists()
    assert not example_item.exists()
    assert "item.txt" not in alpha_exclude.read_text()
    assert "item.txt" not in example_exclude.read_text()
    assert "subpath: []" in config_path.read_text()


def test_remove_deletes_directory_hub_and_projections(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """Remove deletes a hub directory tree and every target copy of it."""
    hub = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    example = tmp_path / "example"
    for directory in (hub, alpha, example):
        directory.mkdir()
    for root in (hub, alpha, example):
        hooks = root / "hooks"
        hooks.mkdir()
        (hooks / "hook.json").write_text('{"on": "save"}')
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"""lab-app:
  target: [{alpha}, {example}]
  subpath:
    - hooks
"""
    )

    monkeypatch.chdir(alpha)
    result = invoke_with_daemon(config_path, ["remove", "hooks"], isolated_home)

    assert result.exit_code == 0, result.output
    assert not (hub / "hooks").exists()
    assert not (alpha / "hooks").exists()
    assert not (example / "hooks").exists()
