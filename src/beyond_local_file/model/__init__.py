"""Model package for configuration and mapping-unit data structures.

Config models represent user intent as expressed in YAML.
Mapping units are the expanded managed project x one target after translation.
"""

from .config import ConfigProject, Mapping
from .processing import MappingUnit
from .translator import translate_config_to_mapping_units

__all__ = [
    "ConfigProject",
    "Mapping",
    "MappingUnit",
    "translate_config_to_mapping_units",
]
