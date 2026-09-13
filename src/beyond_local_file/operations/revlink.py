"""revlink subcommand — operation logic and output formatting."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import click

from beyond_local_file.config import ConfigUpdater
from beyond_local_file.copy_manager import copy_projection
from beyond_local_file.daemon.process import state_dir
from beyond_local_file.git_manager import GitExcludeManager
from beyond_local_file.held import (
    REASON_CREATE_OVERWRITE,
    reason_clause,
    store_held_copy,
)
from beyond_local_file.model.config import Mapping
from beyond_local_file.sync_state import SyncState, compute_item_hash

# ---------------------------------------------------------------------------
# ChecksumVerifier
# ---------------------------------------------------------------------------


class ChecksumVerifier:
    """Computes deterministic MD5 digests for files and directory trees.

    For a single file the digest covers the file's raw bytes. For a directory
    the digest covers the concatenation of each file's relative path string
    and its raw bytes, with files visited in sorted order so the result is
    independent of filesystem traversal order.
    """

    @staticmethod
    def compute(path: Path) -> str:
        """Compute the MD5 digest for a file or directory tree.

        For a file: MD5 of the file's raw bytes.
        For a directory: MD5 of the sorted ``(relative_path_str + file_bytes)``
        concatenation, visiting all files under the tree via ``rglob("*")``.

        Args:
            path: Absolute or relative path to a file or directory.

        Returns:
            Hex-encoded MD5 digest string (32 lowercase hex characters).

        Raises:
            FileNotFoundError: If ``path`` does not exist.
            IsADirectoryError: If a path expected to be a file is a directory
                (should not occur in normal usage).
        """
        if path.is_dir():
            return ChecksumVerifier._hash_directory(path)
        return ChecksumVerifier._hash_file(path)

    @staticmethod
    def _hash_file(path: Path) -> str:
        """Compute MD5 of a single file's contents.

        Args:
            path: Path to the file.

        Returns:
            Hex-encoded MD5 digest string.
        """
        md5 = hashlib.md5()
        md5.update(path.read_bytes())
        return md5.hexdigest()

    @staticmethod
    def _hash_directory(path: Path) -> str:
        """Compute a deterministic MD5 digest for a directory tree.

        Files are visited in sorted order by their path relative to ``path``
        so the digest is independent of filesystem traversal order.

        Args:
            path: Root directory to hash.

        Returns:
            Hex-encoded MD5 digest string.
        """
        md5 = hashlib.md5()
        for file in sorted(path.rglob("*")):
            if file.is_file():
                # as_posix() keeps digests identical across Windows and Unix.
                md5.update(file.relative_to(path).as_posix().encode())
                md5.update(file.read_bytes())
        return md5.hexdigest()


# ---------------------------------------------------------------------------
# CreateFormatter
# ---------------------------------------------------------------------------


class CreateFormatter:
    """Formats and prints step-by-step progress for the revlink create operation.

    All output is emitted via ``click.echo``. When ``dry_run`` is ``True``
    every output line is prefixed with ``[dry-run]`` so the user can
    distinguish preview output from real output.
    """

    def __init__(self, dry_run: bool) -> None:
        """Initialise the formatter.

        Args:
            dry_run: When ``True``, prefix every output line with
                ``[dry-run]``.
        """
        self._dry_run = dry_run

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _echo(self, message: str) -> None:
        """Emit a single output line, prepending the dry-run prefix if active.

        Args:
            message: The message text to display.
        """
        if self._dry_run:
            click.echo(f"[dry-run] {message}")
        else:
            click.echo(message)

    # ------------------------------------------------------------------
    # Public formatter methods
    # ------------------------------------------------------------------

    def computing_checksum(self, source: Path) -> None:
        """Print a message indicating that the checksum of *source* is being computed.

        Args:
            source: Path to the file or directory whose checksum is being
                computed.
        """
        self._echo(f"Computing checksum of {source.as_posix()}")

    def copying(self, source: Path, dest: Path) -> None:
        """Print a message showing the source and destination paths for the copy.

        Args:
            source: Path to the original file or directory in the target
                directory.
            dest: Path to the destination location in the managed project.
        """
        self._echo(f"Copying {source.as_posix()} -> {dest.as_posix()}")

    def checksum_ok(self) -> None:
        """Print a confirmation that the MD5 checksums of source and copy match."""
        self._echo("✓ MD5 checksum verified")

    def target_left_in_place(self, path: Path) -> None:
        """Print a confirmation that the target path remains a real file or directory.

        Args:
            path: Target-side path that was left in place as a projection.
        """
        self._echo(f"✓ Target path left in place: {path.as_posix()}")

    def git_exclude_added(self, name: str) -> None:
        """Print a confirmation that *name* was added to ``.git/info/exclude``.

        Args:
            name: The filename or directory name that was added to the git
                exclude file.
        """
        self._echo(f"Added {name!r} to .git/info/exclude")

    def git_exclude_exists(self, name: str) -> None:
        """Print a notice that *name* is already present in ``.git/info/exclude``.

        Args:
            name: The filename or directory name that already exists in the
                git exclude file.
        """
        self._echo(f"{name!r} already in .git/info/exclude")

    def force_warning(self, dest: Path) -> None:
        """Print a warning that the existing managed copy at *dest* will be overwritten.

        Args:
            dest: Path to the existing file or directory in the managed project
                that will be overwritten.
        """
        self._echo(f"Warning: overwriting existing managed copy at {dest.as_posix()}")

    def info(self, message: str) -> None:
        """Print an informational message (no ``Error:`` prefix).

        Used for non-error early exits such as the Rule 3 managed-symlink
        case where the path is already managed through an ancestor.

        Args:
            message: Human-readable informational text to display.
        """
        self._echo(message)

    def error(self, message: str) -> None:
        """Print an error message.

        Args:
            message: Human-readable description of the error condition.
        """
        self._echo(f"Error: {message}")

    def config_updated(self, entry_name: str) -> None:
        """Print a confirmation that *entry_name* was added to the config subpath list.

        Args:
            entry_name: The filename or directory name added to the config.
        """
        self._echo(f"Added {entry_name!r} to config subpath list")

    def fan_out_copying(self, hub: Path, replica: Path) -> None:
        """Print that the hub copy is being fanned out to a replica.

        Args:
            hub: Managed-project copy.
            replica: Path on another target project.
        """
        self._echo(f"Fan-out {hub.as_posix()} -> {replica.as_posix()}")

    def held_overwrite_warning(self, clause: str, held_slot: Path) -> None:
        """Print the hold-reason clause and where the previous bytes were stored.

        Args:
            clause: Hold-reason clause for WARNINGs and the later resolve UI.
            held_slot: Directory under ``.blf-held/`` that now holds the bytes.
        """
        self._echo(f"WARNING: {clause}")
        self._echo(f"Held at {held_slot.as_posix()}")


# ---------------------------------------------------------------------------
# RestoreFormatter
# ---------------------------------------------------------------------------


class RestoreFormatter:
    """Formats and prints step-by-step progress for the revlink restore operation.

    All output is emitted via ``click.echo``. When ``dry_run`` is ``True``
    every output line is prefixed with ``[dry-run]`` so the user can
    distinguish preview output from real output.
    """

    def __init__(self, dry_run: bool) -> None:
        """Initialise the formatter.

        Args:
            dry_run: When ``True``, prefix every output line with
                ``[dry-run]``.
        """
        self._dry_run = dry_run

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _echo(self, message: str) -> None:
        """Emit a single output line, prepending the dry-run prefix if active.

        Args:
            message: The message text to display.
        """
        if self._dry_run:
            click.echo(f"[dry-run] {message}")
        else:
            click.echo(message)

    # ------------------------------------------------------------------
    # Public formatter methods
    # ------------------------------------------------------------------

    def leaving_target_file(self, path: Path) -> None:
        """Print a confirmation that the target path is left as an unmanaged file.

        Args:
            path: Target-side path that remains after the hub copy is deleted.
        """
        self._echo(f"Leaving target file in place: {path.as_posix()}")

    def removing_symlink(self, path: Path) -> None:
        """Print a message indicating that the leftover symlink at *path* is removed.

        Args:
            path: Path to the leftover symlink that is about to be unlinked.
        """
        self._echo(f"Removing symlink at {path.as_posix()}")

    def copying_back(self, source: Path, dest: Path) -> None:
        """Print a message showing the managed copy source and the restore destination.

        Args:
            source: Path to the managed copy (the symlink target in the managed
                project).
            dest: Path to the destination in the current working directory where
                the content is being restored.
        """
        self._echo(f"Copying {source.as_posix()} -> {dest.as_posix()}")

    def computing_checksum(self, source: Path) -> None:
        """Print a message indicating that the checksum of *source* is being computed.

        Args:
            source: Path to the file or directory whose checksum is being
                computed.
        """
        self._echo(f"Computing checksum of {source.as_posix()}")

    def checksum_ok(self) -> None:
        """Print a confirmation that the MD5 checksums of the managed copy and restored copy match."""
        self._echo("✓ MD5 checksum verified")

    def managed_copy_deleted(self, path: Path) -> None:
        """Print a confirmation that the managed copy at *path* was deleted successfully.

        Args:
            path: Path to the managed copy that was deleted.
        """
        self._echo(f"✓ Managed copy deleted: {path.as_posix()}")

    def managed_copy_delete_failed(self, path: Path) -> None:
        """Print a warning that the managed copy at *path* could not be deleted.

        This is a non-fatal warning — the restore to CWD has already succeeded
        and been verified.  The managed copy is left in place for manual cleanup.

        Args:
            path: Path to the managed copy that could not be deleted.
        """
        self._echo(f"Warning: could not delete managed copy at {path.as_posix()}")

    def git_exclude_removed(self, name: str) -> None:
        """Print a confirmation that *name* was removed from ``.git/info/exclude``.

        Args:
            name: The filename or directory name that was removed from the git
                exclude file.
        """
        self._echo(f"Removed {name!r} from .git/info/exclude")

    def git_exclude_not_found(self, name: str) -> None:
        """Print a notice that *name* was not found in ``.git/info/exclude``.

        Args:
            name: The filename or directory name that was not present in the
                git exclude file.
        """
        self._echo(f"{name!r} not in .git/info/exclude")

    def config_entry_removed(self, name: str) -> None:
        """Print a confirmation that *name* was removed from the config subpath list.

        Args:
            name: The filename or directory name removed from the config.
        """
        self._echo(f"Removed {name!r} from config subpath list")

    def error(self, message: str) -> None:
        """Print an error message.

        Args:
            message: Human-readable description of the error condition.
        """
        self._echo(f"Error: {message}")


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
    """Orchestrates the copy-verify-register workflow for a single source path.

    The operation proceeds through internal steps — ``_validate``,
    ``_copy``, ``_verify``, ``_record_sync_state``, and ``_git_exclude`` —
    each of which returns early with exit code 1 on failure.  The public
    entry point is :meth:`run`.

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
            project.  MD5 verification still applies.
        formatter: Formatter instance used for all user-facing output.
        context: Config-resolution context used for the post-copy config
            update step.  ``None`` skips the update (useful in tests).
    """

    source: Path
    dest_root: Path
    rel_path: Path
    dry_run: bool
    force: bool
    formatter: CreateFormatter
    context: RevlinkContext | None = field(default=None)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> int:
        """Execute the full revlink workflow and return an exit code.

        Derives ``dest`` as ``dest_root / rel_path``, preserving the full
        directory structure so the managed layout mirrors the target layout
        exactly.  Runs the pre-flight validation step, then proceeds through
        copy, verify, record-sync-state, and git-exclude steps in order when
        not in dry-run mode.  In dry-run mode, previews all steps via the
        formatter without modifying the filesystem.

        Returns:
            ``0`` on success, ``1`` if any step fails.
        """
        dest = self.dest_root / self.rel_path

        result = self._validate(dest)
        if result != 0:
            return result

        if self.dry_run:
            self._preview(dest)
        else:
            result = self._copy(dest)
            if result != 0:
                return result

            result = self._verify(dest)
            if result != 0:
                return result

            self.formatter.target_left_in_place(self.source)
            self._record_sync_state(dest, self.source)
            self._git_exclude(self.context.cwd if self.context is not None else None)
            self._update_config()
            self._fan_out(dest)

        return 0

    def _preview(self, dest: Path) -> None:
        """Emit dry-run preview messages for all steps without touching the filesystem.

        Called by :meth:`run` when ``dry_run=True`` and validation has passed.
        Mirrors the output of the real steps so the user can see exactly what
        would happen.

        Args:
            dest: Derived destination path (``dest_root / rel_path``).
        """
        if self.force and dest.exists():
            self.formatter.force_warning(dest)
        self.formatter.copying(self.source, dest)
        self.formatter.computing_checksum(self.source)
        self.formatter.checksum_ok()
        self.formatter.target_left_in_place(self.source)
        self._git_exclude_preview()
        if self.context is not None and self.context.matched_mapping.subpaths is not None:
            self.formatter.config_updated(self.rel_path.as_posix())
        for replica_root in self._other_replica_roots():
            self.formatter.fan_out_copying(dest, replica_root / self.rel_path)

    # ------------------------------------------------------------------
    # Internal steps
    # ------------------------------------------------------------------

    def _validate(self, dest: Path) -> int:  # noqa: PLR0911, PLR0912 -- each validation rule needs its own early return; six ordered rules require multiple branches
        """Run pre-flight validation checks before any filesystem mutation.

        Checks are performed in order:

        1. ``source`` must exist.
        2. ``source`` must not already be a symlink.
        3. No ancestor directory of ``rel_path`` may be a symlink (skipped when
           ``self.context is None``).  If an ancestor symlink resolves into the
           managed project the path is already managed — print an info message
           and return 0.  If it resolves elsewhere print an error and return 1.
        4. When the matched mapping uses sync-all (``subpaths is None``),
           ``rel_path`` must have exactly one component — nested paths are
           rejected with an error (skipped when ``self.context is None``).
        5. When the matched mapping uses selective sync (``subpaths is not None``),
           check each declared subpath for conflicts (skipped when
           ``self.context is None``):

           - 5a: if a declared subpath is an ancestor of (or equal to)
             ``rel_path``, the path is already covered — print an error
             directing the user to let the daemon project the copy (or copy
             manually first) and return 1.
           - 5b: if ``rel_path`` is an ancestor of a declared subpath (reverse
             conflict), adopting the broader path would shadow the narrower
             declared entry — print an error and return 1.

        6. ``dest`` must not exist, unless ``--force`` is set.

        Args:
            dest: Derived destination path (``dest_root / rel_path``).

        Returns:
            ``0`` if all checks pass, ``1`` on the first failing check, or
            ``0`` for the Rule 3 managed-symlink early exit.
        """
        if not self.source.exists():
            self.formatter.error(f"Path does not exist: {self.source}")
            return 1

        if self.source.is_symlink():
            self.formatter.error(f"Path is already a symlink: {self.source.as_posix()}")
            return 1

        # Rule 3 — no intermediate symlink in the path
        if self.context is not None:
            for anc in self.rel_path.parents:
                if anc == Path("."):
                    continue
                candidate = self.context.cwd / anc
                if candidate.is_symlink():
                    resolved = candidate.resolve()
                    if resolved.is_relative_to(self.dest_root):
                        self.formatter.info(
                            f"'{anc.as_posix()}' is a managed symlink — '{self.rel_path.as_posix()}' is already"
                            " managed through it. Nothing to do."
                        )
                        return 0
                    else:
                        self.formatter.error(
                            f"'{anc.as_posix()}' is a symlink not managed by blf."
                            " Cannot adopt a path through an unmanaged symlink."
                        )
                        return 1

        # Rule 4 — sync-all mapping rejects nested paths
        if self.context is not None and self.context.matched_mapping.subpaths is None and len(self.rel_path.parts) > 1:
            self.formatter.error(
                f"'{self.rel_path.as_posix()}' is a nested path. This mapping uses sync-all"
                " — only top-level paths can be adopted directly."
                " Add a 'subpath' entry to your config mapping first."
            )
            return 1

        # Rule 5 — selective sync mapping: no ancestor subpath conflict
        if self.context is not None and self.context.matched_mapping.subpaths is not None:
            managed_copy = self.dest_root / self.rel_path
            for declared in self.context.matched_mapping.subpaths:
                declared_path = Path(declared)
                # 5a — declared subpath is an ancestor of (or equal to) rel_path
                if self.rel_path == declared_path or self.rel_path.is_relative_to(declared_path):
                    if managed_copy.exists():
                        self.formatter.error(
                            f"'{declared}' is already a declared subpath that covers this path,"
                            f" and the managed copy already exists at '{managed_copy.as_posix()}'."
                            " The daemon projects this copy."
                        )
                    else:
                        self.formatter.error(
                            f"'{declared}' is already a declared subpath that covers this path."
                            f" Copy '{self.source.as_posix()}' to '{managed_copy.as_posix()}' manually;"
                            " the daemon will project the copy."
                        )
                    return 1
                # 5b — rel_path is an ancestor of a declared subpath (reverse conflict)
                if declared_path.is_relative_to(self.rel_path) and declared_path != self.rel_path:
                    self.formatter.error(
                        f"'{declared}' is a declared subpath under this path."
                        f" Adopting '{self.rel_path.as_posix()}' would conflict with it."
                        f" Remove '{declared}' from the config subpath list first,"
                        " or adopt a more specific path."
                    )
                    return 1

        if dest.exists() and not self.force:
            self.formatter.error(f"Destination already exists: {dest.as_posix()}\nUse --force to overwrite.")
            return 1

        return 0

    def _copy(self, dest: Path) -> int:
        """Copy the source file or directory to the managed project destination.

        When ``--force`` is active, emits a warning and removes any existing
        destination before copying.  Always emits a progress message showing
        the source and destination paths before the copy begins.

        Copies files and directory trees while preserving nested symlink nodes.

        Args:
            dest: Derived destination path (``dest_root / rel_path``).

        Returns:
            ``0`` on success.
        """
        if self.force:
            self.formatter.force_warning(dest)
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()

        self.formatter.copying(self.source, dest)

        copy_projection(self.source, dest)

        return 0

    def _verify(self, dest: Path) -> int:
        """Verify the integrity of the copy by comparing MD5 checksums.

        Computes the MD5 digest of both the original source and the newly
        created copy at ``dest``.  If the digests match, emits a confirmation
        message and returns 0.  If they differ, deletes the corrupt copy,
        emits an error message, and returns 1 so the caller can abort.

        Args:
            dest: Derived destination path (``dest_root / rel_path``)
                where the copy was placed by :meth:`_copy`.

        Returns:
            ``0`` if the checksums match, ``1`` if they differ or the copy
            is otherwise untrustworthy.
        """
        self.formatter.computing_checksum(self.source)

        source_checksum = ChecksumVerifier.compute(self.source)
        dest_checksum = ChecksumVerifier.compute(dest)

        if source_checksum != dest_checksum:
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
            self.formatter.error("Checksum mismatch \u2014 copy may be corrupt. Destination deleted.")
            return 1

        self.formatter.checksum_ok()
        return 0

    def _record_sync_state(self, dest: Path, replica: Path) -> None:
        """Record a hub/replica pair as in-sync so a later catch-up is a no-op.

        Args:
            dest: Managed-project copy path.
            replica: Target-project path paired with *dest*.
        """
        if self.context is None:
            return
        sync_state = SyncState(state_dir(self.context.config_path))
        sync_state.load()
        sync_state.update_record(dest, replica)
        sync_state.save()

    def _other_replica_roots(self) -> list[Path]:
        """Return other target-project roots for this managed project.

        Returns:
            Unique target paths excluding the source replica (cwd).
        """
        if self.context is None:
            return []
        source = self.context.cwd.resolve()
        seen: set[Path] = set()
        roots: list[Path] = []
        mappings = self.context.mappings or [self.context.matched_mapping]
        for mapping in mappings:
            for target in mapping.targets:
                resolved = target.resolve()
                if resolved == source or resolved in seen:
                    continue
                seen.add(resolved)
                roots.append(target)
        return roots

    def _copy_item(self, src: Path, dest: Path) -> None:
        """Copy a file or directory tree from *src* to *dest*.

        Args:
            src: Existing file or directory.
            dest: Destination path; parent directories are created.
        """
        copy_projection(src, dest)

    def _fan_out(self, dest: Path) -> None:
        """Copy the hub item onto every non-source replica.

        Equal bytes are left in place. Different bytes are held with reason
        ``create-overwrite``, then overwritten from the hub.

        Args:
            dest: Managed-project copy to fan out.
        """
        if self.context is None:
            return
        rel = self.rel_path.as_posix()
        for replica_root in self._other_replica_roots():
            replica_path = replica_root / self.rel_path
            self.formatter.fan_out_copying(dest, replica_path)
            if replica_path.exists() and compute_item_hash(replica_path) != compute_item_hash(dest):
                clause = reason_clause(
                    REASON_CREATE_OVERWRITE,
                    path=rel,
                    replica=replica_root.as_posix(),
                )
                slot = store_held_copy(
                    self.dest_root,
                    rel_path=self.rel_path,
                    source=replica_path,
                    replica=replica_root,
                    reason=REASON_CREATE_OVERWRITE,
                )
                self.formatter.held_overwrite_warning(clause, slot)
            self._copy_item(dest, replica_path)
            self._record_sync_state(dest, replica_path)
            self._git_exclude(replica_root)

    def _update_config(self) -> None:
        """Add the item to every selective mapping of this managed project.

        Sync-all mappings have no subpath list and are left unchanged.
        Failures are non-fatal so a config write error does not undo the copy.
        """
        if self.context is None:
            return
        mappings = self.context.mappings or [self.context.matched_mapping]
        selective = [mapping for mapping in mappings if mapping.subpaths is not None]
        if not selective:
            return
        updater = ConfigUpdater(self.context.config_path)
        entry_name = self.rel_path.as_posix()
        changed = False
        for mapping in selective:
            targets = getattr(mapping, "targets", None) or [self.context.cwd]
            for target in targets:
                if updater.add_subpath_entry(self.context.project_name, target, entry_name):
                    changed = True
        if changed:
            self.formatter.config_updated(entry_name)

    def _git_exclude_preview(self) -> None:
        """Emit a dry-run preview for the git-exclude step.

        Checks whether the project root (``context.cwd``) is a Git repository
        and whether the entry already exists, then reports what would happen via
        the formatter — without writing anything.

        The entry name is ``self.rel_path.as_posix()`` (e.g. ``.kiro/specs/foo``)
        rather than ``source.name`` so the exclude entry mirrors the full
        relative path used by catch-up and ``link check``.
        """
        if self.context is None:
            return
        manager = GitExcludeManager(self.context.cwd)
        if not manager.is_git_repo():
            return
        existing = manager.read_entries()
        entry_name = self.rel_path.as_posix()
        if entry_name in existing:
            self.formatter.git_exclude_exists(entry_name)
        else:
            self.formatter.git_exclude_added(entry_name)

    def _git_exclude(self, replica_root: Path | None = None) -> int:
        """Add the item to ``.git/info/exclude`` for *replica_root* if it is a Git repo.

        If *replica_root* is omitted, the source replica (cwd) is used.

        Args:
            replica_root: Target-project root to exclude in.

        Returns:
            Always ``0``.
        """
        if self.context is None:
            return 0
        root = replica_root if replica_root is not None else self.context.cwd
        manager = GitExcludeManager(root)

        if not manager.is_git_repo():
            return 0

        entry_name = self.rel_path.as_posix()
        added_count, already_existing = manager.write_entries({entry_name})

        if added_count > 0:
            self.formatter.git_exclude_added(entry_name)
        elif entry_name in already_existing:
            self.formatter.git_exclude_exists(entry_name)

        return 0


# ---------------------------------------------------------------------------
# RestoreOperation
# ---------------------------------------------------------------------------


@dataclass
class RestoreOperation:
    """Orchestrates the validate-cleanup workflow for a single projection path.

    The operation is the inverse of :class:`CreateOperation`. It deletes the
    hub copy, leaves the requesting target's file in place, and leaves other
    targets' copies as unmanaged files.

    The operation proceeds through internal steps — ``_validate``, ``_replace``,
    ``_verify``, ``_delete_managed``, ``_git_exclude``, and ``_remove_config`` —
    each of which returns early with exit code 1 on failure (except cleanup steps
    which are non-fatal). The public entry point is :meth:`run`.

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
        formatter: Formatter instance used for all user-facing output.
        context: Config-resolution context used for the post-restore config
            removal step.  ``None`` skips the update (useful in tests).
    """

    source: Path
    dest_root: Path
    rel_path: Path
    dry_run: bool
    formatter: RestoreFormatter
    context: RevlinkContext | None = field(default=None)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> int:
        """Execute the full restore workflow and return an exit code.

        Derives ``managed`` as ``dest_root / rel_path``, preserving the full
        directory structure so the managed copy location mirrors the target
        layout exactly.  Then runs the pre-flight validation step.  When not
        in dry-run mode, proceeds through replace, verify, delete-managed,
        git-exclude, and remove-config steps in order.  When in dry-run mode,
        previews all steps via the formatter without modifying the filesystem.

        Returns:
            ``0`` on success, ``1`` if any step fails.
        """
        managed = self.dest_root / self.rel_path

        result = self._validate(managed)
        if result != 0:
            return result

        if self.dry_run:
            self._preview(managed)
        else:
            if self.source.is_symlink():
                result = self._replace(managed)
                if result != 0:
                    return result

                result = self._verify(managed)
                if result != 0:
                    return result
            else:
                self.formatter.leaving_target_file(self.source)

            self._delete_managed(managed)
            self._git_exclude()
            self._remove_config()

        return 0

    def _preview(self, managed: Path) -> None:
        """Emit dry-run preview messages for all steps without touching the filesystem.

        Called by :meth:`run` when ``dry_run=True`` and validation has passed.
        Mirrors the output of the real steps so the user can see exactly what
        would happen.

        Args:
            managed: Derived managed copy path (``dest_root / rel_path``).
        """
        if self.source.is_symlink():
            self.formatter.removing_symlink(self.source)
            self.formatter.copying_back(managed, self.source)
            self.formatter.computing_checksum(managed)
            self.formatter.checksum_ok()
        else:
            self.formatter.leaving_target_file(self.source)
        self.formatter.managed_copy_deleted(managed)

    # ------------------------------------------------------------------
    # Internal steps
    # ------------------------------------------------------------------

    def _validate(self, managed: Path) -> int:
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
            ``0`` if all checks pass, ``1`` on the first failing check.
        """
        # exists() follows symlinks and returns False for dangling leftover
        # symlinks, so both conditions are needed to distinguish "nothing here"
        # from "dangling leftover symlink".
        if not self.source.exists() and not self.source.is_symlink():
            self.formatter.error(f"Path does not exist: {self.source}")
            return 1

        if not self.source.is_symlink() and not self.source.is_file() and not self.source.is_dir():
            self.formatter.error(f"Path is not a restorable projection: {self.source}")
            return 1

        if not managed.exists():
            if self.source.is_symlink():
                self.formatter.error(f"Dangling symlink: managed copy does not exist at {managed}")
            else:
                self.formatter.error(f"Managed copy does not exist at {managed}")
            return 1

        return 0

    def _replace(self, managed: Path) -> int:
        """Remove the symlink and copy the managed content back to the CWD path.

        The symlink is always a single inode regardless of whether its target
        is a file or directory, so ``source.unlink()`` is always used — never
        ``shutil.rmtree(source)``, which would follow the link and delete the
        managed copy.

        After unlinking, the managed content is copied back, preserving nested
        symlink nodes.

        Args:
            managed: Derived managed copy path (``dest_root / rel_path``)
                whose content will be copied back to ``source``.

        Returns:
            ``0`` on success, ``1`` if the symlink cannot be removed.
        """
        self.formatter.removing_symlink(self.source)

        try:
            self.source.unlink(missing_ok=False)
        except PermissionError:
            self.formatter.error(f"Permission denied removing symlink at {self.source}")
            return 1

        self.formatter.copying_back(managed, self.source)

        copy_projection(managed, self.source)

        return 0

    def _verify(self, managed: Path) -> int:
        """Verify the integrity of the restored copy by comparing MD5 checksums.

        Computes the MD5 digest of both the managed copy and the newly
        restored file at ``source``.  If the digests match, emits a
        confirmation message and returns 0.  If they differ, deletes the
        corrupt restored copy, emits an error message, and returns 1 so the
        caller can abort.

        Args:
            managed: Derived managed copy path (``dest_root / rel_path``)
                used as the reference for checksum comparison.

        Returns:
            ``0`` if the checksums match, ``1`` if they differ.
        """
        self.formatter.computing_checksum(managed)

        managed_checksum = ChecksumVerifier.compute(managed)
        restored_checksum = ChecksumVerifier.compute(self.source)

        if managed_checksum != restored_checksum:
            if self.source.is_dir():
                shutil.rmtree(self.source)
            else:
                self.source.unlink()
            self.formatter.error("Checksum mismatch \u2014 restored copy deleted. Managed copy preserved.")
            return 1

        self.formatter.checksum_ok()
        return 0

    def _delete_managed(self, managed: Path) -> None:
        """Attempt to delete the managed copy after a successful verified restore.

        Failure (e.g. permission error) is a warning, not fatal — the restore
        to CWD has already succeeded and been verified.

        Args:
            managed: Path to the managed copy to delete.
        """
        try:
            if managed.is_dir():
                shutil.rmtree(managed)
            else:
                managed.unlink()
            self.formatter.managed_copy_deleted(managed)
        except OSError:
            self.formatter.managed_copy_delete_failed(managed)

    def _git_exclude(self) -> int:
        """Remove the source item from ``.git/info/exclude`` if inside a Git repository.

        Instantiates a :class:`~beyond_local_file.git_manager.GitExcludeManager`
        for the project root (``context.cwd``).  If the directory is not a Git
        repository the step is silently skipped.  Otherwise calls
        :meth:`~beyond_local_file.git_manager.GitExcludeManager.remove_entries`
        with a set containing ``rel_path.as_posix()`` and reports the outcome via the
        formatter.  Using ``rel_path`` rather than ``source.name`` ensures the
        entry matches what was written by :class:`CreateOperation` for nested
        paths (e.g. ``.kiro/specs/foo`` instead of just ``foo``).

        This step is non-fatal: it always returns ``0`` regardless of outcome.

        Returns:
            Always ``0``.
        """
        if self.context is None:
            return 0
        manager = GitExcludeManager(self.context.cwd)

        if not manager.is_git_repo():
            return 0

        entry_name = self.rel_path.as_posix()
        removed = manager.remove_entries({entry_name})

        if entry_name in removed:
            self.formatter.git_exclude_removed(entry_name)
        else:
            self.formatter.git_exclude_not_found(entry_name)

        return 0

    def _remove_config(self) -> None:
        """Remove the source item from every participating selective mapping.

        Other targets keep their files, but those copies become unmanaged once
        the subpath is dropped. Sync-all mappings have no subpath list and are
        left unchanged. Nested paths use ``rel_path.as_posix()`` so entries
        such as ``.kiro/specs/foo`` match.

        This step is non-fatal: failures are silently ignored so that a config
        write error does not undo the already-completed restore.
        """
        if self.context is None:
            return

        entry_name = self.rel_path.as_posix()
        mappings = self.context.mappings or [self.context.matched_mapping]
        targets = {
            target
            for mapping in mappings
            if mapping.subpaths is not None and entry_name in mapping.subpaths
            for target in mapping.targets
        }
        if not targets:
            return

        updater = ConfigUpdater(self.context.config_path)
        changed = updater.remove_subpath_entries(self.context.project_name, targets, entry_name)
        if changed:
            self.formatter.config_entry_removed(entry_name)
