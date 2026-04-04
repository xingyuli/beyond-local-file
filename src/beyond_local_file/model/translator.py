"""Translation layer between configuration and processing models.

This module translates configuration models (reflecting YAML structure)
into processing units (reflecting execution structure).
"""

from dataclasses import dataclass
from pathlib import Path

from ..options import LinkStrategy
from .config import ConfigProject
from .processing import ManagedProjectItem, ProcessingUnit

# Padding threshold for display names
_PADDING_THRESHOLD = 10


@dataclass
class _DisplayNameContext:
    """Context for computing display names."""

    project_name: str
    total_units: int
    num_mappings: int
    mapping_idx: int
    target_idx: int
    num_targets_in_mapping: int
    needs_mapping_padding: bool
    needs_target_padding: bool


def translate_config_to_processing(
    config_projects: dict[str, ConfigProject],
) -> list[ProcessingUnit]:
    """Translate config model to processing units.

    For each ConfigProject:
      - Iterate through its mappings (mapping_index = 0, 1, 2, ...)
      - For each mapping, iterate through its targets (target_index = 0, 1, 2, ...)
      - Create one ProcessingUnit per (mapping, target) combination
      - Compute display_name based on total mappings and targets per mapping
      - Load items based on mapping's subpaths (None if no subpath, list if subpath specified)

    Display name logic:
      - If total processing units == 1: use project name as-is
      - If multiple mappings, single target each: "project#{mapping_index+1}"
      - If single mapping, multiple targets: "project#{mapping_index+1}-{target_index+1}"
      - If multiple mappings with multiple targets: "project#{mapping_index+1}-{target_index+1}"
      - Use zero-padding when any index >= 10 (e.g., #01, #01-01)

    Items loading:
      - If mapping has no subpaths: items = None (sync everything)
      - If mapping has subpaths: items = list[ManagedProjectItem] (sync specified items only)

    Args:
        config_projects: Dictionary of project name to ConfigProject.

    Returns:
        List of ProcessingUnit instances ready for execution.

    Example:
        ConfigProject with 2 mappings:
          - Mapping 1: 1 target  → ProcessingUnit(display_name="project#1")
          - Mapping 2: 2 targets → ProcessingUnit(display_name="project#2-1"),
                                    ProcessingUnit(display_name="project#2-2")

        Total: 3 ProcessingUnits
    """
    processing_units: list[ProcessingUnit] = []

    for config_project in config_projects.values():
        # First pass: count total units and determine if padding is needed
        total_units = sum(len(mapping.targets) for mapping in config_project.mappings)
        num_mappings = len(config_project.mappings)

        # Determine padding requirements
        needs_mapping_padding = num_mappings >= _PADDING_THRESHOLD
        needs_target_padding = any(len(mapping.targets) >= _PADDING_THRESHOLD for mapping in config_project.mappings)

        # Second pass: create processing units
        for mapping_idx, mapping in enumerate(config_project.mappings):
            for target_idx, target_path in enumerate(mapping.targets):
                # Compute display name
                ctx = _DisplayNameContext(
                    project_name=config_project.managed_project_name,
                    total_units=total_units,
                    num_mappings=num_mappings,
                    mapping_idx=mapping_idx,
                    target_idx=target_idx,
                    num_targets_in_mapping=len(mapping.targets),
                    needs_mapping_padding=needs_mapping_padding,
                    needs_target_padding=needs_target_padding,
                )
                display_name = _compute_display_name(ctx)

                # Load items based on subpaths
                items = _load_items(
                    managed_project_path=config_project.managed_project_path,
                    subpaths=mapping.subpaths,
                    copy_paths=mapping.copy_paths,
                )

                processing_units.append(
                    ProcessingUnit(
                        managed_project_name=config_project.managed_project_name,
                        managed_project_path=config_project.managed_project_path,
                        target_project_path=target_path,
                        items=items,
                        display_name=display_name,
                        mapping_index=mapping_idx,
                        target_index=target_idx,
                    )
                )

    return processing_units


def _compute_display_name(ctx: _DisplayNameContext) -> str:
    """Compute display name for a processing unit.

    Args:
        ctx: Display name context with all required parameters.

    Returns:
        Display name with appropriate suffix.
    """
    # Single unit: no suffix
    if ctx.total_units == 1:
        return ctx.project_name

    # Convert to 1-based for display
    mapping_num = ctx.mapping_idx + 1
    target_num = ctx.target_idx + 1

    # Format with padding if needed
    if ctx.needs_mapping_padding:
        mapping_str = f"{mapping_num:02d}"
    else:
        mapping_str = str(mapping_num)

    if ctx.needs_target_padding:
        target_str = f"{target_num:02d}"
    else:
        target_str = str(target_num)

    # Multiple targets in mapping: use both indices
    if ctx.num_targets_in_mapping > 1:
        return f"{ctx.project_name}#{mapping_str}-{target_str}"

    # Single target in mapping: use only mapping index
    return f"{ctx.project_name}#{mapping_str}"


def _load_items(
    managed_project_path: Path,
    subpaths: list[str] | None,
    copy_paths: set[str] | None,
) -> list[ManagedProjectItem] | None:
    """Load project items based on subpaths configuration.

    Args:
        managed_project_path: Path to the managed project directory.
        subpaths: Optional list of relative subpaths to sync.
        copy_paths: Optional set of subpath names that use copy strategy.

    Returns:
        None if no subpaths specified (sync everything),
        list[ManagedProjectItem] if subpaths specified (sync only those items).

    Raises:
        ValueError: If copy strategy is used on a directory.
    """
    # No subpaths: sync everything (items will be loaded at execution time)
    if subpaths is None:
        return None

    # Subpaths specified: create items for each valid subpath
    copy_set = copy_paths or set()
    items: list[ManagedProjectItem] = []

    for subpath in subpaths:
        source_path = managed_project_path / subpath
        if source_path.exists():
            strategy = LinkStrategy.COPY if subpath in copy_set else LinkStrategy.SYMLINK

            # Validate: copy strategy only for files
            if strategy == LinkStrategy.COPY and source_path.is_dir():
                raise ValueError(f"Copy strategy is not supported for directories: {subpath}")

            items.append(
                ManagedProjectItem(
                    name=subpath,
                    path=source_path,
                    strategy=strategy,
                )
            )

    return items
