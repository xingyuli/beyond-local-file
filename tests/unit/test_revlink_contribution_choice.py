"""CLI seams for choosing a managed project when several contribute to one target."""

from __future__ import annotations

from pathlib import Path

from tests.daemon_support import invoke_with_daemon

_HUB_A = "quvanai-qimiolab"
_HUB_B = "some-other-hub"


def _write_item(root: Path, name: str, content: str) -> None:
    """Write a managed item, creating parent directories as needed."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _write_two_hubs(
    tmp_path: Path,
    *,
    a_items: list[str] | None = None,
    b_items: list[str] | None = None,
) -> tuple[Path, Path, Path, Path]:
    """Two selective managed projects targeting one directory.

    Args:
        tmp_path: Test root.
        a_items: Declared subpaths for the first hub. ``None`` seeds a disjoint placeholder.
        b_items: Declared subpaths for the second hub. ``None`` seeds a disjoint placeholder.

    Returns:
        Config path, hub A, hub B, and the shared target.
    """
    hub_a = tmp_path / _HUB_A
    hub_b = tmp_path / _HUB_B
    target = tmp_path / "target"
    hub_a.mkdir()
    hub_b.mkdir()
    target.mkdir()
    a_sub = list(a_items) if a_items is not None else ["a-only.txt"]
    b_sub = list(b_items) if b_items is not None else ["b-only.txt"]
    for name in a_sub:
        _write_item(hub_a, name, f"from-a:{name}\n")
        _write_item(target, name, f"from-a:{name}\n")
    for name in b_sub:
        _write_item(hub_b, name, f"from-b:{name}\n")
        _write_item(target, name, f"from-b:{name}\n")

    def _subpath_block(names: list[str]) -> str:
        body = "\n".join(f"    - {name}" for name in names)
        return f"  subpath:\n{body}"

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"{_HUB_A}:\n  target: {target}\n{_subpath_block(a_sub)}\n"
        f"{_HUB_B}:\n  target: {target}\n{_subpath_block(b_sub)}\n"
    )
    return config_path, hub_a, hub_b, target


def test_create_prompts_then_copies_into_chosen_hub(tmp_path: Path, monkeypatch, isolated_home: dict[str, str]) -> None:
    """Two hubs target CWD and PATH is new: numbered prompt, then create on the choice."""
    config_path, hub_a, hub_b, target = _write_two_hubs(tmp_path)
    (target / ".env").write_text("secret=1\n")
    monkeypatch.chdir(target)

    result = invoke_with_daemon(
        config_path,
        ["revlink", "create", ".env"],
        isolated_home,
        input="1\n",
    )

    assert result.exit_code == 0, result.output
    assert "More than one managed project contributes to this directory:" in result.output
    assert f"  1. {_HUB_A}" in result.output
    assert f"  2. {_HUB_B}" in result.output
    assert "Choose a managed project:" in result.output
    assert "Copying" in result.output
    assert f"{_HUB_A}/.env" in result.output
    assert (hub_a / ".env").read_text() == "secret=1\n"
    assert not (hub_b / ".env").exists()
    assert (target / ".env").read_text() == "secret=1\n"


def test_create_unique_project_does_not_prompt(tmp_path: Path, monkeypatch, isolated_home: dict[str, str]) -> None:
    """A single managed project targeting CWD never interviews for a hub."""
    managed = tmp_path / "managed"
    target = tmp_path / "target"
    managed.mkdir()
    target.mkdir()
    (managed / "keep.txt").write_text("keep\n")
    (target / "keep.txt").write_text("keep\n")
    (target / ".env").write_text("secret=1\n")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"managed:\n  target: {target}\n  subpath:\n    - keep.txt\n")
    monkeypatch.chdir(target)

    result = invoke_with_daemon(config_path, ["revlink", "create", ".env"], isolated_home)

    assert result.exit_code == 0, result.output
    assert "Choose a managed project" not in result.output
    assert (managed / ".env").read_text() == "secret=1\n"


def test_create_multi_hub_without_input_lists_names_and_does_not_copy(
    tmp_path: Path, monkeypatch, isolated_home: dict[str, str]
) -> None:
    """No TTY / no choice on a new path: exit 1, names in output, hubs unchanged."""
    config_path, hub_a, hub_b, target = _write_two_hubs(tmp_path)
    (target / ".env").write_text("secret=1\n")
    monkeypatch.chdir(target)

    result = invoke_with_daemon(config_path, ["revlink", "create", ".env"], isolated_home)

    assert result.exit_code == 1
    assert _HUB_A in result.output
    assert _HUB_B in result.output
    assert not (hub_a / ".env").exists()
    assert not (hub_b / ".env").exists()
    assert (target / ".env").read_text() == "secret=1\n"


def test_restore_owned_path_uses_that_hub(tmp_path: Path, monkeypatch, isolated_home: dict[str, str]) -> None:
    """Restore on a multi-contributor target follows the PATH owner, not CWD ambiguity."""
    config_path, hub_a, hub_b, target = _write_two_hubs(tmp_path, a_items=[".env", "a-keep.txt"], b_items=[".vscode"])
    monkeypatch.chdir(target)

    result = invoke_with_daemon(config_path, ["revlink", "restore", ".env"], isolated_home)

    assert result.exit_code == 0, result.output
    assert "Ambiguous" not in result.output
    assert not (hub_a / ".env").exists()
    assert (hub_b / ".vscode").read_text() == "from-b:.vscode\n"
    assert (target / ".env").read_text() == "from-a:.env\n"
    assert (target / ".vscode").read_text() == "from-b:.vscode\n"
    assert "- .env" not in config_path.read_text()
    assert "- .vscode" in config_path.read_text()


def test_restore_unowned_path_is_not_managed(tmp_path: Path, monkeypatch, isolated_home: dict[str, str]) -> None:
    """Restore of a path neither hub owns is not-managed, not CWD-ambiguous."""
    config_path, hub_a, hub_b, target = _write_two_hubs(tmp_path, a_items=[".env", "a-keep.txt"], b_items=[".vscode"])
    stray = target / "notes.txt"
    stray.write_text("local\n")
    monkeypatch.chdir(target)

    result = invoke_with_daemon(config_path, ["revlink", "restore", "notes.txt"], isolated_home)

    assert result.exit_code == 1
    assert "Ambiguous" not in result.output
    assert "not a managed item" in result.output.lower() or "not managed" in result.output.lower()
    assert stray.read_text() == "local\n"
    assert (hub_a / ".env").read_text() == "from-a:.env\n"
    assert (hub_b / ".vscode").read_text() == "from-b:.vscode\n"


def test_remove_owned_path_uses_that_hub(tmp_path: Path, monkeypatch, isolated_home: dict[str, str]) -> None:
    """Remove on a multi-contributor target follows the PATH owner, not CWD ambiguity."""
    config_path, hub_a, hub_b, target = _write_two_hubs(tmp_path, a_items=[".env", "a-keep.txt"], b_items=[".vscode"])
    monkeypatch.chdir(target)

    result = invoke_with_daemon(config_path, ["remove", ".env"], isolated_home)

    assert result.exit_code == 0, result.output
    assert "Ambiguous" not in result.output
    assert not (hub_a / ".env").exists()
    assert not (target / ".env").exists()
    assert (hub_b / ".vscode").read_text() == "from-b:.vscode\n"
    assert (target / ".vscode").read_text() == "from-b:.vscode\n"
    assert "- .env" not in config_path.read_text()
    assert "- .vscode" in config_path.read_text()


def test_remove_unowned_path_is_not_managed(tmp_path: Path, monkeypatch, isolated_home: dict[str, str]) -> None:
    """Remove of a path neither hub owns is not-managed, not CWD-ambiguous."""
    config_path, hub_a, hub_b, target = _write_two_hubs(tmp_path, a_items=[".env", "a-keep.txt"], b_items=[".vscode"])
    stray = target / "notes.txt"
    stray.write_text("local\n")
    monkeypatch.chdir(target)

    result = invoke_with_daemon(config_path, ["remove", "notes.txt"], isolated_home)

    assert result.exit_code == 1
    assert "Ambiguous" not in result.output
    assert "not a managed item" in result.output.lower() or "not managed" in result.output.lower()
    assert stray.read_text() == "local\n"
    assert (hub_a / ".env").read_text() == "from-a:.env\n"
    assert (target / ".env").read_text() == "from-a:.env\n"
    assert (hub_b / ".vscode").read_text() == "from-b:.vscode\n"
