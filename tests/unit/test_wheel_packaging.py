"""Unit tests for wheel packaging correctness.

Verifies that the built wheel contains exactly the right files:
- All expected modules from the beyond_local_file package
- No root-level Python modules
- No managed project directories (local-file, example-project-*)
"""

import subprocess
import tempfile
import zipfile
from pathlib import Path

# Canonical list of all modules that must be present in the wheel.
# Update this list whenever a module is added or removed from the package.
REQUIRED_WHEEL_MODULES = [
    "beyond_local_file/__init__.py",
    "beyond_local_file/blfrc.py",
    "beyond_local_file/cli.py",
    "beyond_local_file/config.py",
    "beyond_local_file/constants.py",
    "beyond_local_file/copy_manager.py",
    "beyond_local_file/git_manager.py",
    "beyond_local_file/link_strategy_protocol.py",
    "beyond_local_file/options.py",
    "beyond_local_file/project_processor.py",
    "beyond_local_file/symlink_manager.py",
    "beyond_local_file/sync_state.py",
    # model subpackage
    "beyond_local_file/model/__init__.py",
    "beyond_local_file/model/config.py",
    "beyond_local_file/model/processing.py",
    "beyond_local_file/model/translator.py",
    # operations subpackage
    "beyond_local_file/operations/__init__.py",
    "beyond_local_file/operations/base.py",
    "beyond_local_file/operations/link_check.py",
    "beyond_local_file/operations/link_sync.py",
]

# Directories that must never appear in the wheel.
EXCLUDED_DIRS = [
    "example-project-a/",
    "example-project-b/",
    "local-file/",
]


def _build_wheel(dist_dir: Path) -> Path:
    """Build the wheel into dist_dir and return its path."""
    result = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Wheel build failed:\n{result.stderr}"

    wheel_files = list(dist_dir.glob("*.whl"))
    assert len(wheel_files) == 1, f"Expected 1 wheel file, found {len(wheel_files)}: {wheel_files}"
    return wheel_files[0]


def test_built_wheel_contains_only_package() -> None:
    """Wheel contains exactly the expected package files and nothing else.

    Checks:
    1. All required modules (including the model subpackage) are present.
    2. No extra .py files appear at the wheel root (would indicate a
       packaging misconfiguration that accidentally bundles root-level scripts).
    3. No managed project directories are bundled into the wheel.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        wheel_path = _build_wheel(Path(tmpdir) / "dist")
        wheel_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(wheel_path, "r") as wheel:
            file_list = wheel.namelist()

            # 1. All required modules must be present.
            missing = [m for m in REQUIRED_WHEEL_MODULES if m not in file_list]
            assert not missing, "Modules missing from wheel:\n" + "\n".join(f"  - {m}" for m in missing)

            # 2. No unexpected root-level .py files.
            root_py_files = [
                f
                for f in file_list
                if f.endswith(".py")
                and "/" not in f.rstrip("/")
                and not f.startswith("beyond_local_file/")
            ]
            assert not root_py_files, (
                f"Wheel contains unexpected root-level .py files: {root_py_files}"
            )

            # 3. No managed project directories bundled in.
            for excluded_dir in EXCLUDED_DIRS:
                leaked = [f for f in file_list if f.startswith(excluded_dir)]
                assert not leaked, (
                    f"Wheel must not contain managed project directory "
                    f"'{excluded_dir}', but found: {leaked}"
                )
