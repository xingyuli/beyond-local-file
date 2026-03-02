"""Unit tests for package structure validation.

Tests verify that the package is correctly structured and that the build
system properly includes/excludes files according to the specification.
"""

import subprocess
import tempfile
import zipfile
from pathlib import Path


def test_all_modules_exist_in_package():
    """Test that all required modules exist in src/beyond_local_file/."""
    package_dir = Path("src/beyond_local_file")
    assert package_dir.exists(), "Package directory src/beyond_local_file/ must exist"
    assert package_dir.is_dir(), "src/beyond_local_file/ must be a directory"

    # List of required modules
    required_modules = [
        "cli.py",
        "config.py",
        "models.py",
        "formatters.py",
        "git_manager.py",
        "project_processor.py",
        "symlink_manager.py",
    ]

    for module in required_modules:
        module_path = package_dir / module
        assert module_path.exists(), f"Module {module} must exist in src/beyond_local_file/"
        assert module_path.is_file(), f"{module} must be a file"


def test_init_file_exists_in_package():
    """Test that __init__.py exists in the package."""
    init_file = Path("src/beyond_local_file/__init__.py")
    assert init_file.exists(), "__init__.py must exist in src/beyond_local_file/"
    assert init_file.is_file(), "__init__.py must be a file"


def test_built_wheel_contains_only_package():
    """Test that built wheel contains only src/beyond_local_file/ package.

    This test builds the package and inspects the wheel contents to verify
    that only the beyond_local_file package is included, and no root-level
    modules or managed project directories are present.
    """
    # Build the wheel in a temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        dist_dir = Path(tmpdir) / "dist"
        dist_dir.mkdir()

        # Build the wheel using uv
        result = subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(dist_dir)],
            capture_output=True,
            text=True,
            check=False,
        )

        # Check if build succeeded
        assert result.returncode == 0, f"Build failed: {result.stderr}"

        # Find the wheel file
        wheel_files = list(dist_dir.glob("*.whl"))
        assert len(wheel_files) == 1, f"Expected 1 wheel file, found {len(wheel_files)}"
        wheel_path = wheel_files[0]

        # Extract and inspect wheel contents
        with zipfile.ZipFile(wheel_path, "r") as wheel:
            file_list = wheel.namelist()

            # Check that beyond_local_file package is present
            package_files = [f for f in file_list if f.startswith("beyond_local_file/")]
            assert len(package_files) > 0, "Wheel must contain beyond_local_file/ package"

            # Verify all required modules are in the wheel
            required_modules = [
                "beyond_local_file/__init__.py",
                "beyond_local_file/cli.py",
                "beyond_local_file/config.py",
                "beyond_local_file/models.py",
                "beyond_local_file/formatters.py",
                "beyond_local_file/git_manager.py",
                "beyond_local_file/project_processor.py",
                "beyond_local_file/symlink_manager.py",
            ]

            for module in required_modules:
                assert module in file_list, f"Module {module} must be in wheel"

            # Check that no root-level Python modules are included
            # (files at the root of the wheel that end with .py)
            root_py_files = [
                f
                for f in file_list
                if f.endswith(".py") and "/" not in f.rstrip("/") and not f.startswith("beyond_local_file/")
            ]
            assert len(root_py_files) == 0, f"Wheel should not contain root-level .py files: {root_py_files}"

            # Check that managed project directories are not included
            # (academy-broom, local-file, quvanai-server-old)
            excluded_dirs = ["academy-broom/", "local-file/", "quvanai-server-old/"]
            for excluded_dir in excluded_dirs:
                excluded_files = [f for f in file_list if f.startswith(excluded_dir)]
                assert len(excluded_files) == 0, f"Wheel should not contain managed project directory: {excluded_dir}"


def test_root_level_modules_excluded_from_package():
    """Test that root-level modules are excluded from the distributed package.

    This test verifies the package structure by checking that:
    1. Only src/beyond_local_file/ exists as a package directory
    2. The built wheel does not contain root-level Python modules

    Note: This test focuses on the wheel contents, not the repository structure.
    Root-level .py files may exist in the repository for backward compatibility,
    but they should not be included in the distributed package.
    """
    # Check that src/beyond_local_file/ is the only package directory
    src_dir = Path("src")
    assert src_dir.exists(), "src/ directory must exist"

    # List all directories in src/
    package_dirs = [d for d in src_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]

    # Should only have beyond_local_file
    assert len(package_dirs) == 1, f"src/ should contain only one package, found: {[d.name for d in package_dirs]}"
    assert package_dirs[0].name == "beyond_local_file", "Package must be named beyond_local_file"

    # The actual exclusion of root-level modules from the wheel is tested
    # in test_built_wheel_contains_only_package(), which verifies that
    # the wheel contains no root-level .py files
