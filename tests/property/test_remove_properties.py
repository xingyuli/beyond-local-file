"""Property-based coverage for the public ``blf remove`` command seam."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from click.testing import CliRunner
from hypothesis import given, settings
from hypothesis import strategies as st

from beyond_local_file.cli import cli

_component = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"),
    min_size=1,
    max_size=12,
).filter(lambda value: value not in {".", ".."})


@settings(max_examples=30)
@given(item_name=_component)
def test_remove_lexically_normalizes_contained_paths(item_name: str) -> None:
    """A lexically normalized contained path identifies the same target item.

    Args:
        item_name: Safe item name embedded in the generated CLI path.
    """
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        managed = root / "managed"
        target = root / "target"
        managed.mkdir()
        target.mkdir()
        (managed / item_name).write_text("content")
        (target / item_name).symlink_to(managed / item_name)
        config = root / "config.yml"
        config.write_text(f"managed: {target}\n")
        previous_cwd = Path.cwd()
        try:
            os.chdir(target)
            result = CliRunner().invoke(cli, ["--config", str(config), "remove", f"./unused/../{item_name}"])
        finally:
            os.chdir(previous_cwd)

        assert result.exit_code == 0, result.output
        assert not (target / item_name).exists()
        assert not (managed / item_name).exists()


@settings(max_examples=30)
@given(parts=st.lists(_component, min_size=1, max_size=3))
def test_remove_rejects_every_generated_path_outside_cwd(parts: list[str]) -> None:
    """A lexical path beginning outside CWD never removes the outside item.

    Args:
        parts: Safe relative components identifying an item above the CWD.
    """
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        target = root / "target"
        target.mkdir()
        outside = root.joinpath(*parts)
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("must remain")
        previous_cwd = Path.cwd()
        try:
            os.chdir(target)
            result = CliRunner().invoke(cli, ["remove", str(Path("..").joinpath(*parts))])
        finally:
            os.chdir(previous_cwd)

        assert result.exit_code == 1
        assert outside.read_text() == "must remain"


@settings(max_examples=30)
@given(participates=st.lists(st.booleans(), min_size=1, max_size=4))
def test_remove_selects_only_generated_participating_mappings(participates: list[bool]) -> None:
    """Only mappings declaring the exact item are removed across a project.

    Args:
        participates: Whether each additional selective mapping declares item.txt.
    """
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        managed = root / "managed"
        managed.mkdir()
        managed_item = managed / "item.txt"
        managed_item.write_text("content")
        targets = [root / f"target-{index}" for index in range(len(participates) + 1)]
        for target in targets:
            target.mkdir()
        (targets[0] / "item.txt").symlink_to(managed_item)

        mappings = [f"  - target: {targets[0]}\n    subpath:\n      - item.txt\n"]
        for target, participates_for_target in zip(targets[1:], participates, strict=True):
            entry = "item.txt" if participates_for_target else "other.txt"
            mappings.append(f"  - target: {target}\n    subpath:\n      - {entry}\n")
            item = target / "item.txt"
            if participates_for_target:
                item.symlink_to(managed_item)
            else:
                item.write_text("incidental")
        config = root / "config.yml"
        config.write_text("managed:\n" + "".join(mappings))

        previous_cwd = Path.cwd()
        try:
            os.chdir(targets[0])
            result = CliRunner().invoke(cli, ["--config", str(config), "remove", "item.txt"])
        finally:
            os.chdir(previous_cwd)

        assert result.exit_code == 0, result.output
        for target, participates_for_target in zip(targets[1:], participates, strict=True):
            item = target / "item.txt"
            if participates_for_target:
                assert not item.exists()
            else:
                assert item.read_text() == "incidental"
        assert not managed_item.exists()


@settings(max_examples=30)
@given(invalid_kind=st.sampled_from(("dangling", "misdirected", "copy-mismatch")))
def test_remove_invalid_projection_never_mutates_persistent_state(invalid_kind: str) -> None:
    """Any generated invalid invocation state leaves all persistent state intact.

    Args:
        invalid_kind: Invalid projection form used to exercise the preflight.
    """
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        managed = root / "managed"
        target = root / "target"
        managed.mkdir()
        target.mkdir()
        managed_item = managed / "item.txt"
        managed_item.write_text("authoritative")
        target_item = target / "item.txt"
        if invalid_kind == "dangling":
            target_item.symlink_to(root / "missing.txt")
            subpath = "    - item.txt\n"
        elif invalid_kind == "misdirected":
            wrong_item = root / "wrong.txt"
            wrong_item.write_text("wrong")
            target_item.symlink_to(wrong_item)
            subpath = "    - item.txt\n"
        else:
            target_item.write_text("divergent")
            subpath = "    - path: item.txt\n      copy: true\n"
        exclude = target / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True)
        exclude.write_text("item.txt\n")
        config = root / "config.yml"
        config.write_text(f"managed:\n  target: {target}\n  subpath:\n{subpath}")
        before = {
            "config": config.read_bytes(),
            "exclude": exclude.read_bytes(),
            "managed": managed_item.read_bytes(),
            "target_link": target_item.readlink() if target_item.is_symlink() else None,
            "target_content": target_item.read_bytes() if not target_item.is_symlink() else None,
        }

        previous_cwd = Path.cwd()
        try:
            os.chdir(target)
            result = CliRunner().invoke(cli, ["--config", str(config), "remove", "item.txt"])
        finally:
            os.chdir(previous_cwd)

        assert result.exit_code == 1
        assert config.read_bytes() == before["config"]
        assert exclude.read_bytes() == before["exclude"]
        assert managed_item.read_bytes() == before["managed"]
        if before["target_link"] is not None:
            assert target_item.is_symlink()
            assert target_item.readlink() == before["target_link"]
        else:
            assert target_item.read_bytes() == before["target_content"]
