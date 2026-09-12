"""Item path overlap and contribution-source helpers."""

from pathlib import Path

from beyond_local_file.contribution import find_item_path_overlaps, item_paths_overlap
from beyond_local_file.model.config import ConfigProject, Mapping


def test_sibling_names_do_not_overlap() -> None:
    """CONTEXT.md is not a prefix of CONTEXT-MAP.md."""
    assert not item_paths_overlap("CONTEXT.md", "CONTEXT-MAP.md")
    assert not item_paths_overlap(".kiro/hooks", ".kiro/settings")


def test_directory_item_overlaps_nested_file() -> None:
    """A directory item overlaps a nested file item."""
    assert item_paths_overlap("local-file", "local-file/devops/k8s.md")
    assert item_paths_overlap("local-file/devops/k8s.md", "local-file")
    assert item_paths_overlap("local-file", "local-file")


def test_find_overlaps_names_both_projects(tmp_path: Path) -> None:
    """Discovery reports both managed projects and both item names."""
    hub_a = tmp_path / "proj-a"
    hub_b = tmp_path / "proj-b"
    target = tmp_path / "target"
    hub_a.mkdir()
    hub_b.mkdir()
    (hub_a / "local-file").mkdir()
    nested = hub_b / "local-file" / "devops"
    nested.mkdir(parents=True)
    (nested / "k8s.md").write_text("k8s")
    projects = {
        "proj-a": ConfigProject(
            managed_project_name="proj-a",
            managed_project_path=hub_a,
            mappings=[Mapping(targets=[target], subpaths=["local-file"])],
        ),
        "proj-b": ConfigProject(
            managed_project_name="proj-b",
            managed_project_path=hub_b,
            mappings=[Mapping(targets=[target], subpaths=["local-file/devops/k8s.md"])],
        ),
    }

    overlaps = find_item_path_overlaps(projects)

    assert len(overlaps) == 1
    assert overlaps[0].project_a == "proj-a"
    assert overlaps[0].item_a == "local-file"
    assert overlaps[0].project_b == "proj-b"
    assert overlaps[0].item_b == "local-file/devops/k8s.md"
