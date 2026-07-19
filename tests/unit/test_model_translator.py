"""Tests for model translation layer (config → processing).

The translator is a pure mapping-expansion and display-name function once the
``item_loader`` seam is used.  Tests are divided into five groups:

1. ``TestDisplayNameGeneration``    — pure display-name logic, no disk I/O.
2. ``TestItemLoader``               — unit tests for ``_load_items`` (the default
                                     filesystem adapter), using ``tmp_path``.
3. ``TestItemsLoading``             — integration-style tests that exercise the
                                     full pipeline (loader + translator together).
4. ``TestMultipleProjects``         — multi-project scenarios.
5. ``TestProcessingUnitAttributes`` — attribute-level correctness.
"""

from pathlib import Path

import pytest

from beyond_local_file.model import ConfigProject, Mapping, translate_config_to_processing
from beyond_local_file.model.processing import LinkStrategy, ManagedProjectItem
from beyond_local_file.model.translator import _load_items

# ---------------------------------------------------------------------------
# Shared stub loader — returns one fake item regardless of arguments.
# Used by tests that exercise display-name / mapping-expansion logic only
# and should not touch the disk.
# ---------------------------------------------------------------------------


def _fake_loader(path: Path, subpaths: list[str] | None, copy_paths: set[str] | None) -> list[ManagedProjectItem]:
    """Deterministic stub: always returns one symlink item named 'stub'."""
    return [ManagedProjectItem(name="stub", path=path / "stub", strategy=LinkStrategy.SYMLINK)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(
    tmp_path: Path,
    *,
    name: str = "my-project",
    mappings: list[Mapping],
) -> dict[str, ConfigProject]:
    """Build a minimal config_projects dict using a non-existent base path."""
    return {
        name: ConfigProject(
            managed_project_name=name,
            managed_project_path=tmp_path / name,
            mappings=mappings,
        )
    }


# ---------------------------------------------------------------------------
# 1. Display-name generation (pure — no disk I/O via _fake_loader)
# ---------------------------------------------------------------------------


class TestDisplayNameGeneration:
    """Display-name logic is pure once item_loader is stubbed out."""

    def test_single_mapping_single_target_no_suffix(self, tmp_path: Path) -> None:
        """Single mapping with single target should have no suffix."""
        projects = _make_project(
            tmp_path,
            mappings=[Mapping(targets=[Path("/target1")], subpaths=None, copy_paths=None)],
        )
        units = translate_config_to_processing(projects, item_loader=_fake_loader)

        assert len(units) == 1
        assert units[0].display_name == "my-project"
        assert units[0].mapping_index == 0
        assert units[0].target_index == 0

    def test_multiple_mappings_single_target_each(self, tmp_path: Path) -> None:
        """Multiple mappings with single target each should use #N format."""
        projects = _make_project(
            tmp_path,
            mappings=[
                Mapping(targets=[Path("/t1")], subpaths=None, copy_paths=None),
                Mapping(targets=[Path("/t2")], subpaths=None, copy_paths=None),
                Mapping(targets=[Path("/t3")], subpaths=None, copy_paths=None),
            ],
        )
        units = translate_config_to_processing(projects, item_loader=_fake_loader)

        assert len(units) == 3  # noqa: PLR2004
        assert units[0].display_name == "my-project#1"
        assert units[1].display_name == "my-project#2"
        assert units[2].display_name == "my-project#3"

    def test_single_mapping_multiple_targets(self, tmp_path: Path) -> None:
        """Single mapping with multiple targets should use #N-M format."""
        projects = _make_project(
            tmp_path,
            mappings=[
                Mapping(
                    targets=[Path("/t1"), Path("/t2"), Path("/t3")],
                    subpaths=None,
                    copy_paths=None,
                )
            ],
        )
        units = translate_config_to_processing(projects, item_loader=_fake_loader)

        assert len(units) == 3  # noqa: PLR2004
        assert units[0].display_name == "my-project#1-1"
        assert units[1].display_name == "my-project#1-2"
        assert units[2].display_name == "my-project#1-3"

    def test_multiple_mappings_mixed_targets(self, tmp_path: Path) -> None:
        """Multiple mappings with mixed target counts."""
        projects = _make_project(
            tmp_path,
            mappings=[
                Mapping(targets=[Path("/t1")], subpaths=None, copy_paths=None),
                Mapping(targets=[Path("/t2"), Path("/t3")], subpaths=None, copy_paths=None),
                Mapping(targets=[Path("/t4")], subpaths=None, copy_paths=None),
            ],
        )
        units = translate_config_to_processing(projects, item_loader=_fake_loader)

        assert len(units) == 4  # noqa: PLR2004
        assert units[0].display_name == "my-project#1"
        assert units[1].display_name == "my-project#2-1"
        assert units[2].display_name == "my-project#2-2"
        assert units[3].display_name == "my-project#3"

    def test_padding_when_mapping_index_reaches_10(self, tmp_path: Path) -> None:
        """Zero-padding applied when mapping index >= 10."""
        mappings = [Mapping(targets=[Path(f"/t{i}")], subpaths=None, copy_paths=None) for i in range(1, 12)]
        projects = _make_project(tmp_path, mappings=mappings)
        units = translate_config_to_processing(projects, item_loader=_fake_loader)

        assert len(units) == 11  # noqa: PLR2004
        assert units[0].display_name == "my-project#01"
        assert units[8].display_name == "my-project#09"
        assert units[9].display_name == "my-project#10"
        assert units[10].display_name == "my-project#11"

    def test_padding_when_target_index_reaches_10(self, tmp_path: Path) -> None:
        """Zero-padding applied when target index >= 10."""
        targets = [Path(f"/t{i}") for i in range(1, 12)]
        projects = _make_project(
            tmp_path,
            mappings=[Mapping(targets=targets, subpaths=None, copy_paths=None)],
        )
        units = translate_config_to_processing(projects, item_loader=_fake_loader)

        assert len(units) == 11  # noqa: PLR2004
        assert units[0].display_name == "my-project#1-01"
        assert units[8].display_name == "my-project#1-09"
        assert units[9].display_name == "my-project#1-10"
        assert units[10].display_name == "my-project#1-11"

    def test_padding_both_indices(self, tmp_path: Path) -> None:
        """Zero-padding on both indices when both >= 10."""
        mappings = [
            Mapping(
                targets=[Path(f"/t{i}-{j}") for j in range(1, 12)],
                subpaths=None,
                copy_paths=None,
            )
            for i in range(1, 12)
        ]
        projects = _make_project(tmp_path, mappings=mappings)
        units = translate_config_to_processing(projects, item_loader=_fake_loader)

        assert len(units) == 121  # noqa: PLR2004
        assert units[0].display_name == "my-project#01-01"
        assert units[10].display_name == "my-project#01-11"
        assert units[110].display_name == "my-project#11-01"
        assert units[120].display_name == "my-project#11-11"

    def test_empty_loader_result_skips_unit(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Units whose item list is empty are skipped with an info message."""
        projects = _make_project(
            tmp_path,
            mappings=[Mapping(targets=[Path("/t1")], subpaths=None, copy_paths=None)],
        )
        units = translate_config_to_processing(
            projects,
            item_loader=lambda path, sp, cp: [],
        )

        assert units == []
        captured = capsys.readouterr()
        assert "Skipping" in captured.out


# ---------------------------------------------------------------------------
# 2. _load_items — the default filesystem adapter, tested in isolation
# ---------------------------------------------------------------------------


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Real project directory with a known layout."""
    d = tmp_path / "test-project"
    d.mkdir()
    (d / "file1.txt").write_text("content1")
    (d / "file2.txt").write_text("content2")
    kiro = d / ".kiro"
    kiro.mkdir()
    hooks = kiro / "hooks"
    hooks.mkdir()
    (hooks / "hook.json").write_text("{}")
    return d


class TestItemLoader:
    """Unit tests for _load_items (the real filesystem adapter)."""

    def test_sync_all_enumerates_top_level_items(self, project_dir: Path) -> None:
        """No subpaths → all top-level entries returned as SYMLINK items."""
        items = _load_items(project_dir, None, None)

        names = {i.name for i in items}
        assert names == {"file1.txt", "file2.txt", ".kiro"}
        assert all(i.strategy == LinkStrategy.SYMLINK for i in items)

    def test_sync_all_returns_empty_for_empty_directory(self, tmp_path: Path) -> None:
        """Empty directory with no subpaths → empty list (unit skipped by translator)."""
        empty = tmp_path / "empty"
        empty.mkdir()
        assert _load_items(empty, None, None) == []

    def test_sync_all_returns_empty_for_nonexistent_directory(self, tmp_path: Path) -> None:
        """Non-existent directory with no subpaths → empty list."""
        assert _load_items(tmp_path / "ghost", None, None) == []

    def test_subpath_list_returns_only_named_items(self, project_dir: Path) -> None:
        """Explicit subpaths → only those entries, all SYMLINK by default."""
        items = _load_items(project_dir, ["file1.txt", ".kiro/hooks"], None)

        names = {i.name for i in items}
        assert names == {"file1.txt", ".kiro/hooks"}
        assert all(i.strategy == LinkStrategy.SYMLINK for i in items)

    def test_copy_paths_set_assigns_copy_strategy(self, project_dir: Path) -> None:
        """Items in copy_paths get COPY strategy; others remain SYMLINK."""
        items = _load_items(project_dir, ["file1.txt", "file2.txt"], {"file1.txt"})

        by_name = {i.name: i for i in items}
        assert by_name["file1.txt"].strategy == LinkStrategy.COPY
        assert by_name["file2.txt"].strategy == LinkStrategy.SYMLINK

    def test_nonexistent_subpath_is_skipped(self, project_dir: Path) -> None:
        """Subpath entries that don't exist on disk are silently skipped."""
        items = _load_items(project_dir, ["file1.txt", "ghost.txt"], None)

        assert len(items) == 1
        assert items[0].name == "file1.txt"

    def test_copy_strategy_on_directory_raises(self, project_dir: Path) -> None:
        """Copy strategy applied to a directory raises ValueError."""
        with pytest.raises(ValueError, match="Copy strategy is not supported for directories"):
            _load_items(project_dir, [".kiro/hooks"], {".kiro/hooks"})

    def test_item_paths_are_absolute(self, project_dir: Path) -> None:
        """All returned item.path values are absolute."""
        items = _load_items(project_dir, ["file1.txt"], None)

        assert all(i.path.is_absolute() for i in items)

    def test_item_path_points_inside_project_dir(self, project_dir: Path) -> None:
        """item.path is project_dir / item.name."""
        items = _load_items(project_dir, ["file1.txt"], None)

        assert items[0].path == project_dir / "file1.txt"


# ---------------------------------------------------------------------------
# 3. Full pipeline integration (loader + translator together, needs disk)
# ---------------------------------------------------------------------------


class TestItemsLoading:
    """Pipeline tests that use the real _load_items adapter via tmp_path."""

    def test_no_subpaths_expands_all_items(self, project_dir: Path) -> None:
        """Sync-all mapping: all top-level items, all SYMLINK."""
        projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=project_dir,
                mappings=[Mapping(targets=[Path("/t1")], subpaths=None, copy_paths=None)],
            )
        }
        units = translate_config_to_processing(projects)

        assert len(units) == 1
        assert len(units[0].items) == 3  # noqa: PLR2004
        assert all(i.strategy == LinkStrategy.SYMLINK for i in units[0].items)
        assert {i.name for i in units[0].items} == {"file1.txt", "file2.txt", ".kiro"}

    def test_with_subpaths_loads_named_items(self, project_dir: Path) -> None:
        """Selective-sync mapping: only named subpaths returned."""
        projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=project_dir,
                mappings=[
                    Mapping(
                        targets=[Path("/t1")],
                        subpaths=["file1.txt", ".kiro/hooks"],
                        copy_paths=None,
                    )
                ],
            )
        }
        units = translate_config_to_processing(projects)

        assert len(units) == 1
        assert {i.name for i in units[0].items} == {"file1.txt", ".kiro/hooks"}

    def test_with_copy_paths_assigns_strategy(self, project_dir: Path) -> None:
        """copy_paths membership drives COPY vs SYMLINK strategy."""
        projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=project_dir,
                mappings=[
                    Mapping(
                        targets=[Path("/t1")],
                        subpaths=["file1.txt", "file2.txt"],
                        copy_paths={"file1.txt"},
                    )
                ],
            )
        }
        units = translate_config_to_processing(projects)

        by_name = {i.name: i for i in units[0].items}
        assert by_name["file1.txt"].strategy == LinkStrategy.COPY
        assert by_name["file2.txt"].strategy == LinkStrategy.SYMLINK

    def test_copy_strategy_on_directory_raises(self, project_dir: Path) -> None:
        """Copy strategy on a directory bubbles up from _load_items."""
        projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=project_dir,
                mappings=[
                    Mapping(
                        targets=[Path("/t1")],
                        subpaths=[".kiro/hooks"],
                        copy_paths={".kiro/hooks"},
                    )
                ],
            )
        }
        with pytest.raises(ValueError, match="Copy strategy is not supported for directories"):
            translate_config_to_processing(projects)

    def test_nonexistent_subpath_skipped(self, project_dir: Path) -> None:
        """Missing subpath entries are silently skipped."""
        projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=project_dir,
                mappings=[
                    Mapping(
                        targets=[Path("/t1")],
                        subpaths=["file1.txt", "ghost.txt"],
                        copy_paths=None,
                    )
                ],
            )
        }
        units = translate_config_to_processing(projects)

        assert len(units) == 1
        assert len(units[0].items) == 1
        assert units[0].items[0].name == "file1.txt"


# ---------------------------------------------------------------------------
# 4. Multiple projects
# ---------------------------------------------------------------------------


class TestMultipleProjects:
    """Multiple projects each produce their own processing units."""

    def test_multiple_projects(self, tmp_path: Path) -> None:
        project_a = tmp_path / "project-a"
        project_a.mkdir()

        project_b = tmp_path / "project-b"
        project_b.mkdir()

        config_projects = {
            "project-a": ConfigProject(
                managed_project_name="project-a",
                managed_project_path=project_a,
                mappings=[
                    Mapping(targets=[Path("/t1")], subpaths=None, copy_paths=None),
                    Mapping(targets=[Path("/t2")], subpaths=None, copy_paths=None),
                ],
            ),
            "project-b": ConfigProject(
                managed_project_name="project-b",
                managed_project_path=project_b,
                mappings=[Mapping(targets=[Path("/t3")], subpaths=None, copy_paths=None)],
            ),
        }

        units = translate_config_to_processing(config_projects, item_loader=_fake_loader)

        assert len(units) == 3  # noqa: PLR2004

        a_units = [u for u in units if u.managed_project_name == "project-a"]
        assert len(a_units) == 2  # noqa: PLR2004
        assert a_units[0].display_name == "project-a#1"
        assert a_units[1].display_name == "project-a#2"

        b_units = [u for u in units if u.managed_project_name == "project-b"]
        assert len(b_units) == 1
        assert b_units[0].display_name == "project-b"


# ---------------------------------------------------------------------------
# 5. ProcessingUnit attribute correctness
# ---------------------------------------------------------------------------


class TestProcessingUnitAttributes:
    """Verify all ProcessingUnit fields are set correctly."""

    def test_processing_unit_attributes(self, tmp_path: Path) -> None:
        base = tmp_path / "my-project"
        projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=base,
                mappings=[
                    Mapping(
                        targets=[Path("/t1"), Path("/t2")],
                        subpaths=None,
                        copy_paths=None,
                    )
                ],
            )
        }
        units = translate_config_to_processing(projects, item_loader=_fake_loader)

        assert len(units) == 2  # noqa: PLR2004

        u0 = units[0]
        assert u0.managed_project_name == "my-project"
        assert u0.managed_project_path == base
        assert u0.target_project_path == Path("/t1")
        assert u0.display_name == "my-project#1-1"
        assert u0.mapping_index == 0
        assert u0.target_index == 0
        assert len(u0.items) == 1

        u1 = units[1]
        assert u1.target_project_path == Path("/t2")
        assert u1.display_name == "my-project#1-2"
        assert u1.mapping_index == 0
        assert u1.target_index == 1
