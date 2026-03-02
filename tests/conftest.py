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
