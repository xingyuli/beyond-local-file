"""Unit tests for package metadata validation.

Tests verify that pyproject.toml contains the correct metadata configuration
including package name, Python version requirements, dependencies, build backend,
and entry point configuration.
"""

import tomllib
from pathlib import Path


def test_package_name():
    """Test that package name is 'beyond-local-file'."""
    pyproject_path = Path("pyproject.toml")
    assert pyproject_path.exists(), "pyproject.toml must exist"

    with pyproject_path.open("rb") as f:
        config = tomllib.load(f)

    assert "project" in config, "pyproject.toml must have [project] section"
    assert "name" in config["project"], "pyproject.toml must define project name"
    assert config["project"]["name"] == "beyond-local-file", "Package name must be 'beyond-local-file'"


def test_python_version_requirement():
    """Test that Python version requirement is '>=3.13'."""
    pyproject_path = Path("pyproject.toml")
    assert pyproject_path.exists(), "pyproject.toml must exist"

    with pyproject_path.open("rb") as f:
        config = tomllib.load(f)

    assert "project" in config, "pyproject.toml must have [project] section"
    assert "requires-python" in config["project"], "pyproject.toml must define requires-python"
    assert config["project"]["requires-python"] == ">=3.13", "Python version requirement must be '>=3.13'"


def test_pyyaml_dependency():
    """Test that pyyaml>=6.0 is declared as a dependency."""
    pyproject_path = Path("pyproject.toml")
    assert pyproject_path.exists(), "pyproject.toml must exist"

    with pyproject_path.open("rb") as f:
        config = tomllib.load(f)

    assert "project" in config, "pyproject.toml must have [project] section"
    assert "dependencies" in config["project"], "pyproject.toml must define dependencies"

    dependencies = config["project"]["dependencies"]
    assert isinstance(dependencies, list), "dependencies must be a list"

    # Check for pyyaml>=6.0
    pyyaml_found = any(dep.startswith("pyyaml>=6.0") for dep in dependencies)
    assert pyyaml_found, "pyyaml>=6.0 must be in dependencies"


def test_click_dependency():
    """Test that click>=8.0 is declared as a dependency."""
    pyproject_path = Path("pyproject.toml")
    assert pyproject_path.exists(), "pyproject.toml must exist"

    with pyproject_path.open("rb") as f:
        config = tomllib.load(f)

    assert "project" in config, "pyproject.toml must have [project] section"
    assert "dependencies" in config["project"], "pyproject.toml must define dependencies"

    dependencies = config["project"]["dependencies"]
    assert isinstance(dependencies, list), "dependencies must be a list"

    # Check for click>=8.0
    click_found = any(dep.startswith("click>=8.0") for dep in dependencies)
    assert click_found, "click>=8.0 must be in dependencies"


def test_hatchling_build_backend():
    """Test that hatchling is configured as the build backend."""
    pyproject_path = Path("pyproject.toml")
    assert pyproject_path.exists(), "pyproject.toml must exist"

    with pyproject_path.open("rb") as f:
        config = tomllib.load(f)

    assert "build-system" in config, "pyproject.toml must have [build-system] section"
    build_system = config["build-system"]

    assert "requires" in build_system, "build-system must define requires"
    assert "hatchling" in build_system["requires"], "hatchling must be in build-system.requires"

    assert "build-backend" in build_system, "build-system must define build-backend"
    assert build_system["build-backend"] == "hatchling.build", "build-backend must be 'hatchling.build'"


def test_entry_point_configuration():
    """Test that entry point is correctly configured."""
    pyproject_path = Path("pyproject.toml")
    assert pyproject_path.exists(), "pyproject.toml must exist"

    with pyproject_path.open("rb") as f:
        config = tomllib.load(f)

    assert "project" in config, "pyproject.toml must have [project] section"
    assert "scripts" in config["project"], "pyproject.toml must have [project.scripts] section"

    scripts = config["project"]["scripts"]
    assert isinstance(scripts, dict), "[project.scripts] must be a dictionary"

    # Check for beyond-local-file entry point
    assert "beyond-local-file" in scripts, "Entry point 'beyond-local-file' must be defined"
    assert scripts["beyond-local-file"] == "beyond_local_file.cli:cli", (
        "Entry point must point to 'beyond_local_file.cli:cli'"
    )
