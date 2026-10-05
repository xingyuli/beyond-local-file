"""Property-based coverage for the public ``blf remove`` command seam."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from click.testing import CliRunner
from hypothesis import given, settings
from hypothesis import strategies as st

from beyond_local_file.cli import cli
from beyond_local_file.operations.remove import RemoveFormatter, RemoveOperation
from beyond_local_file.project_processor import RevlinkResolveError, resolve_revlink_context
from tests.daemon_support import invoke_with_daemon
from tests.path_strategies import is_safe_fs_name

_component = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"),
    min_size=1,
    max_size=12,
).filter(is_safe_fs_name)


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
        config.write_text(f"managed: {target.as_posix()}\n")
        previous_cwd = Path.cwd()
        try:
            os.chdir(target)
            result = invoke_with_daemon(config, ["remove", f"./unused/../{item_name}"])
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

        mappings = [f"  - target: {targets[0].as_posix()}\n    subpath:\n      - item.txt\n"]
        for target, participates_for_target in zip(targets[1:], participates, strict=True):
            entry = "item.txt" if participates_for_target else "other.txt"
            mappings.append(f"  - target: {target.as_posix()}\n    subpath:\n      - {entry}\n")
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
            result = invoke_with_daemon(config, ["remove", "item.txt"])
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
@given(content=st.binary(min_size=1, max_size=64))
def test_remove_copy_mismatch_never_mutates_persistent_state(content: bytes) -> None:
    """A drifted regular-file projection is refused before any cleanup.

    Args:
        content: Bytes that differ from the managed copy.
    """
    if content == b"authoritative":
        content = b"divergent"
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        managed = root / "managed"
        target = root / "target"
        managed.mkdir()
        target.mkdir()
        managed_item = managed / "item.txt"
        managed_item.write_text("authoritative")
        target_item = target / "item.txt"
        target_item.write_bytes(content)
        exclude = target / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True)
        exclude.write_text("item.txt\n")
        config = root / "config.yml"
        config.write_text(f"managed:\n  target: {target.as_posix()}\n  subpath:\n    - item.txt\n")
        before = {
            "config": config.read_bytes(),
            "exclude": exclude.read_bytes(),
            "managed": managed_item.read_bytes(),
            "target_content": target_item.read_bytes(),
        }

        previous_cwd = Path.cwd()
        try:
            os.chdir(target)
            context = resolve_revlink_context(str(config), Path.cwd())
            assert not isinstance(context, RevlinkResolveError)
            exit_code = RemoveOperation(
                source=target_item,
                rel_path=Path("item.txt"),
                dry_run=False,
                formatter=RemoveFormatter(dry_run=False),
                context=context,
            ).run()
        finally:
            os.chdir(previous_cwd)

        assert exit_code == 1
        assert config.read_bytes() == before["config"]
        assert exclude.read_bytes() == before["exclude"]
        assert managed_item.read_bytes() == before["managed"]
        assert target_item.read_bytes() == before["target_content"]
