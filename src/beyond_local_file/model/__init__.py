"""Model package for configuration and processing data structures.

This package separates configuration models (reflecting YAML structure)
from processing models (reflecting execution structure).

Config models represent user intent as expressed in YAML.
Processing models represent execution units after translation.
"""

from .config import Config, ConfigProject, Mapping
from .processing import ProcessingUnit, ProjectItem
from .translator import translate_config_to_processing

__all__ = [
    "Config",
    "ConfigProject",
    "Mapping",
    "ProcessingUnit",
    "ProjectItem",
    "translate_config_to_processing",
]
