"""Tests for mapping expansion (config → mapping units).

Expansion is pure: M x N units and display names, independent of the
filesystem and of item discovery.
"""

from pathlib import Path

from beyond_local_file.model import ConfigProject, Mapping, translate_config_to_mapping_units


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


class TestDisplayNameGeneration:
    """Display-name logic is pure: no disk, no item discovery."""

    def test_single_mapping_single_target_no_suffix(self, tmp_path: Path) -> None:
        """Single mapping with single target should have no suffix."""
        projects = _make_project(
            tmp_path,
            mappings=[Mapping(targets=[Path("/target1")], subpaths=None)],
        )
        units = translate_config_to_mapping_units(projects)

        assert len(units) == 1
        assert units[0].display_name == "my-project"
        assert units[0].mapping_index == 0
        assert units[0].target_index == 0
        assert units[0].subpaths is None

    def test_multiple_mappings_single_target_each(self, tmp_path: Path) -> None:
        """Multiple mappings with single target each should use #N format."""
        projects = _make_project(
            tmp_path,
            mappings=[
                Mapping(targets=[Path("/t1")], subpaths=None),
                Mapping(targets=[Path("/t2")], subpaths=None),
                Mapping(targets=[Path("/t3")], subpaths=None),
            ],
        )
        units = translate_config_to_mapping_units(projects)

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
                )
            ],
        )
        units = translate_config_to_mapping_units(projects)

        assert len(units) == 3  # noqa: PLR2004
        assert units[0].display_name == "my-project#1-1"
        assert units[1].display_name == "my-project#1-2"
        assert units[2].display_name == "my-project#1-3"

    def test_multiple_mappings_mixed_targets(self, tmp_path: Path) -> None:
        """Multiple mappings with mixed target counts."""
        projects = _make_project(
            tmp_path,
            mappings=[
                Mapping(targets=[Path("/t1")], subpaths=None),
                Mapping(targets=[Path("/t2"), Path("/t3")], subpaths=None),
                Mapping(targets=[Path("/t4")], subpaths=None),
            ],
        )
        units = translate_config_to_mapping_units(projects)

        assert len(units) == 4  # noqa: PLR2004
        assert units[0].display_name == "my-project#1"
        assert units[1].display_name == "my-project#2-1"
        assert units[2].display_name == "my-project#2-2"
        assert units[3].display_name == "my-project#3"

    def test_padding_when_mapping_index_reaches_10(self, tmp_path: Path) -> None:
        """Zero-padding applied when mapping index >= 10."""
        mappings = [Mapping(targets=[Path(f"/t{i}")], subpaths=None) for i in range(1, 12)]
        projects = _make_project(tmp_path, mappings=mappings)
        units = translate_config_to_mapping_units(projects)

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
            mappings=[Mapping(targets=targets, subpaths=None)],
        )
        units = translate_config_to_mapping_units(projects)

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
            )
            for i in range(1, 12)
        ]
        projects = _make_project(tmp_path, mappings=mappings)
        units = translate_config_to_mapping_units(projects)

        assert len(units) == 121  # noqa: PLR2004
        assert units[0].display_name == "my-project#01-01"
        assert units[10].display_name == "my-project#01-11"
        assert units[110].display_name == "my-project#11-01"
        assert units[120].display_name == "my-project#11-11"

    def test_empty_hub_still_emits_the_unit(self, tmp_path: Path) -> None:
        """Expansion always emits one unit per mapping x target."""
        projects = _make_project(
            tmp_path,
            mappings=[Mapping(targets=[Path("/t1")], subpaths=None)],
        )
        units = translate_config_to_mapping_units(projects)

        assert len(units) == 1
        assert units[0].subpaths is None


class TestMultipleProjects:
    """Multiple projects each produce their own mapping units."""

    def test_multiple_projects(self, tmp_path: Path) -> None:
        config_projects = {
            "project-a": ConfigProject(
                managed_project_name="project-a",
                managed_project_path=tmp_path / "project-a",
                mappings=[
                    Mapping(targets=[Path("/t1")], subpaths=None),
                    Mapping(targets=[Path("/t2")], subpaths=None),
                ],
            ),
            "project-b": ConfigProject(
                managed_project_name="project-b",
                managed_project_path=tmp_path / "project-b",
                mappings=[Mapping(targets=[Path("/t3")], subpaths=None)],
            ),
        }

        units = translate_config_to_mapping_units(config_projects)

        assert len(units) == 3  # noqa: PLR2004

        a_units = [u for u in units if u.managed_project_name == "project-a"]
        assert len(a_units) == 2  # noqa: PLR2004
        assert a_units[0].display_name == "project-a#1"
        assert a_units[1].display_name == "project-a#2"

        b_units = [u for u in units if u.managed_project_name == "project-b"]
        assert len(b_units) == 1
        assert b_units[0].display_name == "project-b"


class TestMappingUnitAttributes:
    """Verify all MappingUnit fields are set correctly."""

    def test_processing_unit_attributes(self, tmp_path: Path) -> None:
        base = tmp_path / "my-project"
        projects = {
            "my-project": ConfigProject(
                managed_project_name="my-project",
                managed_project_path=base,
                mappings=[
                    Mapping(
                        targets=[Path("/t1"), Path("/t2")],
                        subpaths=["notes.md"],
                    )
                ],
            )
        }
        units = translate_config_to_mapping_units(projects)

        assert len(units) == 2  # noqa: PLR2004

        u0 = units[0]
        assert u0.managed_project_name == "my-project"
        assert u0.managed_project_path == base
        assert u0.target_project_path == Path("/t1")
        assert u0.display_name == "my-project#1-1"
        assert u0.mapping_index == 0
        assert u0.target_index == 0
        assert u0.subpaths == ["notes.md"]

        u1 = units[1]
        assert u1.target_project_path == Path("/t2")
        assert u1.display_name == "my-project#1-2"
        assert u1.mapping_index == 0
        assert u1.target_index == 1
        assert u1.subpaths == ["notes.md"]
