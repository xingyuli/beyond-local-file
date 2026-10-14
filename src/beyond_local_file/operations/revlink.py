"""revlink subcommand — operation logic and output formatting."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from beyond_local_file.config import ConfigUpdater
from beyond_local_file.daemon.log import log_duration
from beyond_local_file.model.config import Mapping
from beyond_local_file.operations.result import CreateResult, RestoreGitExcludeStatus, RestoreResult

# ---------------------------------------------------------------------------
# RevlinkContext
# ---------------------------------------------------------------------------


@dataclass
class RevlinkContext:
    """Config-resolution context needed for the config update and removal steps.

    Groups the context information that ``CreateOperation`` and
    ``RestoreOperation`` need to register or de-register an adopted item in
    the config file when the matched mapping uses selective sync (``subpath``
    list).  Pass ``None`` to skip the config update step entirely — useful in
    tests that do not exercise that path.

    Attributes:
        config_path: Absolute path to the resolved config file.
        project_name: The project key as it appears in the config file.
        matched_mapping: The ``Mapping`` whose targets include the CWD; used
            to determine whether a config update is needed.
        cwd: The current working directory; used to locate the correct mapping
            node when the project has multiple mappings.
        managed_project_path: Absolute path to the managed project directory.
            Populated by :func:`~beyond_local_file.project_processor.resolve_revlink_context`
            so that CLI handlers can retrieve the destination root without an
            additional config load.  ``None`` when constructed manually in
            tests that do not exercise the destination-root path.
        mappings: Every mapping in the resolved project.  Standalone commands
            that must inspect project-wide scope, such as ``remove``, use this
            collection rather than only ``matched_mapping``.
    """

    config_path: Path
    project_name: str
    matched_mapping: Mapping
    cwd: Path
    managed_project_path: Path | None = field(default=None)
    mappings: list[Mapping] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CreateOperation
# ---------------------------------------------------------------------------


@dataclass
class CreateOperation:
    """Validates and plans revlink create; yaml splice stays in this wrapper.

    Disk writes (hub copy, fan-out, git exclude, gen 0) are a LiveSync
    item-add job. ``run`` does not copy, fan out, or git-exclude.

    Attributes:
        source: Absolute path to the file or directory in the target directory
            that will be adopted as a copy projection.
        dest_root: ``managed_project_path`` from the resolved
            ``ConfigProject``; the destination root for the copy.
        rel_path: Path of the source relative to CWD (e.g.
            ``.kiro/specs/foo``).  Used as the destination suffix so the
            managed layout mirrors the target layout exactly.
        dry_run: When ``True``, perform all validation and report what would
            happen without modifying the filesystem.
        force: When ``True``, overwrite an existing destination in the managed
            project.
        context: Config-resolution context used for the post-copy config
            update step.  ``None`` skips the update (useful in tests).
    """

    source: Path
    dest_root: Path
    rel_path: Path
    dry_run: bool
    force: bool
    context: RevlinkContext | None = field(default=None)

    def run(self) -> CreateResult:
        """Validate, plan, and splice yaml. Disk writes are a LiveSync job.

        Derives ``dest`` as ``dest_root / rel_path``. Dry-run is data on the
        result. A real run splices mapping yaml; LiveSync item-add then writes
        disks.

        Returns:
            The create result the shell renders.
        """
        dest = self.dest_root / self.rel_path

        with log_duration("create: validate"):
            blocked = self._validate(dest)
        if blocked is not None:
            return blocked

        config_entry: str | None = None
        if self.dry_run:
            if self.context is not None and self.context.matched_mapping.subpaths is not None:
                config_entry = self.rel_path.as_posix()
        else:
            with log_duration("create: config"):
                config_entry = self._update_config()
        return self._result(
            dest,
            force_overwrite=dest.as_posix() if self.force and dest.exists() else None,
            config_entry=config_entry,
        )

    def _result(  # noqa: PLR0913 -- CreateResult fields are the IPC shape
        self,
        dest: Path,
        *,
        exit_code: int = 0,
        errors: tuple[str, ...] = (),
        already_managed: str | None = None,
        force_overwrite: str | None = None,
        config_entry: str | None = None,
    ) -> CreateResult:
        return CreateResult(
            exit_code=exit_code,
            dry_run=self.dry_run,
            errors=errors,
            already_managed=already_managed,
            force_overwrite=force_overwrite,
            source=self.source.as_posix(),
            dest=dest.as_posix(),
            git_excludes=(),
            fan_out=(),
            holds=(),
            config_entry=config_entry,
            persist_warning=None,
        )

    def _validate(self, dest: Path) -> CreateResult | None:  # noqa: PLR0911, PLR0912 -- each validation rule needs its own early return; six ordered rules require multiple branches
        """Run pre-flight validation checks before any filesystem mutation.

        Checks are performed in order:

        1. ``source`` must exist.
        2. ``source`` must not already be a symlink.
        3. No ancestor directory of ``rel_path`` may be a symlink (skipped when
           ``self.context is None``).  If an ancestor symlink resolves into the
           managed project the path is already managed — return that info at
           exit 0.  If it resolves elsewhere return an error.
        4. When the matched mapping uses sync-all (``subpaths is None``),
           ``rel_path`` must have exactly one component — nested paths are
           rejected with an error (skipped when ``self.context is None``).
        5. When the matched mapping uses selective sync (``subpaths is not None``),
           check each declared subpath for conflicts (skipped when
           ``self.context is None``):

           - 5a: if a declared subpath is an ancestor of (or equal to)
             ``rel_path``, the path is already covered — return an error
             directing the user to let the daemon project the copy (or copy
             manually first).
           - 5b: if ``rel_path`` is an ancestor of a declared subpath (reverse
             conflict), adopting the broader path would shadow the narrower
             declared entry — return an error.

        6. ``dest`` must not exist, unless ``--force`` is set.

        Args:
            dest: Derived destination path (``dest_root / rel_path``).

        Returns:
            A result when validation stops the plan, or ``None`` when all
            checks pass.
        """
        if not self.source.exists():
            return self._result(dest, exit_code=1, errors=(f"Path does not exist: {self.source}",))

        if self.source.is_symlink():
            return self._result(dest, exit_code=1, errors=(f"Path is already a symlink: {self.source.as_posix()}",))

        if self.context is not None:
            for anc in self.rel_path.parents:
                if anc == Path("."):
                    continue
                candidate = self.context.cwd / anc
                if candidate.is_symlink():
                    resolved = candidate.resolve()
                    if resolved.is_relative_to(self.dest_root):
                        return self._result(
                            dest,
                            already_managed=(
                                f"'{anc.as_posix()}' is a managed symlink — '{self.rel_path.as_posix()}' is already"
                                " managed through it. Nothing to do."
                            ),
                        )
                    return self._result(
                        dest,
                        exit_code=1,
                        errors=(
                            f"'{anc.as_posix()}' is a symlink not managed by blf."
                            " Cannot adopt a path through an unmanaged symlink.",
                        ),
                    )

        if self.context is not None and self.context.matched_mapping.subpaths is None and len(self.rel_path.parts) > 1:
            return self._result(
                dest,
                exit_code=1,
                errors=(
                    f"'{self.rel_path.as_posix()}' is a nested path. This mapping uses sync-all"
                    " — only top-level paths can be adopted directly."
                    " Add a 'subpath' entry to your config mapping first.",
                ),
            )

        if self.context is not None and self.context.matched_mapping.subpaths is not None:
            managed_copy = self.dest_root / self.rel_path
            for declared in self.context.matched_mapping.subpaths:
                declared_path = Path(declared)
                if self.rel_path == declared_path or self.rel_path.is_relative_to(declared_path):
                    if managed_copy.exists():
                        return self._result(
                            dest,
                            exit_code=1,
                            errors=(
                                f"'{declared}' is already a declared subpath that covers this path,"
                                f" and the managed copy already exists at '{managed_copy.as_posix()}'."
                                " The daemon projects this copy.",
                            ),
                        )
                    return self._result(
                        dest,
                        exit_code=1,
                        errors=(
                            f"'{declared}' is already a declared subpath that covers this path."
                            f" Copy '{self.source.as_posix()}' to '{managed_copy.as_posix()}' manually;"
                            " the daemon will project the copy.",
                        ),
                    )
                if declared_path.is_relative_to(self.rel_path) and declared_path != self.rel_path:
                    return self._result(
                        dest,
                        exit_code=1,
                        errors=(
                            f"'{declared}' is a declared subpath under this path."
                            f" Adopting '{self.rel_path.as_posix()}' would conflict with it."
                            f" Remove '{declared}' from the config subpath list first,"
                            " or adopt a more specific path.",
                        ),
                    )

        if dest.exists() and not self.force:
            return self._result(
                dest,
                exit_code=1,
                errors=(f"Destination already exists: {dest.as_posix()}\nUse --force to overwrite.",),
            )

        return None

    def _update_config(self) -> str | None:
        """Add the item to every selective mapping of this managed project.

        Sync-all mappings have no subpath list and are left unchanged.
        Failures are non-fatal so a config write error does not undo the copy.

        Returns:
            The subpath entry name when yaml changed, otherwise ``None``.
        """
        if self.context is None:
            return None
        mappings = self.context.mappings or [self.context.matched_mapping]
        selective = [mapping for mapping in mappings if mapping.subpaths is not None]
        if not selective:
            return None
        updater = ConfigUpdater(self.context.config_path)
        entry_name = self.rel_path.as_posix()
        changed = False
        for mapping in selective:
            targets = getattr(mapping, "targets", None) or [self.context.cwd]
            for target in targets:
                if updater.add_subpath_entry(self.context.project_name, target, entry_name):
                    changed = True
        if changed:
            return entry_name
        return None


# ---------------------------------------------------------------------------
# RestoreOperation
# ---------------------------------------------------------------------------


@dataclass
class RestoreOperation:
    """Validates and plans revlink restore; yaml splice stays in this wrapper.

    Disk writes (delete hub and other replicas, git exclude, last-seen) are a
    LiveSync restore job. ``run`` materializes a leftover symlink at PATH so
    the user keeps a real file, then returns the planned deletes. It does not
    delete, fan out, or git-exclude.

    Attributes:
        source: Absolute path to the projection in the CWD that will be left
            in place as an unmanaged file or directory.
        dest_root: ``managed_project_path`` from the resolved
            ``ConfigProject``; the root under which the managed copy lives.
        rel_path: Path of the source relative to CWD (e.g.
            ``.kiro/specs/foo``).  Used to derive the managed copy location as
            ``dest_root / rel_path``, preserving the full directory structure.
        dry_run: When ``True``, perform all validation and report what would
            happen without modifying the filesystem.
        context: Config-resolution context used for the post-restore config
            removal step.  ``None`` skips the update (useful in tests).
    """

    source: Path
    dest_root: Path
    rel_path: Path
    dry_run: bool
    context: RevlinkContext | None = field(default=None)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> RestoreResult:
        """Validate and return a restore result. Disk writes are a LiveSync job.

        Derives ``managed`` as ``dest_root / rel_path``. Dry-run is data on the
        result. LiveSync restore materializes a leftover symlink and writes
        disks. Yaml drop is :meth:`drop_mapping` after that job.

        Returns:
            The restore result the shell renders.
        """
        managed = self.dest_root / self.rel_path

        with log_duration("restore: validate"):
            blocked = self._validate(managed)
        if blocked is not None:
            return blocked

        if self.dry_run:
            return self._result(managed, config_removed=self._dry_run_config_removed())
        return self._result(managed)

    def drop_mapping(self, result: RestoreResult) -> RestoreResult:
        """Splice the mapping yaml drop after the LiveSync restore job.

        Args:
            result: Restore plan returned by :meth:`run`.

        Returns:
            *result* with ``config_removed`` set when yaml changed.
        """
        with log_duration("restore: config"):
            entry = self._remove_config()
        if entry is None:
            return result
        return replace(result, config_removed=entry)

    def _dry_run_config_removed(self) -> str | None:
        if not self._selective_targets():
            return None
        return self.rel_path.as_posix()

    # ------------------------------------------------------------------
    # Internal steps
    # ------------------------------------------------------------------

    def _result(  # noqa: PLR0913 -- RestoreResult fields are the IPC shape
        self,
        managed: Path,
        *,
        exit_code: int = 0,
        errors: tuple[str, ...] = (),
        leftover_symlink: bool = False,
        replica_deletes: tuple[str, ...] = (),
        git_excludes: tuple[tuple[str, RestoreGitExcludeStatus], ...] = (),
        config_removed: str | None = None,
    ) -> RestoreResult:
        return RestoreResult(
            exit_code=exit_code,
            dry_run=self.dry_run,
            errors=errors,
            leftover_symlink=leftover_symlink,
            source=self.source.as_posix(),
            managed=managed.as_posix(),
            replica_deletes=replica_deletes,
            git_excludes=git_excludes,
            holds=(),
            config_removed=config_removed,
            persist_warning=None,
        )

    def _validate(self, managed: Path) -> RestoreResult | None:
        """Run pre-flight validation checks before any filesystem mutation.

        Checks are performed in order:

        1. ``source`` must exist as a real path or as a dangling leftover symlink.
           A path that does not exist at all (not even as a symlink entry)
           is rejected here.
        2. ``source`` must be a regular file, a directory, or a leftover symlink.
        3. The managed copy at ``managed`` must exist.

        Args:
            managed: Derived managed copy path (``dest_root / rel_path``).

        Returns:
            A result when validation stops the plan, or ``None`` when all
            checks pass.
        """
        # exists() follows symlinks and returns False for dangling leftover
        # symlinks, so both conditions are needed to distinguish "nothing here"
        # from "dangling leftover symlink".
        if not self.source.exists() and not self.source.is_symlink():
            return self._result(managed, exit_code=1, errors=(f"Path does not exist: {self.source}",))

        if not self.source.is_symlink() and not self.source.is_file() and not self.source.is_dir():
            return self._result(managed, exit_code=1, errors=(f"Path is not a restorable projection: {self.source}",))

        if not managed.exists():
            if self.source.is_symlink():
                return self._result(
                    managed,
                    exit_code=1,
                    errors=(f"Dangling symlink: managed copy does not exist at {managed}",),
                )
            return self._result(managed, exit_code=1, errors=(f"Managed copy does not exist at {managed}",))

        return None

    def _mappings(self) -> list[Mapping]:
        """Return this managed project's mappings, or an empty list with no context.

        Returns:
            Config mappings for the resolved project.
        """
        if self.context is None:
            return []
        return self.context.mappings or [self.context.matched_mapping]

    def _participating_mappings(self) -> list[Mapping]:
        """Return mappings that declare this item.

        Sync-all mappings declare every item. Selective mappings declare the
        item when it is in their subpath list.

        Returns:
            Mappings whose targets currently project this item.
        """
        entry = self.rel_path.as_posix()
        return [mapping for mapping in self._mappings() if mapping.subpaths is None or entry in mapping.subpaths]

    def _selective_targets(self) -> set[Path]:
        """Return targets of participating selective mappings.

        Returns:
            Every target that lists this item in a subpath list.
        """
        entry = self.rel_path.as_posix()
        return {
            target
            for mapping in self._participating_mappings()
            if mapping.subpaths is not None and entry in mapping.subpaths
            for target in mapping.targets
        }

    def _remove_config(self) -> str | None:
        """Remove the source item from every participating selective mapping.

        Sync-all mappings have no subpath list and are left unchanged. Nested
        paths use ``rel_path.as_posix()`` so entries such as ``.kiro/specs/foo``
        match.

        This step is non-fatal: failures are silently ignored so that a config
        write error does not undo the already-completed restore.

        Returns:
            The subpath entry name when yaml changed, otherwise ``None``.
        """
        if self.context is None:
            return None

        entry_name = self.rel_path.as_posix()
        targets = self._selective_targets()
        if not targets:
            return None

        updater = ConfigUpdater(self.context.config_path)
        changed = updater.remove_subpath_entries(self.context.project_name, targets, entry_name)
        if changed:
            return entry_name
        return None
