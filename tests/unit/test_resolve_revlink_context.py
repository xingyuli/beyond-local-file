"""Unit tests for resolve_revlink_context().

Tests the new function at its public seam: given (config, cwd), it returns
either a RevlinkContext (happy path) or a RevlinkResolveError (all failure
modes).  Config loading and CWD resolution are mocked at the
project_processor boundary so these tests are pure unit tests.
"""

from pathlib import Path
from unittest.mock import patch

from beyond_local_file.model.config import ConfigProject, Mapping
from beyond_local_file.operations.revlink import RevlinkContext
from beyond_local_file.project_processor import (
    ConfigLoadResult,
    RevlinkResolveError,
    resolve_revlink_context,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path("/fake/config.yml")
_MANAGED_PATH = Path("/fake/managed")
_CWD = Path("/fake/target")


def _make_project(*, name: str = "test-project", targets: list[Path] | None = None) -> ConfigProject:
    """Build a minimal ConfigProject for use in tests.

    Args:
        name: The managed project name.
        targets: Target paths for the single mapping. Defaults to [_CWD].

    Returns:
        A ConfigProject with a single mapping.
    """
    return ConfigProject(
        managed_project_name=name,
        managed_project_path=_MANAGED_PATH,
        mappings=[Mapping(targets=targets if targets is not None else [_CWD], subpaths=None, copy_paths=None)],
    )


# ---------------------------------------------------------------------------
# Failure mode 1: config loading fails (load_config_projects returns None)
# ---------------------------------------------------------------------------


def test_returns_error_when_config_load_fails() -> None:
    """When load_config_projects returns None, resolve_revlink_context returns a RevlinkResolveError.

    The message is None because load_config_projects already printed the
    diagnostic; the caller should check and skip echo when message is None.
    """
    with patch("beyond_local_file.project_processor.load_config_projects", return_value=None):
        result = resolve_revlink_context(config=None, cwd=_CWD)

    assert isinstance(result, RevlinkResolveError)
    assert result.message is None
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Failure mode 2: no matching project (_resolve_project_from_cwd returns None)
# ---------------------------------------------------------------------------


def test_returns_error_when_no_project_matches() -> None:
    """When _resolve_project_from_cwd returns None, the result is a RevlinkResolveError.

    The message must contain a human-readable description and a hint about
    how to fix the config.
    """
    load_result = ConfigLoadResult(projects={}, config_file=_CONFIG_PATH)

    with (
        patch("beyond_local_file.project_processor.load_config_projects", return_value=load_result),
        patch("beyond_local_file.project_processor._resolve_project_from_cwd", return_value=None),
    ):
        result = resolve_revlink_context(config=None, cwd=_CWD)

    assert isinstance(result, RevlinkResolveError)
    assert "No managed project found" in result.message
    assert str(_CWD) in result.message
    assert result.exit_code == 1


def test_no_project_message_includes_hint() -> None:
    """The no-match error message must include the config hint text."""
    load_result = ConfigLoadResult(projects={}, config_file=_CONFIG_PATH)

    with (
        patch("beyond_local_file.project_processor.load_config_projects", return_value=load_result),
        patch("beyond_local_file.project_processor._resolve_project_from_cwd", return_value=None),
    ):
        result = resolve_revlink_context(config=None, cwd=_CWD)

    assert isinstance(result, RevlinkResolveError)
    assert "Hint:" in result.message


# ---------------------------------------------------------------------------
# Failure mode 3: ambiguous projects (_resolve_project_from_cwd returns list)
# ---------------------------------------------------------------------------


def test_returns_error_when_multiple_projects_match() -> None:
    """When _resolve_project_from_cwd returns a list, the result is a RevlinkResolveError.

    The message must mention 'Ambiguous' and include all project names.
    """
    project_a = ConfigProject(
        managed_project_name="project-a",
        managed_project_path=Path("/managed-a"),
        mappings=[Mapping(targets=[_CWD], subpaths=None, copy_paths=None)],
    )
    project_b = ConfigProject(
        managed_project_name="project-b",
        managed_project_path=Path("/managed-b"),
        mappings=[Mapping(targets=[_CWD], subpaths=None, copy_paths=None)],
    )
    load_result = ConfigLoadResult(
        projects={"a": project_a, "b": project_b},
        config_file=_CONFIG_PATH,
    )

    with (
        patch("beyond_local_file.project_processor.load_config_projects", return_value=load_result),
        patch(
            "beyond_local_file.project_processor._resolve_project_from_cwd",
            return_value=[project_a, project_b],
        ),
    ):
        result = resolve_revlink_context(config=None, cwd=_CWD)

    assert isinstance(result, RevlinkResolveError)
    assert "Ambiguous" in result.message
    assert "project-a" in result.message
    assert "project-b" in result.message
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Happy path: unique match → RevlinkContext
# ---------------------------------------------------------------------------


def test_returns_revlink_context_on_unique_match() -> None:
    """When a unique project matches, resolve_revlink_context returns a RevlinkContext.

    The returned context must carry the correct config_path, project_name,
    matched_mapping, cwd, and managed_project_path.
    """
    project = _make_project()
    load_result = ConfigLoadResult(
        projects={"test-project": project},
        config_file=_CONFIG_PATH,
    )

    with (
        patch("beyond_local_file.project_processor.load_config_projects", return_value=load_result),
        patch("beyond_local_file.project_processor._resolve_project_from_cwd", return_value=project),
    ):
        result = resolve_revlink_context(config=None, cwd=_CWD)

    assert isinstance(result, RevlinkContext)
    assert result.config_path == _CONFIG_PATH
    assert result.project_name == "test-project"
    assert result.cwd == _CWD
    assert result.managed_project_path == _MANAGED_PATH
    assert result.mappings == project.mappings
    # matched_mapping must be the one whose targets include _CWD
    assert _CWD in result.matched_mapping.targets


def test_context_config_path_matches_loaded_config() -> None:
    """The RevlinkContext.config_path must equal the config_file from the load result."""
    custom_config = Path("/custom/path/config.yml")
    project = _make_project()
    load_result = ConfigLoadResult(
        projects={"test-project": project},
        config_file=custom_config,
    )

    with (
        patch("beyond_local_file.project_processor.load_config_projects", return_value=load_result),
        patch("beyond_local_file.project_processor._resolve_project_from_cwd", return_value=project),
    ):
        result = resolve_revlink_context(config="custom-config-arg", cwd=_CWD)

    assert isinstance(result, RevlinkContext)
    assert result.config_path == custom_config


def test_load_config_projects_called_with_correct_config_arg() -> None:
    """resolve_revlink_context must pass the config arg through to load_config_projects."""
    project = _make_project()
    load_result = ConfigLoadResult(
        projects={"test-project": project},
        config_file=_CONFIG_PATH,
    )

    with (
        patch("beyond_local_file.project_processor.load_config_projects", return_value=load_result) as mock_load,
        patch("beyond_local_file.project_processor._resolve_project_from_cwd", return_value=project),
    ):
        resolve_revlink_context(config="/explicit/config.yml", cwd=_CWD)

    mock_load.assert_called_once_with("/explicit/config.yml")


def test__resolve_project_from_cwd_called_with_correct_args() -> None:
    """resolve_revlink_context must pass projects dict and cwd to _resolve_project_from_cwd."""
    project = _make_project()
    projects = {"test-project": project}
    load_result = ConfigLoadResult(projects=projects, config_file=_CONFIG_PATH)

    with (
        patch("beyond_local_file.project_processor.load_config_projects", return_value=load_result),
        patch(
            "beyond_local_file.project_processor._resolve_project_from_cwd",
            return_value=project,
        ) as mock_resolve,
    ):
        resolve_revlink_context(config=None, cwd=_CWD)

    mock_resolve.assert_called_once_with(projects, _CWD)
