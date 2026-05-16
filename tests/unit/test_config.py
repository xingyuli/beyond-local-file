"""Unit tests for Config YAML parsing.

Covers Config.get_config_projects() end-to-end: YAML on disk → ConfigProject/Mapping
objects. Each test writes a real YAML file and asserts on the parsed output.
"""

from pathlib import Path

import pytest
import yaml

from beyond_local_file.config import Config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_config(tmp_path: Path, content: dict) -> Path:
    """Write a YAML config file and return its path."""
    config_path = tmp_path / "config.yml"
    config_path.write_text(yaml.dump(content))
    return config_path


def make_project(tmp_path: Path, name: str) -> Path:
    """Create a minimal project directory and return its path."""
    project_dir = tmp_path / name
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir


# ---------------------------------------------------------------------------
# String mapping
# ---------------------------------------------------------------------------


class TestStringMapping:
    """Single string target: project-name: /target"""

    def test_single_string_target_produces_one_mapping(self, tmp_path: Path) -> None:
        """A plain string value creates exactly one Mapping with one target."""
        target = tmp_path / "target"
        make_project(tmp_path, "my-project")
        config_path = write_config(tmp_path, {"my-project": str(target)})

        projects = Config(config_path).get_config_projects()

        assert len(projects["my-project"].mappings) == 1
        assert projects["my-project"].mappings[0].targets == [target.resolve()]

    def test_string_mapping_has_no_subpaths(self, tmp_path: Path) -> None:
        """A plain string mapping leaves subpaths and copy_paths as None."""
        target = tmp_path / "target"
        make_project(tmp_path, "my-project")
        config_path = write_config(tmp_path, {"my-project": str(target)})

        projects = Config(config_path).get_config_projects()
        mapping = projects["my-project"].mappings[0]

        assert mapping.subpaths is None
        assert mapping.copy_paths is None


# ---------------------------------------------------------------------------
# Dict mapping — the gap identified in the auto-review finding
# ---------------------------------------------------------------------------


class TestDictMapping:
    """Dict mapping: project-name: {target: /path, subpath?: [...]}"""

    def test_dict_with_target_only(self, tmp_path: Path) -> None:
        """Dict mapping with only a target key produces one Mapping, no subpaths."""
        target = tmp_path / "target"
        make_project(tmp_path, "my-project")
        config_path = write_config(tmp_path, {"my-project": {"target": str(target)}})

        projects = Config(config_path).get_config_projects()
        mapping = projects["my-project"].mappings[0]

        assert len(projects["my-project"].mappings) == 1
        assert mapping.targets == [target.resolve()]
        assert mapping.subpaths is None
        assert mapping.copy_paths is None

    def test_dict_with_subpath_list(self, tmp_path: Path) -> None:
        """Dict mapping with subpath list populates subpaths correctly."""
        target = tmp_path / "target"
        make_project(tmp_path, "my-project")
        config_path = write_config(
            tmp_path,
            {
                "my-project": {
                    "target": str(target),
                    "subpath": [".kiro/hooks", "README.md"],
                }
            },
        )

        projects = Config(config_path).get_config_projects()
        mapping = projects["my-project"].mappings[0]

        assert mapping.subpaths == [".kiro/hooks", "README.md"]
        assert mapping.copy_paths is None

    def test_dict_with_single_string_subpath(self, tmp_path: Path) -> None:
        """A scalar subpath value (not a list) is wrapped into a list."""
        target = tmp_path / "target"
        make_project(tmp_path, "my-project")
        config_path = write_config(
            tmp_path,
            {
                "my-project": {
                    "target": str(target),
                    "subpath": ".kiro/hooks",
                }
            },
        )

        projects = Config(config_path).get_config_projects()
        mapping = projects["my-project"].mappings[0]

        assert mapping.subpaths == [".kiro/hooks"]
        assert mapping.copy_paths is None

    def test_dict_with_copy_flag(self, tmp_path: Path) -> None:
        """Subpath entry with copy: true is added to copy_paths."""
        target = tmp_path / "target"
        make_project(tmp_path, "my-project")
        config_path = write_config(
            tmp_path,
            {
                "my-project": {
                    "target": str(target),
                    "subpath": [
                        ".kiro/hooks",
                        {"path": "rules.md", "copy": True},
                    ],
                }
            },
        )

        projects = Config(config_path).get_config_projects()
        mapping = projects["my-project"].mappings[0]

        assert mapping.subpaths == [".kiro/hooks", "rules.md"]
        assert mapping.copy_paths == {"rules.md"}

    def test_dict_with_multiple_copy_flags(self, tmp_path: Path) -> None:
        """Multiple copy: true entries all appear in copy_paths."""
        target = tmp_path / "target"
        make_project(tmp_path, "my-project")
        config_path = write_config(
            tmp_path,
            {
                "my-project": {
                    "target": str(target),
                    "subpath": [
                        {"path": "file-a.md", "copy": True},
                        {"path": "file-b.md", "copy": True},
                        "plain.txt",
                    ],
                }
            },
        )

        projects = Config(config_path).get_config_projects()
        mapping = projects["my-project"].mappings[0]

        assert set(mapping.subpaths) == {"file-a.md", "file-b.md", "plain.txt"}
        assert mapping.copy_paths == {"file-a.md", "file-b.md"}

    def test_dict_with_multiple_targets(self, tmp_path: Path) -> None:
        """target: [t1, t2] in a dict mapping produces one Mapping with two targets."""
        t1 = tmp_path / "target1"
        t2 = tmp_path / "target2"
        make_project(tmp_path, "my-project")
        config_path = write_config(
            tmp_path,
            {
                "my-project": {
                    "target": [str(t1), str(t2)],
                    "subpath": [".kiro/hooks"],
                }
            },
        )

        projects = Config(config_path).get_config_projects()
        mapping = projects["my-project"].mappings[0]

        assert len(projects["my-project"].mappings) == 1
        assert mapping.targets == [t1.resolve(), t2.resolve()]
        assert mapping.subpaths == [".kiro/hooks"]


# ---------------------------------------------------------------------------
# List of mappings
# ---------------------------------------------------------------------------


class TestListOfMappings:
    """List format: project-name: [mapping1, mapping2, ...]"""

    def test_list_of_strings_creates_separate_mappings(self, tmp_path: Path) -> None:
        """Each string in a list becomes its own Mapping."""
        t1 = tmp_path / "target1"
        t2 = tmp_path / "target2"
        make_project(tmp_path, "my-project")
        config_path = write_config(tmp_path, {"my-project": [str(t1), str(t2)]})

        projects = Config(config_path).get_config_projects()

        assert len(projects["my-project"].mappings) == 2  # noqa: PLR2004
        assert projects["my-project"].mappings[0].targets == [t1.resolve()]
        assert projects["my-project"].mappings[1].targets == [t2.resolve()]

    def test_list_mixing_string_and_dict_mappings(self, tmp_path: Path) -> None:
        """A list can mix plain strings and dict entries."""
        t1 = tmp_path / "target1"
        t2 = tmp_path / "target2"
        make_project(tmp_path, "my-project")
        config_path = write_config(
            tmp_path,
            {
                "my-project": [
                    str(t1),
                    {"target": str(t2), "subpath": [".kiro/hooks"]},
                ]
            },
        )

        projects = Config(config_path).get_config_projects()
        mappings = projects["my-project"].mappings

        assert len(mappings) == 2  # noqa: PLR2004
        # First: plain string — no subpaths
        assert mappings[0].targets == [t1.resolve()]
        assert mappings[0].subpaths is None
        # Second: dict — has subpaths
        assert mappings[1].targets == [t2.resolve()]
        assert mappings[1].subpaths == [".kiro/hooks"]

    def test_list_dict_mapping_with_copy_flag(self, tmp_path: Path) -> None:
        """Dict entry inside a list correctly parses copy_paths."""
        target = tmp_path / "target"
        make_project(tmp_path, "my-project")
        config_path = write_config(
            tmp_path,
            {
                "my-project": [
                    {
                        "target": str(target),
                        "subpath": [{"path": "rules.md", "copy": True}],
                    }
                ]
            },
        )

        projects = Config(config_path).get_config_projects()
        mapping = projects["my-project"].mappings[0]

        assert mapping.subpaths == ["rules.md"]
        assert mapping.copy_paths == {"rules.md"}


# ---------------------------------------------------------------------------
# get_config_projects filtering
# ---------------------------------------------------------------------------


class TestGetConfigProjectsFiltering:
    """project_name filter and error handling."""

    def test_filter_by_project_name_returns_only_that_project(self, tmp_path: Path) -> None:
        """Passing project_name returns a dict with only that project."""
        t1 = tmp_path / "target1"
        t2 = tmp_path / "target2"
        make_project(tmp_path, "project-a")
        make_project(tmp_path, "project-b")
        config_path = write_config(
            tmp_path,
            {"project-a": str(t1), "project-b": str(t2)},
        )

        projects = Config(config_path).get_config_projects(project_name="project-a")

        assert list(projects.keys()) == ["project-a"]

    def test_unknown_project_name_raises_value_error(self, tmp_path: Path) -> None:
        """Requesting a non-existent project raises ValueError."""
        target = tmp_path / "target"
        make_project(tmp_path, "my-project")
        config_path = write_config(tmp_path, {"my-project": str(target)})

        with pytest.raises(ValueError, match="not found in config"):
            Config(config_path).get_config_projects(project_name="does-not-exist")

    def test_all_projects_returned_when_no_filter(self, tmp_path: Path) -> None:
        """Without a filter, all projects in the config are returned."""
        make_project(tmp_path, "project-a")
        make_project(tmp_path, "project-b")
        config_path = write_config(
            tmp_path,
            {
                "project-a": str(tmp_path / "t1"),
                "project-b": str(tmp_path / "t2"),
            },
        )

        projects = Config(config_path).get_config_projects()

        assert set(projects.keys()) == {"project-a", "project-b"}


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Config loading errors."""

    def test_missing_config_file_raises_file_not_found(self, tmp_path: Path) -> None:
        """Calling get_config_projects() when the file doesn't exist raises FileNotFoundError."""
        config_path = tmp_path / "nonexistent.yml"

        with pytest.raises(FileNotFoundError, match="Config file not found"):
            Config(config_path).get_config_projects()


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


class TestPathResolution:
    """Project paths resolve relative to the config file's directory."""

    def test_relative_project_name_resolves_from_config_dir(self, tmp_path: Path) -> None:
        """A relative project name is resolved relative to the config file."""
        config_dir = tmp_path / "configs"
        config_dir.mkdir()
        project_dir = config_dir / "projects" / "my-project"
        project_dir.mkdir(parents=True)

        config_path = config_dir / "config.yml"
        config_path.write_text(yaml.dump({"projects/my-project": str(tmp_path / "target")}))

        projects = Config(config_path).get_config_projects()

        expected = (config_dir / "projects" / "my-project").resolve()
        assert projects["projects/my-project"].managed_project_path == expected

    def test_target_path_is_resolved(self, tmp_path: Path) -> None:
        """Target paths in the Mapping are resolved to absolute Paths."""
        target = tmp_path / "some" / "target"
        make_project(tmp_path, "my-project")
        config_path = write_config(tmp_path, {"my-project": str(target)})

        projects = Config(config_path).get_config_projects()
        mapping = projects["my-project"].mappings[0]

        assert mapping.targets[0].is_absolute()
        assert mapping.targets[0] == target.resolve()
