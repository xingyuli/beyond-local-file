"""Operations package — one module per blf subcommand.

Each module owns both the operation logic and its user-facing output formatting.
"""

from .remove import RemoveOperation
from .revlink import CreateOperation, RestoreOperation, RevlinkContext
from .upgrade import run_upgrade

__all__ = [
    "CreateOperation",
    "RemoveOperation",
    "RestoreOperation",
    "RevlinkContext",
    "run_upgrade",
]
