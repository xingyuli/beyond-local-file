"""Processing models that reflect execution structure.

These models represent execution units after translating configuration.
Each ProcessingUnit represents one specific (project, mapping, target) combination.
"""

from dataclasses import dataclass
from pathlib import Path

from ..options import LinkStrategy


@dataclass
class ProjectItem:
    """A single file or directory in the managed project.

    Attributes:
        name: The name of the item (file or directory name).
        path: Absolute path to the item in the managed project.
        strategy: How this item should be linked (SYMLINK or COPY).
    """

    name: str
    path: Path
    strategy: LinkStrategy


@dataclass
class ProcessingUnit:
    """One project-to-target mapping for execution.

    A ConfigProject with M mappings and N total targets becomes M*N ProcessingUnits.
    Each ProcessingUnit represents one specific (project, mapping, target) combination.

    Attributes:
        managed_project_name: Original project name from configuration.
        managed_project_path: Absolute path to the managed project directory.
        target_project_path: Single target path for this processing unit.
        items: None = sync everything, list = sync specified items only.
               Empty list is invalid and should be caught during validation.
        display_name: Computed display name with suffix for output.
        mapping_index: Which mapping this unit comes from (0-based).
        target_index: Which target within the mapping (0-based).

    Display name format:
        - Single mapping, single target:   "project"
        - Multiple mappings, single target each: "project#1", "project#2"
        - Single mapping, multiple targets: "project#1-1", "project#1-2"
        - Multiple mappings, multiple targets: "project#1-1", "project#1-2", "project#2-1"
        - Padding: Use zero-padding when any index >= 10 (e.g., "project#01", "project#01-01")

    Examples:
        my-project:
          - /target1              → "my-project#1"
          - /target2              → "my-project#2"

        my-project:
          - target: [/t1, /t2]    → "my-project#1-1", "my-project#1-2"

        my-project:
          - /target1              → "my-project#1"
          - target: [/t2, /t3]    → "my-project#2-1", "my-project#2-2"
    """

    managed_project_name: str
    managed_project_path: Path
    target_project_path: Path
    items: list[ProjectItem] | None
    display_name: str
    mapping_index: int
    target_index: int
