"""Configuration set identity and set run directory."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

from beyond_local_file.blfrc import get_home_directory, runtime_home
from beyond_local_file.configuration_set import (
    ConfigError,
    ConfigurationSet,
    configuration_set_for_shell,
    configuration_set_for_start,
)


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


def _write_live_global_run(mapping: Path, *, pid: int) -> None:
    run_dir = runtime_home() / "run" / "global"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "daemon.pid").write_text(f"{pid}\n", encoding="utf-8")
    (run_dir / "mapping-files").write_text(f"{mapping.resolve()}\n", encoding="utf-8")


def test_for_shell_dash_c_attaches_to_live_global_owner(tmp_path: Path) -> None:
    """-c of a yaml listed in a live global run dir returns the global identity."""
    mapping = _write_mapping(tmp_path / "workspace" / "config.yml", "alpha-files", tmp_path / "target")
    _write_live_global_run(mapping, pid=os.getpid())
    loaded = configuration_set_for_shell(str(mapping))
    assert loaded is not None
    assert loaded.identity == runtime_home() / "config"
    assert loaded.is_global is True


def test_for_start_dash_c_does_not_attach_and_reports_global_overlap(tmp_path: Path) -> None:
    """-c start keeps the singleton identity; overlap names the live global pid and yaml."""
    mapping = _write_mapping(tmp_path / "workspace" / "config.yml", "alpha-files", tmp_path / "target")
    pid = os.getpid()
    _write_live_global_run(mapping, pid=pid)
    asked = configuration_set_for_start(str(mapping))
    assert asked is not None
    assert asked.identity == mapping.resolve()
    assert asked.is_global is False
    overlap = asked.running_overlap()
    assert overlap is not None
    assert overlap.identity == runtime_home() / "config"
    assert overlap.pid == pid
    assert overlap.mapping_file == mapping.resolve()


def _write_pointer(content: str) -> Path:
    path = runtime_home() / "config"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _global_set() -> ConfigurationSet:
    return ConfigurationSet(runtime_home() / "config")


def test_global_pointer_list_ignores_leftover_dot_blfrc(tmp_path: Path) -> None:
    """A leftover ``~/.blfrc`` is not the global pointer list."""
    mapping = _write_mapping(tmp_path / "workspace" / "config.yml", "alpha-files", tmp_path / "target")
    (get_home_directory() / ".blfrc").write_text(f"config_file: {mapping}\n")
    assert _global_set().mapping_files() == ()


def test_empty_global_pointer_list_has_no_mapping_files() -> None:
    """An empty pointer list yields no mapping files."""
    _write_pointer("")
    assert _global_set().mapping_files() == ()
    with pytest.raises(ConfigError, match="No mapping files"):
        _global_set().projects()


def test_global_pointer_list_resolves_absolute_relative_and_tilde_paths(tmp_path: Path) -> None:
    """Pointer-list paths resolve as absolute, home-relative, and tilde paths."""
    home = get_home_directory()
    absolute = _write_mapping(tmp_path / "absolute.yml", "alpha-files", tmp_path / "target-alpha")
    relative = _write_mapping(home / "configs" / "relative.yml", "beta-files", tmp_path / "target-beta")
    tilde = _write_mapping(home / "tilde.yml", "gamma-files", tmp_path / "target-gamma")
    _write_pointer(f"config_file:\n  - {absolute}\n  - configs/relative.yml\n  - ~/tilde.yml\n")
    configuration_set = _global_set()
    assert configuration_set.mapping_files() == (absolute.resolve(), relative.resolve(), tilde.resolve())
    assert {project.managed_project_name for project in configuration_set.projects().values()} == {
        "alpha-files",
        "beta-files",
        "gamma-files",
    }


def test_global_pointer_list_strips_whitespace_from_paths(tmp_path: Path) -> None:
    """Whitespace around a pointer-list path is stripped."""
    mapping = _write_mapping(tmp_path / "workspace" / "config.yml", "alpha-files", tmp_path / "target")
    _write_pointer(f"config_file: '  {mapping}  '\n")
    assert _global_set().mapping_files() == (mapping.resolve(),)


@pytest.mark.skipif(sys.platform == "win32", reason="chmod-based permission denial is ineffective on Windows")
def test_unreadable_global_pointer_list_raises_config_error() -> None:
    """An unreadable pointer list is a ConfigError."""
    pointer = _write_pointer("config_file: test.yml\n")
    pointer.chmod(0o000)
    with pytest.raises(ConfigError, match=r"Cannot read.*Permission denied"):
        _global_set().mapping_files()
    pointer.chmod(0o644)


def test_empty_config_file_string_raises_config_error() -> None:
    """An empty config_file string is a ConfigError."""
    _write_pointer('config_file: ""\n')
    with pytest.raises(ConfigError, match="cannot be empty"):
        _global_set().mapping_files()


def test_whitespace_only_config_file_raises_config_error() -> None:
    """A whitespace-only config_file string is a ConfigError."""
    _write_pointer('config_file: "   "\n')
    with pytest.raises(ConfigError, match="cannot be empty"):
        _global_set().mapping_files()


def test_empty_config_file_list_raises_config_error() -> None:
    """An empty config_file list is a ConfigError."""
    _write_pointer("config_file: []\n")
    with pytest.raises(ConfigError, match="cannot be an empty list"):
        _global_set().mapping_files()


def test_config_file_wrong_type_raises_config_error() -> None:
    """A non-string, non-list config_file field is a ConfigError."""
    _write_pointer("config_file: 123\n")
    with pytest.raises(ConfigError, match="must be a string or list of strings"):
        _global_set().mapping_files()
    _write_pointer("config_file:\n  key: value\n")
    with pytest.raises(ConfigError, match="must be a string or list of strings"):
        _global_set().mapping_files()


def test_config_file_list_with_non_string_raises_config_error() -> None:
    """A config_file list item that is not a string is a ConfigError."""
    _write_pointer("config_file:\n  - test.yml\n  - 123\n")
    with pytest.raises(ConfigError, match="must be strings"):
        _global_set().mapping_files()


def test_missing_mapping_file_in_pointer_list_raises_config_error() -> None:
    """A listed mapping file that does not exist is a ConfigError."""
    _write_pointer("config_file: nonexistent.yml\n")
    with pytest.raises(ConfigError, match="Config file not found"):
        _global_set().mapping_files()


def test_pointer_list_directory_entry_raises_config_error(tmp_path: Path) -> None:
    """A listed mapping path that is a directory is a ConfigError."""
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    _write_pointer(f"config_file: {config_dir}\n")
    with pytest.raises(ConfigError, match="is a directory"):
        _global_set().mapping_files()


@pytest.mark.skipif(sys.platform == "win32", reason="chmod-based permission denial is ineffective on Windows")
def test_unreadable_mapping_file_in_pointer_list_raises_config_error(tmp_path: Path) -> None:
    """An unreadable listed mapping file is a ConfigError."""
    mapping = _write_mapping(tmp_path / "workspace" / "config.yml", "alpha-files", tmp_path / "target")
    mapping.chmod(0o000)
    _write_pointer(f"config_file: {mapping}\n")
    with pytest.raises(ConfigError, match=r"Cannot read config file.*Permission denied"):
        _global_set().mapping_files()
    mapping.chmod(0o644)


def test_pointer_list_error_names_file_number_for_multiple_files(tmp_path: Path) -> None:
    """A later missing file in a multi-file list is named by index."""
    first = _write_mapping(tmp_path / "config1.yml", "alpha-files", tmp_path / "target")
    _write_pointer(f"config_file:\n  - {first}\n  - nonexistent.yml\n")
    with pytest.raises(ConfigError, match="file 2 of 2"):
        _global_set().mapping_files()


def test_running_overlap_is_none_when_pid_is_not_live(tmp_path: Path) -> None:
    """A mapping-files listing with a dead pid is not an overlap."""
    mapping = _write_mapping(tmp_path / "workspace" / "config.yml", "alpha-files", tmp_path / "target")
    _write_live_global_run(mapping, pid=0)
    asked = ConfigurationSet(mapping)
    assert asked.running_overlap() is None
    assert configuration_set_for_shell(str(mapping)) is not None
    assert configuration_set_for_shell(str(mapping)).identity == mapping.resolve()
