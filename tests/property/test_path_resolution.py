"""Property-based tests for path resolution.

This module contains property-based tests that verify the tool's path
resolution behavior across a wide range of inputs.
"""

import os
import tempfile
from pathlib import Path

import yaml
from hypothesis import given
from hypothesis import strategies as st

from beyond_local_file.config import Config
from beyond_local_file.project_processor import get_absolute_path


# Feature: uvx-installable-tool, Property 1: Config File Path Resolution
@given(
    relative_config_path=st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters="-_./",
        ),
        min_size=1,
        max_size=50,
    ).filter(lambda x: x and not x.startswith("/") and ".." not in x),
    cwd_suffix=st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters="-_/",
        ),
        min_size=1,
        max_size=30,
    ).filter(lambda x: x and not x.startswith("/") and ".." not in x),
)
def test_config_file_path_resolved_relative_to_cwd(
    relative_config_path: str,
    cwd_suffix: str,
) -> None:
    """Verify config file paths are resolved relative to CWD.

    Property: For any relative config file path and any current working
    directory, when the tool resolves the config path, the resolved path
    should be relative to the current working directory.

    Args:
        relative_config_path: A randomly generated relative path.
        cwd_suffix: A randomly generated directory suffix for CWD.
    """
    # Save original CWD
    original_cwd = os.getcwd()

    # Create a temporary directory for this test case
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # Create a test CWD
            test_cwd = Path(tmpdir) / cwd_suffix
            test_cwd.mkdir(parents=True, exist_ok=True)

            # Change to test CWD
            os.chdir(test_cwd)

            # Resolve the config path using the tool's function
            resolved_path = get_absolute_path(relative_config_path)

            # Expected path: CWD + relative_config_path
            expected_path = (test_cwd / relative_config_path).resolve()

            # Verify the resolved path is relative to CWD
            assert Path(resolved_path) == expected_path, (
                f"Config path not resolved relative to CWD. Expected: {expected_path}, Got: {resolved_path}"
            )

        finally:
            # Restore original CWD
            os.chdir(original_cwd)


# Feature: uvx-installable-tool, Property 2: Project Path Resolution
@given(
    relative_project_path=st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters="-_",
        ),
        min_size=1,
        max_size=30,
    ).filter(lambda x: x and not x.startswith("/") and ".." not in x and "/" not in x),
    config_dir_suffix=st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters="-_/",
        ),
        min_size=1,
        max_size=30,
    ).filter(lambda x: x and not x.startswith("/") and ".." not in x),
)
def test_project_path_resolved_relative_to_config_file(
    relative_project_path: str,
    config_dir_suffix: str,
) -> None:
    """Verify project paths are resolved relative to config file directory.

    Property: For any relative project path in a config file, when the tool
    resolves the project directory, the resolved path should be relative to
    the config file's directory location.

    Args:
        relative_project_path: A randomly generated relative project name/path.
        config_dir_suffix: A randomly generated directory suffix for config location.
    """
    # Save original CWD
    original_cwd = os.getcwd()

    # Create a temporary directory for this test case
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # Create a config directory structure
            config_dir = Path(tmpdir) / config_dir_suffix
            config_dir.mkdir(parents=True, exist_ok=True)

            # Create a project directory relative to config directory
            project_dir = config_dir / relative_project_path
            project_dir.mkdir(parents=True, exist_ok=True)

            # Create a dummy file in the project directory so it's not empty
            (project_dir / "test_file.txt").write_text("test content")

            # Create a config file with relative project path
            config_file = config_dir / "config.yml"
            config_data = {relative_project_path: [str(Path(tmpdir) / "target")]}
            config_file.write_text(yaml.dump(config_data))

            # Change to a different directory (not the config directory)
            # to ensure project path is NOT resolved relative to CWD
            different_cwd = Path(tmpdir) / "different_cwd"
            different_cwd.mkdir(parents=True, exist_ok=True)
            os.chdir(different_cwd)

            # Load the config
            cfg = Config(config_file)
            config_projects = cfg.get_config_projects()

            # Get the resolved project path from the config
            project_data = config_projects[relative_project_path]
            actual_project_path = project_data.managed_project_path

            # Expected: project path should resolve relative to config file directory
            expected_project_path = (config_dir / relative_project_path).resolve()

            # Verify the project path is resolved relative to config file directory
            assert actual_project_path == expected_project_path, (
                f"Project path not resolved relative to config file directory. "
                f"Expected: {expected_project_path}, Got: {actual_project_path}"
            )

        finally:
            # Restore original CWD
            os.chdir(original_cwd)


# Feature: uvx-installable-tool, Property 4: Target Path Resolution
@given(
    relative_target_path=st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters="-_/",
        ),
        min_size=1,
        max_size=50,
    ).filter(lambda x: x and not x.startswith("/") and ".." not in x),
    cwd_suffix=st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters="-_/",
        ),
        min_size=1,
        max_size=30,
    ).filter(lambda x: x and not x.startswith("/") and ".." not in x),
)
def test_target_path_resolved_relative_to_cwd(
    relative_target_path: str,
    cwd_suffix: str,
) -> None:
    """Verify target paths are resolved relative to CWD.

    Property: For any relative target path in a config file, when the tool
    resolves the target location, the resolved path should be relative to
    the current working directory.

    Args:
        relative_target_path: A randomly generated relative target path.
        cwd_suffix: A randomly generated directory suffix for CWD.
    """
    # Save original CWD
    original_cwd = os.getcwd()

    # Create a temporary directory for this test case
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # Create a test CWD
            test_cwd = Path(tmpdir) / cwd_suffix
            test_cwd.mkdir(parents=True, exist_ok=True)

            # Change to test CWD
            os.chdir(test_cwd)

            # Create a config directory in a different location
            config_dir = Path(tmpdir) / "config_location"
            config_dir.mkdir(parents=True, exist_ok=True)

            # Create a project directory relative to config directory
            project_dir = config_dir / "test_project"
            project_dir.mkdir(parents=True, exist_ok=True)
            (project_dir / "test_file.txt").write_text("test content")

            # Create a config file with relative target path
            config_file = config_dir / "config.yml"
            config_data = {"test_project": [relative_target_path]}
            config_file.write_text(yaml.dump(config_data))

            # Load the config
            cfg = Config(config_file)
            config_projects = cfg.get_config_projects()

            # Get the resolved target paths from the config
            project_data = config_projects["test_project"]
            # Get targets from first mapping
            resolved_targets = project_data.mappings[0].targets

            # Expected path: CWD + relative_target_path
            expected_target_path = (test_cwd / relative_target_path).resolve()

            # Verify the target path is resolved relative to CWD
            assert len(resolved_targets) == 1, f"Expected 1 target path, got {len(resolved_targets)}"
            assert resolved_targets[0] == expected_target_path, (
                f"Target path not resolved relative to CWD. "
                f"Expected: {expected_target_path}, Got: {resolved_targets[0]}"
            )

        finally:
            # Restore original CWD
            os.chdir(original_cwd)


# Feature: uvx-installable-tool, Property 5: Working Directory Independence
@given(
    config_dir_suffix=st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters="-_/",
        ),
        min_size=1,
        max_size=30,
    ).filter(lambda x: x and not x.startswith("/") and ".." not in x),
    execution_dir_suffix=st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters="-_/",
        ),
        min_size=1,
        max_size=30,
    ).filter(lambda x: x and not x.startswith("/") and ".." not in x),
    project_name=st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters="-_",
        ),
        min_size=1,
        max_size=20,
    ).filter(lambda x: x and not x.startswith("/") and ".." not in x and "/" not in x),
)
def test_working_directory_independence(
    config_dir_suffix: str,
    execution_dir_suffix: str,
    project_name: str,
) -> None:
    """Verify tool works correctly from any execution directory.

    Property: For any valid config file and any current working directory,
    when the tool is executed with the config file path, the tool should
    successfully load the configuration and resolve paths correctly without
    depending on the tool's installation directory.

    Args:
        config_dir_suffix: A randomly generated directory suffix for config location.
        execution_dir_suffix: A randomly generated directory suffix for execution location.
        project_name: A randomly generated project name.
    """
    # Save original CWD
    original_cwd = os.getcwd()

    # Create a temporary directory for this test case
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # Create a config directory structure
            config_dir = Path(tmpdir) / config_dir_suffix
            config_dir.mkdir(parents=True, exist_ok=True)

            # Create a project directory relative to config directory
            project_dir = config_dir / project_name
            project_dir.mkdir(parents=True, exist_ok=True)

            # Create a dummy file in the project directory so it's not empty
            (project_dir / "test_file.txt").write_text("test content")

            # Create a target directory (absolute path)
            target_dir = Path(tmpdir) / "targets" / "target1"
            target_dir.mkdir(parents=True, exist_ok=True)

            # Create a config file with relative project path and absolute target path
            config_file = config_dir / "config.yml"
            config_data = {project_name: [str(target_dir)]}
            config_file.write_text(yaml.dump(config_data))

            # Create an execution directory (different from config directory)
            execution_dir = Path(tmpdir) / execution_dir_suffix
            execution_dir.mkdir(parents=True, exist_ok=True)

            # Change to execution directory (simulating running tool from any directory)
            os.chdir(execution_dir)

            # Load the config using absolute path to config file
            # This simulates: beyond-local-file --config /path/to/config.yml
            cfg = Config(config_file)
            config_projects = cfg.get_config_projects()

            # Verify the config was loaded successfully
            assert project_name in config_projects, f"Project '{project_name}' not found in loaded config"

            # Get the resolved project path
            project_data = config_projects[project_name]
            actual_project_path = project_data.managed_project_path
            # Get targets from first mapping
            actual_targets = project_data.mappings[0].targets

            # Expected: project path should resolve relative to config file directory
            expected_project_path = (config_dir / project_name).resolve()

            # Expected: target path should be the absolute path we specified
            expected_target_path = target_dir.resolve()

            # Verify the project path is resolved correctly
            assert actual_project_path == expected_project_path, (
                f"Project path not resolved correctly from execution directory. "
                f"Expected: {expected_project_path}, Got: {actual_project_path}"
            )

            # Verify the target path is resolved correctly
            assert len(actual_targets) == 1, f"Expected 1 target path, got {len(actual_targets)}"
            assert actual_targets[0] == expected_target_path, (
                f"Target path not resolved correctly from execution directory. "
                f"Expected: {expected_target_path}, Got: {actual_targets[0]}"
            )

            # Additional verification: ensure we're not in the config directory
            # This confirms we're truly testing working directory independence
            assert os.getcwd() != str(config_dir), (
                "Test should execute from a different directory than config directory"
            )

        finally:
            # Restore original CWD
            os.chdir(original_cwd)
