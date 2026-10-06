"""Configuration set identity and set run directory."""

from __future__ import annotations

import hashlib
from pathlib import Path

from beyond_local_file.blfrc import runtime_home
from beyond_local_file.configuration_set import ConfigurationSet


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
