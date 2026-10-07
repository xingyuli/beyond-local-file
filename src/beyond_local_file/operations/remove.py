"""Standalone logic and output formatting for the destructive ``blf remove`` command."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from beyond_local_file.config import ConfigUpdater
from beyond_local_file.daemon.live import item_matches
from beyond_local_file.daemon.log import log_duration
from beyond_local_file.git_manager import GitExcludeManager
from beyond_local_file.model.config import Mapping
from beyond_local_file.operations.result import RemoveArtifactKind, RemoveConfigStatus, RemoveResult
from beyond_local_file.operations.revlink import RevlinkContext


class RemoveFormatter:
    """Render adapter for remove: string builders used only by ``render``.

    When ``dry_run`` is ``True`` every line of a message is prefixed with
    ``[dry-run]``.
    """

    def __init__(self, dry_run: bool) -> None:
        """Initialise the formatter.

        Args:
            dry_run: Whether every message must be labelled as a preview.
        """
        self._dry_run = dry_run

    def _line(self, message: str) -> str:
        """Return message lines, prefixing each one when this is a dry run.

        Args:
            message: Human-readable removal status text, possibly multiline.
        """
        prefix = "[dry-run] " if self._dry_run else ""
        return "\n".join(f"{prefix}{line}" for line in message.splitlines() or [""])

    def error(self, message: str) -> str:
        """Return a fatal validation or cleanup error.

        Args:
            message: Explanation of the failed safety condition or action.
        """
        return self._line(f"Error: {message}")

    def artifact_removed(self, artifact: str, strategy: str) -> str:
        """Return deletion of one target-side projection.

        Args:
            artifact: Removed target-side item path.
            strategy: Projection strategy represented by the deleted item.
        """
        return self._line(f"Removed {strategy} artifact: {artifact}")

    def artifact_absent(self, artifact: str) -> str:
        """Return that a missing expected target artifact needs no cleanup.

        Args:
            artifact: Expected projection path that is absent.
        """
        return self._line(f"Skipping absent artifact: {artifact}")

    def exclude_removed(self, entry: str, exclude_file: str) -> str:
        """Return deletion of one Git-exclude entry.

        Args:
            entry: Relative item path removed from the exclude file.
            exclude_file: Repository exclude file updated by the removal.
        """
        return self._line(f"Removed Git exclude entry {entry!r} from {exclude_file}")

    def exclude_absent(self, entry: str, exclude_file: str) -> str:
        """Return that an absent Git-exclude entry needs no cleanup.

        Args:
            entry: Relative item path that was not present.
            exclude_file: Repository exclude file that was inspected.
        """
        return self._line(f"Skipping absent Git exclude entry {entry!r} in {exclude_file}")

    def managed_copy_deleted(self, managed_copy: str) -> str:
        """Return permanent deletion of the authoritative managed item.

        Args:
            managed_copy: Removed canonical managed item path.
        """
        return self._line(f"Deleted managed copy: {managed_copy}")

    def config_updated(self, entry: str, config_path: str) -> str:
        """Return removal of selective-sync configuration entries.

        Args:
            entry: Relative item path removed from selective mappings.
            config_path: Updated configuration file.
        """
        return self._line(f"Removed {entry!r} from selective-sync configuration: {config_path}")

    def config_skipped(self) -> str:
        """Return that no participating selective mapping needs updating."""
        return self._line("Skipping configuration update: no participating selective mapping")

    def config_repair_needed(self, managed_copy: str, entry: str) -> str:
        """Return the manual repair needed after a post-deletion config failure.

        Args:
            managed_copy: Managed item already deleted before the failed write.
            entry: Configuration entry that may require manual removal.
        """
        return self._line(f"Managed copy {managed_copy} was deleted; remove {entry!r} from configuration manually.")


@dataclass(frozen=True)
class _Artifact:
    """A validated target-side representation of one managed item."""

    target: Path
    path: Path
    copy_strategy: bool
    present: bool


@dataclass
class RemoveOperation:
    """Validates and plans ``blf remove``; yaml splice stays in this wrapper.

    Disk writes (delete hub and every projection, git exclude, last-seen) are a
    LiveSync remove job. Mapping membership is enough for a leftover
    projection-path symlink; copy artifacts still have to match the hub.
    ``run`` does not delete, fan out, or git-exclude.

    Attributes:
        source: Lexically normalized target-side path supplied by the user.
        rel_path: Source path relative to the configured CWD target root.
        dry_run: Whether to validate and preview without persistent mutation.
        context: Resolved project, mapping, and configuration context.
    """

    source: Path
    rel_path: Path
    dry_run: bool
    context: RevlinkContext

    def run(self) -> RemoveResult:
        """Validate and return planned deletes. Disk writes are a LiveSync job.

        Returns:
            The remove result the shell renders.
        """
        managed_copy = self.context.managed_project_path / self.rel_path
        with log_duration("remove: validate"):
            invocation_error = self._validate_invocation(managed_copy)
            if invocation_error is not None:
                return self._result(managed_copy, exit_code=1, errors=(invocation_error,))
            artifacts, errors = self._preflight_targets(managed_copy)
        if errors:
            return self._result(managed_copy, exit_code=1, errors=errors)

        artifact_rows = tuple(self._artifact_row(artifact) for artifact in artifacts)
        excludes, exclude_errors = self._collect_excludes(artifacts)
        if exclude_errors:
            return self._result(
                managed_copy,
                exit_code=1,
                errors=exclude_errors,
                artifacts=artifact_rows,
                excludes=excludes,
            )
        config: RemoveConfigStatus | None = None
        config_path: str | None = None
        config_entry: str | None = None
        if self.dry_run:
            if self._selective_targets():
                config = "updated"
                config_path = self.context.config_path.as_posix()
                config_entry = self.rel_path.as_posix()
            else:
                config = "skipped"
        return self._result(
            managed_copy,
            artifacts=artifact_rows,
            excludes=excludes,
            config=config,
            config_path=config_path,
            config_entry=config_entry,
        )

    def drop_mapping(self, result: RemoveResult) -> RemoveResult:
        """Splice the mapping yaml drop after the LiveSync remove job.

        Args:
            result: Remove plan returned by :meth:`run`.

        Returns:
            *result* with config status set, or repair fields after a failed write.
        """
        with log_duration("remove: config"):
            return self._update_config(result)

    def _result(  # noqa: PLR0913 -- RemoveResult fields are the IPC shape
        self,
        managed_copy: Path,
        *,
        exit_code: int = 0,
        errors: tuple[str, ...] = (),
        artifacts: tuple[tuple[str, RemoveArtifactKind | None, bool], ...] = (),
        excludes: tuple[tuple[str, str, bool], ...] = (),
        config: RemoveConfigStatus | None = None,
        config_path: str | None = None,
        config_entry: str | None = None,
    ) -> RemoveResult:
        return RemoveResult(
            exit_code=exit_code,
            dry_run=self.dry_run,
            errors=errors,
            artifacts=artifacts,
            excludes=excludes,
            managed_copy=managed_copy.as_posix(),
            config=config,
            config_path=config_path,
            config_entry=config_entry,
            persist_warning=None,
        )

    @staticmethod
    def _artifact_row(artifact: _Artifact) -> tuple[str, RemoveArtifactKind | None, bool]:
        if not artifact.present:
            return artifact.path.as_posix(), None, False
        kind: RemoveArtifactKind = "copy" if artifact.copy_strategy else "symlink"
        return artifact.path.as_posix(), kind, True

    def _validate_invocation(self, managed_copy: Path) -> str | None:
        """Prove that the supplied path is the expected invocation projection.

        Args:
            managed_copy: Canonical item path in the managed project.

        Returns:
            An error body when the path is not an owned projection, otherwise None.
        """
        if not managed_copy.exists():
            return f"Managed copy does not exist: {managed_copy}"
        ancestor_error = self._symlink_ancestor_error()
        if ancestor_error is not None:
            return ancestor_error
        if not self.source.exists() and not self.source.is_symlink():
            return f"Invocation path does not exist: {self.source}"

        entry = self.rel_path.as_posix()
        mapping = self.context.matched_mapping
        if mapping.subpaths is not None and entry not in mapping.subpaths:
            return f"Invocation mapping does not manage {entry!r}"

        if self.source.is_symlink():
            return None
        return self._copy_artifact_error(self.source, managed_copy, "invocation path")

    def _symlink_ancestor_error(self) -> str | None:
        """Reject a child reached by traversing a directory symlink.

        Returns:
            An error body when an ancestor is a symlink; otherwise None.
        """
        for ancestor in self.rel_path.parents:
            if ancestor == Path("."):
                continue
            candidate = self.context.cwd / ancestor
            if candidate.is_symlink():
                return (
                    f"Invocation path traverses directory symlink {candidate}; only configured artifacts are removable."
                )
        return None

    def _preflight_targets(self, managed_copy: Path) -> tuple[list[_Artifact], tuple[str, ...]]:
        """Validate every participating target without changing persistent state.

        Args:
            managed_copy: Canonical item path in the managed project.

        Returns:
            Validated artifacts and any error bodies.
        """
        artifacts: list[_Artifact] = []
        errors: list[str] = []
        for mapping in self._participating_mappings():
            for target in mapping.targets:
                if not target.is_dir() or not os.access(target, os.X_OK):
                    errors.append(f"Participating target is inaccessible: {target}")
                    continue
                artifact = target / self.rel_path
                present = artifact.exists() or artifact.is_symlink()
                copy_strategy = not artifact.is_symlink()
                if present and not artifact.is_symlink():
                    copy_error = self._copy_artifact_error(artifact, managed_copy, f"target artifact {artifact}")
                    if copy_error is not None:
                        errors.append(copy_error)
                artifacts.append(_Artifact(target, artifact, copy_strategy, present))
        return artifacts, tuple(errors)

    def _participating_mappings(self) -> list[Mapping]:
        """Return mappings that explicitly or implicitly manage this exact item.

        Returns:
            Every sync-all mapping plus selective mappings containing Rel_Path.
        """
        entry = self.rel_path.as_posix()
        return [mapping for mapping in self.context.mappings if mapping.subpaths is None or entry in mapping.subpaths]

    def _copy_artifact_error(self, artifact: Path, managed_copy: Path, label: str) -> str | None:
        """Verify that a target artifact is an identical file or directory copy.

        Args:
            artifact: Projection path to validate.
            managed_copy: Canonical managed item expected to match.
            label: Human-readable location description for diagnostics.

        Returns:
            An error body when the artifact is not a byte-identical copy.
        """
        same_kind = (artifact.is_file() and managed_copy.is_file()) or (artifact.is_dir() and managed_copy.is_dir())
        if artifact.is_symlink() or not same_kind:
            return f"{label} must be a regular file or directory matching managed copy: {artifact}"
        hub_root = managed_copy
        replica_root = artifact
        for _ in self.rel_path.parts:
            hub_root = hub_root.parent
            replica_root = replica_root.parent
        if not item_matches(hub_root, replica_root, self.rel_path.as_posix()):
            return f"{label} does not match managed copy: {artifact}"
        return None

    def _collect_excludes(
        self, artifacts: list[_Artifact]
    ) -> tuple[tuple[tuple[str, str, bool], ...], tuple[str, ...]]:
        """Collect planned Git-exclude handling without writing exclude files.

        Args:
            artifacts: Target projections whose distinct target roots are checked.

        Returns:
            Exclude rows and any read-error bodies.
        """
        rows: list[tuple[str, str, bool]] = []
        errors: list[str] = []
        entry = self.rel_path.as_posix()
        for target in self._distinct_targets(artifacts):
            manager = GitExcludeManager(target)
            if not manager.is_git_repo():
                continue
            try:
                entries = manager.read_entries()
            except OSError as error:
                errors.append(f"Could not read Git exclude file {manager.exclude_file}: {error}")
                continue
            rows.append((entry, manager.exclude_file.as_posix(), entry in entries))
        return tuple(rows), tuple(errors)

    def _distinct_targets(self, artifacts: list[_Artifact]) -> list[Path]:
        """Return target roots once each, preserving their configuration order.

        Args:
            artifacts: Validated artifacts whose targets may repeat.

        Returns:
            Unique target paths in first-seen order.
        """
        return list(dict.fromkeys(artifact.target for artifact in artifacts))

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

    def _update_config(self, result: RemoveResult) -> RemoveResult:
        """Persist all selective mapping removals in one configuration update.

        Args:
            result: Remove plan after the LiveSync job.

        Returns:
            *result* with config status, or repair fields after a failed write.
        """
        targets = self._selective_targets()
        if not targets:
            return replace(result, config="skipped")
        path = self.context.config_path.as_posix()
        entry = self.rel_path.as_posix()
        try:
            changed = ConfigUpdater(self.context.config_path).remove_subpath_entries(
                self.context.project_name, targets, entry
            )
        except OSError as error:
            return replace(
                result,
                exit_code=1,
                errors=(f"Could not update configuration {self.context.config_path}: {error}",),
                config="repair",
                config_path=path,
                config_entry=entry,
            )
        if not changed:
            return replace(
                result,
                exit_code=1,
                errors=(f"Could not remove {self.rel_path!s} from participating selective mappings",),
                config="repair",
                config_path=path,
                config_entry=entry,
            )
        return replace(result, config="updated", config_path=path, config_entry=entry)
