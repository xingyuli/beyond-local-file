"""Model package for configuration and mapping-unit data structures.

Config models represent user intent as expressed in YAML.
Mapping units are the expanded managed project x one target after translation.
"""

from .config import Config, ConfigProject, Mapping
from .processing import ManagedProjectItem, MappingUnit
from .translator import translate_config_to_mapping_units

__all__ = [
    "Config",
    "ConfigProject",
    "ManagedProjectItem",
    "Mapping",
    "MappingUnit",
    "translate_config_to_mapping_units",
]
