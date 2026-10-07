"""Translate configuration models into mapping units.

The public entry point is :func:`translate_config_to_mapping_units`. Expansion
is pure: M x N mapping units and display names, independent of the filesystem
and of item discovery.
"""

from dataclasses import dataclass

from .config import ConfigProject
from .processing import MappingUnit

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


def translate_config_to_mapping_units(
    config_projects: dict[str, ConfigProject],
) -> list[MappingUnit]:
    """Translate config model to mapping units.

    For each ConfigProject:
      - Iterate through its mappings (mapping_index = 0, 1, 2, ...)
      - For each mapping, iterate through its targets (target_index = 0, 1, 2, ...)
      - Create one MappingUnit per (mapping, target) combination
      - Compute display_name based on total mappings and targets per mapping

    Display name logic:
      - If total mapping units == 1: use project name as-is
      - If multiple mappings, single target each: "project#{mapping_index+1}"
      - If single mapping, multiple targets: "project#{mapping_index+1}-{target_index+1}"
      - If multiple mappings with multiple targets: "project#{mapping_index+1}-{target_index+1}"
      - Use zero-padding when any index >= 10 (e.g., #01, #01-01)

    Item names come from item discovery, not expansion.

    Args:
        config_projects: Dictionary of project name to ConfigProject.

    Returns:
        List of MappingUnit instances, one per mapping x target.

    Example:
        ConfigProject with 2 mappings:
          - Mapping 1: 1 target  → MappingUnit(display_name="project#1")
          - Mapping 2: 2 targets → MappingUnit(display_name="project#2-1"),
                                    MappingUnit(display_name="project#2-2")

        Total: 3 MappingUnits
    """
    mapping_units: list[MappingUnit] = []

    for config_project in config_projects.values():
        # First pass: count total units and determine if padding is needed
        total_units = sum(len(mapping.targets) for mapping in config_project.mappings)
        num_mappings = len(config_project.mappings)

        # Determine padding requirements
        needs_mapping_padding = num_mappings >= _PADDING_THRESHOLD
        needs_target_padding = any(len(mapping.targets) >= _PADDING_THRESHOLD for mapping in config_project.mappings)

        # Second pass: create mapping units
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

                mapping_units.append(
                    MappingUnit(
                        managed_project_name=config_project.managed_project_name,
                        managed_project_path=config_project.managed_project_path,
                        target_project_path=target_path,
                        subpaths=mapping.subpaths,
                        display_name=display_name,
                        mapping_index=mapping_idx,
                        target_index=target_idx,
                    )
                )

    return mapping_units


def _compute_display_name(ctx: _DisplayNameContext) -> str:
    """Compute display name for a mapping unit.

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
