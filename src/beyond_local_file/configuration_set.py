"""Configuration set identity and set run directory."""

from __future__ import annotations

import hashlib
from pathlib import Path

from beyond_local_file.blfrc import runtime_home


class ConfigurationSet:
    """The mapping yaml files one daemon process loads, identified by one path."""

    identity: Path

    def __init__(self, identity: Path) -> None:
        """Store the resolved identity path.

        Args:
            identity: Global config path or a mapping yaml path.
        """
        self.identity = identity.resolve()

    @property
    def is_global(self) -> bool:
        """Return whether this is the global configuration set.

        Returns:
            True when identity is the global config under runtime home.
        """
        return self.identity == runtime_home() / "config"

    @property
    def run_directory(self) -> Path:
        """Return the set run directory for this configuration set.

        Returns:
            ``<runtime home>/run/global`` or ``.../run/file-<sha256>``.
        """
        if self.is_global:
            return runtime_home() / "run" / "global"
        digest = hashlib.sha256(str(self.identity).encode("utf-8")).hexdigest()
        return runtime_home() / "run" / f"file-{digest}"
