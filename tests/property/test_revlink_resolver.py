"""Property-based tests for the revlink project resolver.

This module contains property-based tests that verify the correctness of
``resolve_project_from_cwd`` across a wide range of generated inputs.
"""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from beyond_local_file.model.config import ConfigProject, Mapping
from beyond_local_file.project_processor import resolve_project_from_cwd

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate safe path components: alphanumeric + hyphens/underscores, no slashes
_path_component = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="-_",
    ),
    min_size=1,
    max_size=20,
).filter(lambda s: s not in (".", ".."))

# Generate an absolute Path by building /component/component/...
_absolute_path = st.lists(_path_component, min_size=1, max_size=4).map(lambda parts: Path("/" + "/".join(parts)))


def _build_mapping(targets: list[Path]) -> Mapping:
    """Build a Mapping with the given targets and no subpaths or copy_paths.

    Args:
        targets: List of target paths for the mapping.

    Returns:
        A Mapping instance with the provided targets.
    """
    return Mapping(targets=targets, subpaths=None, copy_paths=None)


def _build_config_project(name: str, project_path: Path, targets: list[Path]) -> ConfigProject:
    """Build a ConfigProject with a single mapping containing the given targets.

    Args:
        name: The managed project name.
        project_path: The managed project path.
        targets: List of target paths for the single mapping.

    Returns:
        A ConfigProject instance with one mapping.
    """
    return ConfigProject(
        managed_project_name=name,
        managed_project_path=project_path,
        mappings=[_build_mapping(targets)],
    )


# Strategy: generate a list of (name, project_path, targets) tuples for building
# ConfigProject instances. Each project gets a unique name derived from its index
# to avoid key collisions in the dict.
_config_project_list = st.lists(
    st.builds(
        lambda project_path, targets: (project_path, targets),
        project_path=_absolute_path,
        targets=st.lists(_absolute_path, min_size=0, max_size=3),
    ),
    min_size=0,
    max_size=5,
)


def _build_config_projects(
    project_specs: list[tuple[Path, list[Path]]],
) -> dict[str, ConfigProject]:
    """Convert a list of (project_path, targets) specs into a config_projects dict.

    Args:
        project_specs: List of (project_path, targets) tuples.

    Returns:
        Dictionary mapping unique project keys to ConfigProject instances.
    """
    return {
        f"project-{i}": _build_config_project(
            name=f"project-{i}",
            project_path=project_path,
            targets=targets,
        )
        for i, (project_path, targets) in enumerate(project_specs)
    }


# ---------------------------------------------------------------------------
# Property 1: Project resolver returns the unique matching project
# ---------------------------------------------------------------------------


# Feature: revlink, Property 1: Project resolver returns the unique matching project
@settings(max_examples=100)
@given(
    other_projects=_config_project_list,
    matching_project_path=_absolute_path,
    cwd=_absolute_path,
    extra_targets=st.lists(_absolute_path, min_size=0, max_size=3),
)
def test_resolver_returns_unique_matching_project(
    other_projects: list[tuple[Path, list[Path]]],
    matching_project_path: Path,
    cwd: Path,
    extra_targets: list[Path],
) -> None:
    """Verify the resolver returns the single project when exactly one matches cwd.

    **Validates: Requirements 2.2, 2.3, 2.5**

    For any set of ConfigProject instances and any Path that appears as a
    target in exactly one project's mappings, ``resolve_project_from_cwd``
    must return that project and only that project.

    Args:
        other_projects: Arbitrary list of (project_path, targets) specs for
            background projects that do NOT contain cwd.
        matching_project_path: The managed_project_path for the one project
            that will contain cwd in its targets.
        cwd: The path to resolve — injected as a target into exactly one project.
        extra_targets: Additional targets for the matching project (cwd is
            always included, so the mapping has at least one target).
    """
    # Build background projects, filtering out any that accidentally contain cwd
    filtered_other = [(pp, [t for t in targets if t != cwd]) for pp, targets in other_projects]

    config_projects = _build_config_projects(filtered_other)

    # Add the one project that contains cwd — use a key that cannot collide
    # with the "project-{i}" keys above.
    matching_targets = [cwd, *[t for t in extra_targets if t != cwd]]
    matching_project = _build_config_project(
        name="matching-project",
        project_path=matching_project_path,
        targets=matching_targets,
    )
    config_projects["matching-project"] = matching_project

    result = resolve_project_from_cwd(config_projects, cwd)

    assert result is matching_project, f"Expected the unique matching ConfigProject, got {result!r}"


# ---------------------------------------------------------------------------
# Property 2: Project resolver signals no-match correctly
# ---------------------------------------------------------------------------


# Feature: revlink, Property 2: Project resolver signals no-match correctly
@settings(max_examples=100)
@given(
    project_specs=_config_project_list,
    cwd=_absolute_path,
)
def test_resolver_returns_none_when_no_project_matches(
    project_specs: list[tuple[Path, list[Path]]],
    cwd: Path,
) -> None:
    """Verify the resolver returns None when cwd does not appear in any mapping.

    **Validates: Requirements 2.4**

    For any set of ConfigProject instances and any Path that does not appear
    as a target in any project's mappings, ``resolve_project_from_cwd`` must
    return ``None``.

    Args:
        project_specs: Arbitrary list of (project_path, targets) specs.
            ``cwd`` is stripped from every target list to guarantee no match.
        cwd: The path to resolve — guaranteed absent from all mappings.
    """
    # Strip cwd from every project's targets so no project matches
    filtered_specs = [(project_path, [t for t in targets if t != cwd]) for project_path, targets in project_specs]

    config_projects = _build_config_projects(filtered_specs)

    result = resolve_project_from_cwd(config_projects, cwd)

    assert result is None, f"Expected None when cwd is absent from all mappings, got {result!r}"


# ---------------------------------------------------------------------------
# Property 3: Project resolver signals ambiguity correctly
# ---------------------------------------------------------------------------


# Feature: revlink, Property 3: Project resolver signals ambiguity correctly
@settings(max_examples=100)
@given(
    other_projects=_config_project_list,
    first_project_path=_absolute_path,
    second_project_path=_absolute_path,
    extra_matching_specs=st.lists(
        st.builds(
            lambda project_path: (project_path,),
            project_path=_absolute_path,
        ),
        min_size=0,
        max_size=3,
    ),
    cwd=_absolute_path,
)
def test_resolver_returns_list_when_multiple_projects_match(
    other_projects: list[tuple[Path, list[Path]]],
    first_project_path: Path,
    second_project_path: Path,
    extra_matching_specs: list[tuple[Path]],
    cwd: Path,
) -> None:
    """Verify the resolver returns a list of all matching projects when cwd is ambiguous.

    **Validates: Requirements 2.6**

    For any set of ConfigProject instances where two or more projects share
    the same target path, ``resolve_project_from_cwd`` must return a list
    containing all matching projects.

    Args:
        other_projects: Arbitrary list of (project_path, targets) specs for
            background projects that do NOT contain cwd.
        first_project_path: The managed_project_path for the first project
            that will contain cwd in its targets.
        second_project_path: The managed_project_path for the second project
            that will contain cwd in its targets.
        extra_matching_specs: Additional (project_path,) tuples for further
            projects that also contain cwd, exercising matches > 2.
        cwd: The path to resolve — injected as a target into at least two projects.
    """
    # Build background projects, filtering out any that accidentally contain cwd
    filtered_other = [(pp, [t for t in targets if t != cwd]) for pp, targets in other_projects]
    config_projects = _build_config_projects(filtered_other)

    # Add at least two projects that all contain cwd — keys cannot collide with
    # the "project-{i}" keys above.
    matching_project_paths = [first_project_path, second_project_path, *(pp for (pp,) in extra_matching_specs)]
    matching_projects: list[ConfigProject] = []
    for idx, project_path in enumerate(matching_project_paths):
        project = _build_config_project(
            name=f"ambiguous-project-{idx}",
            project_path=project_path,
            targets=[cwd],
        )
        config_projects[f"ambiguous-project-{idx}"] = project
        matching_projects.append(project)

    result = resolve_project_from_cwd(config_projects, cwd)

    assert isinstance(result, list), (
        f"Expected a list when multiple projects match cwd, got {type(result).__name__!r}: {result!r}"
    )
    min_expected_matches = 2
    assert len(result) >= min_expected_matches, f"Expected at least 2 matches, got {len(result)}: {result!r}"
    for project in matching_projects:
        assert project in result, f"Expected {project!r} to be in the ambiguous result list, got {result!r}"
