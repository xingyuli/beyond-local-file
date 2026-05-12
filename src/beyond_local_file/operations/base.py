"""Base classes shared by all operations."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..model.processing import ProcessingUnit


class CmdOperation(ABC):
    """Base class for CLI operations executed per processing unit.

    Subclasses implement :meth:`execute_unit` to perform the actual work, and may
    override :attr:`verbose_progress` to suppress the per-target progress line
    printed by :class:`~beyond_local_file.project_processor.ProjectProcessor`
    (useful when output is deferred, e.g. a table rendered after all projects
    are processed).
    """

    @property
    def verbose_progress(self) -> bool:
        """Whether to print per-target progress lines during processing.

        Returns:
            True by default; subclasses may override to return False when
            progress output should be suppressed (e.g. deferred table rendering).
        """
        return True

    @abstractmethod
    def execute_unit(self, unit: ProcessingUnit) -> bool:
        """Execute the operation for a single processing unit.

        Args:
            unit: The processing unit to execute.

        Returns:
            True to continue processing, False to abort.
        """
