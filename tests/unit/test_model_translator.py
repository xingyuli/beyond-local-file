"""Tests for model translation layer (config → processing)."""

from pathlib import Path

import pytest

from beyond_local_file.model import ConfigProject, Mapping, translate_config_to_processing
from beyond_local_file.options import LinkStrategy


@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory with some files."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    (project_dir / "file1.txt").write_text("content1")
    (project_dir / "file2.txt").write_text("content2")
    (project_dir / ".kiro").mkdir()
    (project_dir / ".kiro" / "hooks").mkdir()
    (project_dir / ".kiro" / "hooks" / "hook.json").write_text("{}")
    return project_dir


class TestDisplayNameGeneration:
    """Test display name generation logic."""

    def test_single_mapping_single_target_no_suffix(self, temp_project_dir: Path) -> None:
        """Single mapping with single target should have no suffix."""
        config_projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=temp_project_dir,
                mappings=[
                    Mapping(targets=[Path("/target1")], subpaths=None, copy_paths=None),
                ],
            ),
        }

        units = translate_config_to_processing(config_projects)

        assert len(units) == 1
        assert units[0].display_name == "my-project"
        assert units[0].mapping_index == 0
        assert units[0].target_index == 0

    def test_multiple_mappings_single_target_each(self, temp_project_dir: Path) -> None:
        """Multiple mappings with single target each should use #N format."""
        config_projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=temp_project_dir,
                mappings=[
                    Mapping(targets=[Path("/target1")], subpaths=None, copy_paths=None),
                    Mapping(targets=[Path("/target2")], subpaths=None, copy_paths=None),
                    Mapping(targets=[Path("/target3")], subpaths=None, copy_paths=None),
                ],
            ),
        }

        units = translate_config_to_processing(config_projects)

        assert len(units) == 3  # noqa: PLR2004
        assert units[0].display_name == "my-project#1"
        assert units[1].display_name == "my-project#2"
        assert units[2].display_name == "my-project#3"

    def test_single_mapping_multiple_targets(self, temp_project_dir: Path) -> None:
        """Single mapping with multiple targets should use #N-M format."""
        config_projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=temp_project_dir,
                mappings=[
                    Mapping(
                        targets=[Path("/target1"), Path("/target2"), Path("/target3")],
                        subpaths=None,
                        copy_paths=None,
                    ),
                ],
            ),
        }

        units = translate_config_to_processing(config_projects)

        assert len(units) == 3  # noqa: PLR2004
        assert units[0].display_name == "my-project#1-1"
        assert units[1].display_name == "my-project#1-2"
        assert units[2].display_name == "my-project#1-3"

    def test_multiple_mappings_mixed_targets(self, temp_project_dir: Path) -> None:
        """Multiple mappings with mixed target counts."""
        config_projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=temp_project_dir,
                mappings=[
                    Mapping(targets=[Path("/target1")], subpaths=None, copy_paths=None),
                    Mapping(
                        targets=[Path("/target2"), Path("/target3")],
                        subpaths=None,
                        copy_paths=None,
                    ),
                    Mapping(targets=[Path("/target4")], subpaths=None, copy_paths=None),
                ],
            ),
        }

        units = translate_config_to_processing(config_projects)

        assert len(units) == 4  # noqa: PLR2004
        assert units[0].display_name == "my-project#1"
        assert units[1].display_name == "my-project#2-1"
        assert units[2].display_name == "my-project#2-2"
        assert units[3].display_name == "my-project#3"

    def test_padding_when_mapping_index_reaches_10(self, temp_project_dir: Path) -> None:
        """Display names should use zero-padding when mapping index >= 10."""
        mappings = [Mapping(targets=[Path(f"/target{i}")], subpaths=None, copy_paths=None) for i in range(1, 12)]

        config_projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=temp_project_dir,
                mappings=mappings,
            ),
        }

        units = translate_config_to_processing(config_projects)

        assert len(units) == 11  # noqa: PLR2004
        assert units[0].display_name == "my-project#01"
        assert units[8].display_name == "my-project#09"
        assert units[9].display_name == "my-project#10"
        assert units[10].display_name == "my-project#11"

    def test_padding_when_target_index_reaches_10(self, temp_project_dir: Path) -> None:
        """Display names should use zero-padding when target index >= 10."""
        targets = [Path(f"/target{i}") for i in range(1, 12)]

        config_projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=temp_project_dir,
                mappings=[
                    Mapping(targets=targets, subpaths=None, copy_paths=None),
                ],
            ),
        }

        units = translate_config_to_processing(config_projects)

        assert len(units) == 11  # noqa: PLR2004
        assert units[0].display_name == "my-project#1-01"
        assert units[8].display_name == "my-project#1-09"
        assert units[9].display_name == "my-project#1-10"
        assert units[10].display_name == "my-project#1-11"

    def test_padding_both_indices(self, temp_project_dir: Path) -> None:
        """Display names should pad both indices when both >= 10."""
        mappings = [
            Mapping(
                targets=[Path(f"/target{i}-{j}") for j in range(1, 12)],
                subpaths=None,
                copy_paths=None,
            )
            for i in range(1, 12)
        ]

        config_projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=temp_project_dir,
                mappings=mappings,
            ),
        }

        units = translate_config_to_processing(config_projects)

        # 11 mappings * 11 targets each = 121 units
        assert len(units) == 121  # noqa: PLR2004
        assert units[0].display_name == "my-project#01-01"
        assert units[10].display_name == "my-project#01-11"
        assert units[110].display_name == "my-project#11-01"
        assert units[120].display_name == "my-project#11-11"


class TestItemsLoading:
    """Test items loading logic (None vs list[ProjectItem])."""

    def test_no_subpaths_items_is_none(self, temp_project_dir: Path) -> None:
        """When mapping has no subpaths, items should be None (sync everything)."""
        config_projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=temp_project_dir,
                mappings=[
                    Mapping(targets=[Path("/target1")], subpaths=None, copy_paths=None),
                ],
            ),
        }

        units = translate_config_to_processing(config_projects)

        assert len(units) == 1
        assert units[0].items is None

    def test_with_subpaths_items_is_list(self, temp_project_dir: Path) -> None:
        """When mapping has subpaths, items should be a list of ProjectItem."""
        config_projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=temp_project_dir,
                mappings=[
                    Mapping(
                        targets=[Path("/target1")],
                        subpaths=["file1.txt", ".kiro/hooks"],
                        copy_paths=None,
                    ),
                ],
            ),
        }

        units = translate_config_to_processing(config_projects)

        assert len(units) == 1
        assert units[0].items is not None
        assert len(units[0].items) == 2  # noqa: PLR2004

        # Check items
        item_names = {item.name for item in units[0].items}
        assert item_names == {"file1.txt", ".kiro/hooks"}

        # Check strategies (default is SYMLINK)
        for item in units[0].items:
            assert item.strategy == LinkStrategy.SYMLINK

    def test_with_copy_paths(self, temp_project_dir: Path) -> None:
        """Items with copy_paths should have COPY strategy."""
        config_projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=temp_project_dir,
                mappings=[
                    Mapping(
                        targets=[Path("/target1")],
                        subpaths=["file1.txt", "file2.txt"],
                        copy_paths={"file1.txt"},
                    ),
                ],
            ),
        }

        units = translate_config_to_processing(config_projects)

        assert len(units) == 1
        assert units[0].items is not None
        assert len(units[0].items) == 2  # noqa: PLR2004

        # Find items by name
        items_by_name = {item.name: item for item in units[0].items}

        assert items_by_name["file1.txt"].strategy == LinkStrategy.COPY
        assert items_by_name["file2.txt"].strategy == LinkStrategy.SYMLINK

    def test_copy_strategy_on_directory_raises_error(self, temp_project_dir: Path) -> None:
        """Copy strategy on directory should raise ValueError."""
        config_projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=temp_project_dir,
                mappings=[
                    Mapping(
                        targets=[Path("/target1")],
                        subpaths=[".kiro/hooks"],
                        copy_paths={".kiro/hooks"},
                    ),
                ],
            ),
        }

        with pytest.raises(ValueError, match="Copy strategy is not supported for directories"):
            translate_config_to_processing(config_projects)

    def test_nonexistent_subpath_skipped(self, temp_project_dir: Path) -> None:
        """Nonexistent subpaths should be skipped."""
        config_projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=temp_project_dir,
                mappings=[
                    Mapping(
                        targets=[Path("/target1")],
                        subpaths=["file1.txt", "nonexistent.txt"],
                        copy_paths=None,
                    ),
                ],
            ),
        }

        units = translate_config_to_processing(config_projects)

        assert len(units) == 1
        assert units[0].items is not None
        assert len(units[0].items) == 1
        assert units[0].items[0].name == "file1.txt"


class TestMultipleProjects:
    """Test translation with multiple projects."""

    def test_multiple_projects(self, temp_project_dir: Path) -> None:
        """Multiple projects should each produce their own processing units."""
        project_dir_2 = temp_project_dir.parent / "test-project-2"
        project_dir_2.mkdir()
        (project_dir_2 / "file.txt").write_text("content")

        config_projects = {
            "project-a": ConfigProject(
                managed_project_name="project-a",
                managed_project_path=temp_project_dir,
                mappings=[
                    Mapping(targets=[Path("/target1")], subpaths=None, copy_paths=None),
                    Mapping(targets=[Path("/target2")], subpaths=None, copy_paths=None),
                ],
            ),
            "project-b": ConfigProject(
                managed_project_name="project-b",
                managed_project_path=project_dir_2,
                mappings=[
                    Mapping(targets=[Path("/target3")], subpaths=None, copy_paths=None),
                ],
            ),
        }

        units = translate_config_to_processing(config_projects)

        assert len(units) == 3  # noqa: PLR2004

        # Check project-a units
        project_a_units = [u for u in units if u.managed_project_name == "project-a"]
        assert len(project_a_units) == 2  # noqa: PLR2004
        assert project_a_units[0].display_name == "project-a#1"
        assert project_a_units[1].display_name == "project-a#2"

        # Check project-b units
        project_b_units = [u for u in units if u.managed_project_name == "project-b"]
        assert len(project_b_units) == 1
        assert project_b_units[0].display_name == "project-b"


class TestProcessingUnitAttributes:
    """Test ProcessingUnit attribute correctness."""

    def test_processing_unit_attributes(self, temp_project_dir: Path) -> None:
        """Verify all ProcessingUnit attributes are set correctly."""
        config_projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=temp_project_dir,
                mappings=[
                    Mapping(
                        targets=[Path("/target1"), Path("/target2")],
                        subpaths=["file1.txt"],
                        copy_paths=None,
                    ),
                ],
            ),
        }

        units = translate_config_to_processing(config_projects)

        assert len(units) == 2  # noqa: PLR2004

        # First unit
        assert units[0].managed_project_name == "my-project"
        assert units[0].managed_project_path == temp_project_dir
        assert units[0].target_project_path == Path("/target1")
        assert units[0].display_name == "my-project#1-1"
        assert units[0].mapping_index == 0
        assert units[0].target_index == 0
        assert units[0].items is not None
        assert len(units[0].items) == 1

        # Second unit
        assert units[1].managed_project_name == "my-project"
        assert units[1].managed_project_path == temp_project_dir
        assert units[1].target_project_path == Path("/target2")
        assert units[1].display_name == "my-project#1-2"
        assert units[1].mapping_index == 0
        assert units[1].target_index == 1
        assert units[1].items is not None
        assert len(units[1].items) == 1
