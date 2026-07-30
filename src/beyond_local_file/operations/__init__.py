"""Operations package — one module per blf subcommand.

Each module owns both the operation logic and its user-facing output formatting.
"""

from .base import CmdOperation
from .link_check import CheckOperation
from .link_sync import SyncOperation
from .remove import RemoveOperation
from .revlink import CreateOperation, RestoreOperation, RevlinkContext
from .upgrade import run_upgrade

__all__ = [
    "CheckOperation",
    "CmdOperation",
    "CreateOperation",
    "RemoveOperation",
    "RestoreOperation",
    "RevlinkContext",
    "SyncOperation",
    "run_upgrade",
]
