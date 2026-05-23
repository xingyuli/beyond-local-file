"""Shared pytest fixtures for all tests."""

import tempfile
from pathlib import Path

import pytest
from hypothesis import settings


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing.

    Yields:
        Path: Path to the temporary directory.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Create an isolated home directory with no .blfrc, bypassing the real ~/.blfrc.

    Sets the BLF_HOME environment variable to a temporary directory so that
    ``resolve_config_from_blfrc()`` finds no .blfrc file and falls through to
    the default ``config.yml`` discovery logic.

    Args:
        tmp_path: Pytest temporary directory fixture.
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        dict: Environment variables dict suitable for passing to ``CliRunner.invoke``.
    """
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("BLF_HOME", str(home_dir))
    return {"BLF_HOME": str(home_dir)}


@pytest.fixture
def sample_config_content():
    """Provide sample YAML configuration content.

    Returns:
        str: Sample YAML configuration.
    """
    return """
test-project:
  - /tmp/target1
  - /tmp/target2

another-project: /tmp/target3
"""


# Configure Hypothesis settings for property-based tests
settings.register_profile("default", max_examples=100, deadline=None)
settings.load_profile("default")


@pytest.fixture
def temp_config_dir(temp_dir: Path) -> Path:
    """Create a temporary directory for config files.

    Args:
        temp_dir: Temporary directory fixture.

    Returns:
        Path: Path to the config directory.
    """
    config_dir = temp_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


@pytest.fixture
def temp_project_dir(temp_dir: Path) -> Path:
    """Create a temporary directory for project files.

    Args:
        temp_dir: Temporary directory fixture.

    Returns:
        Path: Path to the project directory.
    """
    project_dir = temp_dir / "projects"
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir


@pytest.fixture
def temp_target_dir(temp_dir: Path) -> Path:
    """Create a temporary directory for target locations.

    Args:
        temp_dir: Temporary directory fixture.

    Returns:
        Path: Path to the target directory.
    """
    target_dir = temp_dir / "targets"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir
