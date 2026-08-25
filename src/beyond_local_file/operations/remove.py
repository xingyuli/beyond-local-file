"""Standalone logic and output formatting for the destructive ``blf remove`` command."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import click

from beyond_local_file.config import ConfigUpdater
from beyond_local_file.git_manager import GitExcludeManager
from beyond_local_file.model.config import Mapping
from beyond_local_file.operations.revlink import ChecksumVerifier, RevlinkContext


class RemoveFormatter:
    """Format all user-facing output for a managed-item removal operation.

    Attributes:
        _dry_run: Whether each emitted line is marked as a non-mutating preview.
    """

    def __init__(self, dry_run: bool) -> None:
        """Initialise the formatter.

        Args:
            dry_run: Whether every message must be labelled as a preview.
        """
        self._dry_run = dry_run

    def _echo(self, message: str) -> None:
        """Print message lines, prefixing each one when this is a dry run.

        Args:
            message: Human-readable removal status text, possibly multiline.
        """
        prefix = "[dry-run] " if self._dry_run else ""
        for line in message.splitlines() or [""]:
            click.echo(f"{prefix}{line}")

    def info(self, message: str) -> None:
        """Print a non-error informational message.

        Args:
            message: Human-readable status or captured resolver output.
        """
        self._echo(message)

    def error(self, message: str) -> None:
        """Print a fatal validation or cleanup error.

        Args:
            message: Explanation of the failed safety condition or action.
        """
        self._echo(f"Error: {message}")

    def artifact_removed(self, artifact: Path, strategy: str) -> None:
        """Report deletion of one target-side projection.

        Args:
            artifact: Removed target-side item path.
            strategy: Projection strategy represented by the deleted item.
        """
        self._echo(f"Removed {strategy} artifact: {artifact.as_posix()}")

    def artifact_absent(self, artifact: Path) -> None:
        """Report that a missing expected target artifact needs no cleanup.

        Args:
            artifact: Expected projection path that is absent.
        """
        self._echo(f"Skipping absent artifact: {artifact.as_posix()}")

    def exclude_removed(self, entry: str, exclude_file: Path) -> None:
        """Report deletion of one Git-exclude entry.

        Args:
            entry: Relative item path removed from the exclude file.
            exclude_file: Repository exclude file updated by the removal.
        """
        self._echo(f"Removed Git exclude entry {entry!r} from {exclude_file.as_posix()}")

    def exclude_absent(self, entry: str, exclude_file: Path) -> None:
        """Report that an absent Git-exclude entry needs no cleanup.

        Args:
            entry: Relative item path that was not present.
            exclude_file: Repository exclude file that was inspected.
        """
        self._echo(f"Skipping absent Git exclude entry {entry!r} in {exclude_file.as_posix()}")

    def managed_copy_deleted(self, managed_copy: Path) -> None:
        """Report permanent deletion of the authoritative managed item.

        Args:
            managed_copy: Removed canonical managed item path.
        """
        self._echo(f"Deleted managed copy: {managed_copy.as_posix()}")

    def config_updated(self, entry: str, config_path: Path) -> None:
        """Report removal of selective-sync configuration entries.

        Args:
            entry: Relative item path removed from selective mappings.
            config_path: Updated configuration file.
        """
        self._echo(f"Removed {entry!r} from selective-sync configuration: {config_path.as_posix()}")

    def config_skipped(self) -> None:
        """Report that no participating selective mapping needs updating."""
        self._echo("Skipping configuration update: no participating selective mapping")

    def cleanup_retained(self) -> None:
        """Explain recovery state after a partially failed target cleanup."""
        self._echo("Target cleanup failed; the managed copy and configuration were retained. Fix errors and retry.")

    def config_repair_needed(self, managed_copy: Path, entry: str) -> None:
        """Explain the manual repair needed after a post-deletion config failure.

        Args:
            managed_copy: Managed item already deleted before the failed write.
            entry: Configuration entry that may require manual removal.
        """
        self._echo(f"Managed copy {managed_copy.as_posix()} was deleted; remove {entry!r} from configuration manually.")


@dataclass(frozen=True)
class _Artifact:
    """A validated target-side representation of one managed item."""

    target: Path
    path: Path
    copy_strategy: bool
    present: bool


@dataclass
class RemoveOperation:
    """Safely remove one managed item and every validated projection of it.

    The operation performs all ownership and target validation before mutating
    target artifacts, Git-exclude files, the managed copy, or configuration.
    If configuration persistence fails after managed-copy deletion, it returns
    a failure so the caller can perform the reported manual repair.

    Attributes:
        source: Lexically normalized target-side path supplied by the user.
        rel_path: Source path relative to the configured CWD target root.
        dry_run: Whether to validate and preview without persistent mutation.
        formatter: Owner of all operation status and error output.
        context: Resolved project, mapping, and configuration context.
    """

    source: Path
    rel_path: Path
    dry_run: bool
    formatter: RemoveFormatter
    context: RevlinkContext

    def run(self) -> int:
        """Validate and permanently remove the managed item and its projections.

        Returns:
            Zero after every required cleanup and configuration update succeeds;
            one when validation or any cleanup phase fails.
        """
        managed_copy = self.context.managed_project_path / self.rel_path
        if not self._validate_invocation(managed_copy):
            return 1

        artifacts = self._preflight_targets(managed_copy)
        if artifacts is None:
            return 1

        if self.dry_run:
            return 0 if self._preview(artifacts, managed_copy) else 1

        if not self._cleanup_targets(artifacts):
            self.formatter.cleanup_retained()
            return 1

        if not self._delete_managed_copy(managed_copy):
            return 1

        return self._update_config()

    def _validate_invocation(self, managed_copy: Path) -> bool:  # noqa: PLR0911 -- ordered ownership checks stop at the first unsafe condition
        """Prove that the supplied path is the expected invocation projection.

        Args:
            managed_copy: Canonical item path in the managed project.

        Returns:
            True when the supplied path is an owned projection; otherwise False.
        """
        if not managed_copy.exists():
            self.formatter.error(f"Managed copy does not exist: {managed_copy}")
            return False
        if self._has_symlink_ancestor():
            return False
        if self.source.is_symlink() and not self.source.exists():
            self.formatter.error(f"Invocation path is a dangling symlink: {self.source}")
            return False
        if not self.source.exists():
            self.formatter.error(f"Invocation path does not exist: {self.source}")
            return False

        entry = self.rel_path.as_posix()
        mapping = self.context.matched_mapping
        if mapping.subpaths is not None and entry not in mapping.subpaths:
            self.formatter.error(f"Invocation mapping does not manage {entry!r}")
            return False

        is_copy = mapping.copy_paths is not None and entry in mapping.copy_paths
        if is_copy:
            return self._validate_copy_artifact(self.source, managed_copy, "invocation path")
        return self._validate_symlink_artifact(self.source, managed_copy, "invocation path")

    def _has_symlink_ancestor(self) -> bool:
        """Reject a child reached by traversing a directory symlink.

        Returns:
            True and emits an error when an ancestor is a symlink; otherwise False.
        """
        for ancestor in self.rel_path.parents:
            if ancestor == Path("."):
                continue
            candidate = self.context.cwd / ancestor
            if candidate.is_symlink():
                self.formatter.error(
                    f"Invocation path traverses directory symlink {candidate}; only configured artifacts are removable."
                )
                return True
        return False

    def _preflight_targets(self, managed_copy: Path) -> list[_Artifact] | None:
        """Validate every participating target without changing persistent state.

        Args:
            managed_copy: Canonical item path in the managed project.

        Returns:
            All expected artifacts when validation succeeds, otherwise None.
        """
        artifacts: list[_Artifact] = []
        valid = True
        for mapping in self._participating_mappings():
            copy_strategy = self._uses_copy_strategy(mapping)
            if copy_strategy and not managed_copy.is_file():
                self.formatter.error(f"Copy strategy requires a file managed copy: {managed_copy}")
                valid = False
            for target in mapping.targets:
                if not target.is_dir() or not os.access(target, os.X_OK):
                    self.formatter.error(f"Participating target is inaccessible: {target}")
                    valid = False
                    continue
                artifact = target / self.rel_path
                present = artifact.exists() or artifact.is_symlink()
                if present:
                    label = f"target artifact {artifact}"
                    if copy_strategy:
                        valid = self._validate_copy_artifact(artifact, managed_copy, label) and valid
                    else:
                        valid = self._validate_symlink_artifact(artifact, managed_copy, label) and valid
                artifacts.append(_Artifact(target, artifact, copy_strategy, present))
        return artifacts if valid else None

    def _participating_mappings(self) -> list[Mapping]:
        """Return mappings that explicitly or implicitly manage this exact item.

        Returns:
            Every sync-all mapping plus selective mappings containing Rel_Path.
        """
        entry = self.rel_path.as_posix()
        return [mapping for mapping in self.context.mappings if mapping.subpaths is None or entry in mapping.subpaths]

    def _uses_copy_strategy(self, mapping: Mapping) -> bool:
        """Determine whether a mapping materializes this item as a regular file.

        Args:
            mapping: Participating mapping to inspect.

        Returns:
            True only when this exact relative item path has copy strategy.
        """
        return mapping.copy_paths is not None and self.rel_path.as_posix() in mapping.copy_paths

    def _validate_symlink_artifact(self, artifact: Path, managed_copy: Path, label: str) -> bool:
        """Verify that a target artifact is the expected non-dangling symlink.

        Args:
            artifact: Projection path to validate.
            managed_copy: Canonical managed item expected as the link target.
            label: Human-readable location description for diagnostics.

        Returns:
            True when the artifact is a symlink resolving to the managed copy.
        """
        if not artifact.is_symlink():
            self.formatter.error(f"{label} must be a managed symlink: {artifact}")
            return False
        if not artifact.exists():
            self.formatter.error(f"{label} is a dangling symlink: {artifact}")
            return False
        if artifact.resolve() != managed_copy.resolve():
            self.formatter.error(f"{label} points somewhere other than managed copy {managed_copy}: {artifact}")
            return False
        return True

    def _validate_copy_artifact(self, artifact: Path, managed_copy: Path, label: str) -> bool:
        """Verify that a target artifact is an identical regular-file copy.

        Args:
            artifact: Projection path to validate.
            managed_copy: Canonical managed item expected to match.
            label: Human-readable location description for diagnostics.

        Returns:
            True when the artifact is a byte-identical regular file.
        """
        if artifact.is_symlink() or not artifact.is_file() or not managed_copy.is_file():
            self.formatter.error(f"{label} must be a regular file matching managed copy: {artifact}")
            return False
        if ChecksumVerifier.compute(artifact) != ChecksumVerifier.compute(managed_copy):
            self.formatter.error(f"Checksum mismatch for {label}: {artifact}")
            return False
        return True

    def _preview(self, artifacts: list[_Artifact], managed_copy: Path) -> bool:
        """Print every planned cleanup after successful read-only validation.

        Args:
            artifacts: Fully validated target artifacts.
            managed_copy: Canonical managed item planned for deletion.

        Returns:
            True when all preview inspection succeeds; False after an I/O error.
        """
        for artifact in artifacts:
            if artifact.present:
                strategy = "copy" if artifact.copy_strategy else "symlink"
                self.formatter.artifact_removed(artifact.path, strategy)
            else:
                self.formatter.artifact_absent(artifact.path)
        if not self._preview_excludes(artifacts):
            return False
        self.formatter.managed_copy_deleted(managed_copy)
        if self._selective_targets():
            self.formatter.config_updated(self.rel_path.as_posix(), self.context.config_path)
        else:
            self.formatter.config_skipped()
        return True

    def _preview_excludes(self, artifacts: list[_Artifact]) -> bool:
        """Print planned Git-exclude handling without writing exclude files.

        Args:
            artifacts: Target projections whose distinct target roots are checked.

        Returns:
            True when all Git-exclude reads succeed; False otherwise.
        """
        succeeded = True
        for target in self._distinct_targets(artifacts):
            manager = GitExcludeManager(target)
            if not manager.is_git_repo():
                continue
            entry = self.rel_path.as_posix()
            try:
                entries = manager.read_entries()
            except OSError as error:
                self.formatter.error(f"Could not read Git exclude file {manager.exclude_file}: {error}")
                succeeded = False
                continue
            if entry in entries:
                self.formatter.exclude_removed(entry, manager.exclude_file)
            else:
                self.formatter.exclude_absent(entry, manager.exclude_file)
        return succeeded

    def _cleanup_targets(self, artifacts: list[_Artifact]) -> bool:
        """Remove every validated target artifact and matching Git-exclude entry.

        Args:
            artifacts: Validated target-side representations to clean up.

        Returns:
            True when every artifact and Git-exclude cleanup succeeds.
        """
        succeeded = True
        for artifact in artifacts:
            if not artifact.present:
                self.formatter.artifact_absent(artifact.path)
                continue
            try:
                artifact.path.unlink()
            except OSError as error:
                self.formatter.error(f"Could not remove artifact {artifact.path}: {error}")
                succeeded = False
                continue
            strategy = "copy" if artifact.copy_strategy else "symlink"
            self.formatter.artifact_removed(artifact.path, strategy)

        for target in self._distinct_targets(artifacts):
            if not self._cleanup_exclude(target):
                succeeded = False
        return succeeded

    def _cleanup_exclude(self, target: Path) -> bool:
        """Remove this item's exclude entry from one participating Git target.

        Args:
            target: Participating target directory to inspect as a Git root.

        Returns:
            True when the target is not Git, has no entry, or was updated safely.
        """
        manager = GitExcludeManager(target)
        if not manager.is_git_repo():
            return True
        entry = self.rel_path.as_posix()
        try:
            entries = manager.read_entries()
        except OSError as error:
            self.formatter.error(f"Could not read Git exclude file {manager.exclude_file}: {error}")
            return False
        if entry not in entries:
            self.formatter.exclude_absent(entry, manager.exclude_file)
            return True
        try:
            manager.remove_entries({entry})
        except OSError as error:
            self.formatter.error(f"Could not remove Git exclude entry {entry!r} in {manager.exclude_file}: {error}")
            return False
        self.formatter.exclude_removed(entry, manager.exclude_file)
        return True

    def _distinct_targets(self, artifacts: list[_Artifact]) -> list[Path]:
        """Return target roots once each, preserving their configuration order.

        Args:
            artifacts: Validated artifacts whose targets may repeat.

        Returns:
            Unique target paths in first-seen order.
        """
        return list(dict.fromkeys(artifact.target for artifact in artifacts))

    def _delete_managed_copy(self, managed_copy: Path) -> bool:
        """Permanently delete the canonical managed item after target cleanup.

        Args:
            managed_copy: File or directory to delete from the managed project.

        Returns:
            True on successful deletion; False after reporting an OS failure.
        """
        try:
            if managed_copy.is_dir():
                shutil.rmtree(managed_copy)
            else:
                managed_copy.unlink()
        except OSError as error:
            self.formatter.error(f"Could not delete managed copy {managed_copy}: {error}")
            return False
        self.formatter.managed_copy_deleted(managed_copy)
        return True

    def _selective_targets(self) -> set[Path]:
        """Return targets of participating mappings that need config removal.

        Returns:
            Every target declared by a participating selective mapping.
        """
        return {
            target
            for mapping in self._participating_mappings()
            if mapping.subpaths is not None
            for target in mapping.targets
        }

    def _update_config(self) -> int:
        """Persist all selective mapping removals in one configuration update.

        Returns:
            Zero on success; one if the atomic update fails after item deletion.
        """
        targets = self._selective_targets()
        if not targets:
            self.formatter.config_skipped()
            return 0
        try:
            changed = ConfigUpdater(self.context.config_path).remove_subpath_entries(
                self.context.project_name, targets, self.rel_path.as_posix()
            )
        except OSError as error:
            self.formatter.error(f"Could not update configuration {self.context.config_path}: {error}")
            self.formatter.config_repair_needed(
                managed_copy=self.context.managed_project_path / self.rel_path,
                entry=self.rel_path.as_posix(),
            )
            return 1
        if not changed:
            self.formatter.error(f"Could not remove {self.rel_path!s} from participating selective mappings")
            managed_copy = self.context.managed_project_path / self.rel_path
            self.formatter.config_repair_needed(managed_copy, self.rel_path.as_posix())
            return 1
        self.formatter.config_updated(self.rel_path.as_posix(), self.context.config_path)
        return 0
