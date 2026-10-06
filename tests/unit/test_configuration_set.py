"""Configuration set identity and set run directory."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from beyond_local_file.blfrc import runtime_home
from beyond_local_file.configuration_set import ConfigError, ConfigurationSet


def _write_mapping(path: Path, project: str, target: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{project}: {target}\n", encoding="utf-8")
    return path


def test_constructor_stores_resolved_identity(tmp_path: Path) -> None:
    """The stored identity is the resolved mapping-file path."""
    mapping = tmp_path / "workspace" / "config.yml"
    mapping.parent.mkdir()
    mapping.write_text("proj: /tmp/t\n")
    given = mapping.parent / ".." / "workspace" / "config.yml"
    configuration_set = ConfigurationSet(given)
    assert configuration_set.identity == mapping.resolve()


def test_singleton_identity_is_not_global_and_run_directory_uses_path_digest(tmp_path: Path) -> None:
    """A mapping yaml is a singleton set under run/file-<sha256 of the resolved path>."""
    mapping = tmp_path / "workspace" / "config.yml"
    mapping.parent.mkdir()
    mapping.write_text("proj: /tmp/t\n")
    configuration_set = ConfigurationSet(mapping)
    digest = hashlib.sha256(str(mapping.resolve()).encode("utf-8")).hexdigest()
    assert configuration_set.is_global is False
    assert configuration_set.run_directory == runtime_home() / "run" / f"file-{digest}"


def test_global_identity_uses_runtime_home_run_global() -> None:
    """The global config path is the global set under run/global."""
    configuration_set = ConfigurationSet(runtime_home() / "config")
    assert configuration_set.is_global is True
    assert configuration_set.run_directory == runtime_home() / "run" / "global"


def test_singleton_mapping_files_projects_and_sources_match_yaml(tmp_path: Path) -> None:
    """A singleton set's mapping file is its identity; projects come from that yaml."""
    mapping = tmp_path / "workspace" / "config.yml"
    target = tmp_path / "target"
    _write_mapping(mapping, "alpha-files", target)
    configuration_set = ConfigurationSet(mapping)
    projects = configuration_set.projects()
    sources = configuration_set.project_sources()
    assert configuration_set.mapping_files() == (mapping.resolve(),)
    assert list(projects) == ["alpha-files"]
    assert projects["alpha-files"].managed_project_name == "alpha-files"
    assert projects["alpha-files"].mappings[0].targets == [target.resolve()]
    assert sources == {projects["alpha-files"].managed_project_path: mapping.resolve()}


def test_global_mapping_files_combine_projects_and_sources(tmp_path: Path) -> None:
    """The global set loads every mapping file in the pointer list."""
    alpha_target = tmp_path / "target-alpha"
    viclau_target = tmp_path / "target-viclau"
    alpha_mapping = _write_mapping(tmp_path / "alpha" / "config.yml", "alpha-files", alpha_target)
    viclau_mapping = _write_mapping(tmp_path / "viclau" / "config.yml", "viclau-files", viclau_target)
    pointer = runtime_home() / "config"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(f"config_file:\n  - {alpha_mapping}\n  - {viclau_mapping}\n", encoding="utf-8")
    configuration_set = ConfigurationSet(pointer)
    projects = configuration_set.projects()
    sources = configuration_set.project_sources()
    by_name = {project.managed_project_name: project for project in projects.values()}
    assert configuration_set.mapping_files() == (alpha_mapping.resolve(), viclau_mapping.resolve())
    assert set(by_name) == {"alpha-files", "viclau-files"}
    assert by_name["alpha-files"].mappings[0].targets == [alpha_target.resolve()]
    assert by_name["viclau-files"].mappings[0].targets == [viclau_target.resolve()]
    assert sources[by_name["alpha-files"].managed_project_path] == alpha_mapping.resolve()
    assert sources[by_name["viclau-files"].managed_project_path] == viclau_mapping.resolve()


def test_duplicate_managed_project_path_across_mapping_files_raises(tmp_path: Path) -> None:
    """The same managed-project path in two mapping files is a ConfigError."""
    target_one = tmp_path / "target-one"
    target_two = tmp_path / "target-two"
    first = _write_mapping(tmp_path / "config1.yml", "shared-files", target_one)
    second = _write_mapping(tmp_path / "config2.yml", "shared-files", target_two)
    pointer = runtime_home() / "config"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(f"config_file:\n  - {first}\n  - {second}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="defined in multiple config files"):
        ConfigurationSet(pointer).projects()


def test_projects_rereads_yaml_on_each_call(tmp_path: Path) -> None:
    """projects() has no yaml cache; a later call sees disk edits."""
    mapping = tmp_path / "workspace" / "config.yml"
    first_target = tmp_path / "target-one"
    second_target = tmp_path / "target-two"
    _write_mapping(mapping, "alpha-files", first_target)
    configuration_set = ConfigurationSet(mapping)
    first = configuration_set.projects()
    assert list(first) == ["alpha-files"]
    assert first["alpha-files"].mappings[0].targets == [first_target.resolve()]
    _write_mapping(mapping, "beta-files", second_target)
    second = configuration_set.projects()
    assert list(second) == ["beta-files"]
    assert second["beta-files"].mappings[0].targets == [second_target.resolve()]
    assert list(ConfigurationSet(mapping).projects()) == ["beta-files"]


def test_missing_global_pointer_list_has_no_mapping_files() -> None:
    """A missing global pointer list yields no mapping files."""
    identity = runtime_home() / "config"
    configuration_set = ConfigurationSet(identity)
    assert configuration_set.mapping_files() == ()
    with pytest.raises(ConfigError, match=f"No mapping files for {identity}"):
        configuration_set.projects()


def test_global_pointer_list_without_config_file_has_no_mapping_files() -> None:
    """A pointer list missing the config_file field yields no mapping files."""
    identity = runtime_home() / "config"
    identity.parent.mkdir(parents=True, exist_ok=True)
    identity.write_text("unrelated: true\n", encoding="utf-8")
    configuration_set = ConfigurationSet(identity)
    assert configuration_set.mapping_files() == ()
    with pytest.raises(ConfigError, match=f"No mapping files for {identity}"):
        configuration_set.projects()


def test_invalid_global_pointer_list_raises_config_error() -> None:
    """An invalid global pointer list is a ConfigError with the pointer-list message."""
    identity = runtime_home() / "config"
    identity.parent.mkdir(parents=True, exist_ok=True)
    identity.write_text("config_file: [\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid YAML"):
        ConfigurationSet(identity).mapping_files()
