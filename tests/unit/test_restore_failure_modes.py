"""Leftover-symlink materialize lives on LiveSync.restore_item."""

from pathlib import Path
from unittest.mock import patch

import pytest

from beyond_local_file.daemon.live import LiveSync
from beyond_local_file.model.config import ConfigProject, Mapping


def _live(hub: Path, replica: Path) -> LiveSync:
    project = ConfigProject(
        managed_project_name="lab-app",
        managed_project_path=hub,
        mappings=[Mapping(targets=[replica], subpaths=["data.txt"])],
    )
    return LiveSync({"lab-app": project}, {})


def _make_symlink(link: Path, target: Path) -> None:
    link.symlink_to(target)


def test_copy_oserror_propagates_and_preserves_managed(tmp_path: Path) -> None:
    """copy_projection OSError propagates; the hub copy is unchanged."""
    hub = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    hub.mkdir()
    alpha.mkdir()
    managed = hub / "data.txt"
    managed.write_text("managed content")
    source = alpha / "data.txt"
    _make_symlink(source, managed)
    live = _live(hub, alpha)

    with (
        patch("beyond_local_file.daemon.live.copy_projection", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        live.restore_item(alpha, "data.txt")

    assert managed.read_text() == "managed content"


def test_leftover_symlink_restore_materializes_then_deletes_hub(tmp_path: Path) -> None:
    """restore_item replaces the symlink with hub bytes, then deletes the hub copy."""
    hub = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    hub.mkdir()
    alpha.mkdir()
    managed = hub / "data.txt"
    managed.write_text("managed content")
    source = alpha / "data.txt"
    _make_symlink(source, managed)

    facts = _live(hub, alpha).restore_item(alpha, "data.txt")

    assert facts.leftover_symlink is True
    assert facts.error is None
    assert source.is_file()
    assert not source.is_symlink()
    assert source.read_text() == "managed content"
    assert not managed.exists()


def test_permission_error_on_unlink_returns_an_error_and_skips_the_copy(tmp_path: Path) -> None:
    """A permission error unlinking the symlink does not copy or delete the hub."""
    hub = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    hub.mkdir()
    alpha.mkdir()
    managed = hub / "data.txt"
    managed.write_text("managed content")
    source = alpha / "data.txt"
    _make_symlink(source, managed)

    with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
        facts = _live(hub, alpha).restore_item(alpha, "data.txt")

    assert facts.leftover_symlink is True
    assert facts.error == f"Permission denied removing symlink at {source}"
    assert source.is_symlink()
    assert managed.read_text() == "managed content"
