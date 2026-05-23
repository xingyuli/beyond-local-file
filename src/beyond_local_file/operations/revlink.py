"""revlink subcommand — operation logic and output formatting."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

import click

from beyond_local_file.git_manager import GitExcludeManager

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
                md5.update(str(file.relative_to(path)).encode())
                md5.update(file.read_bytes())
        return md5.hexdigest()


# ---------------------------------------------------------------------------
# RevlinkFormatter
# ---------------------------------------------------------------------------


class RevlinkFormatter:
    """Formats and prints step-by-step progress for the revlink operation.

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
        self._echo(f"Computing checksum of {source}")

    def copying(self, source: Path, dest: Path) -> None:
        """Print a message showing the source and destination paths for the copy.

        Args:
            source: Path to the original file or directory in the target
                directory.
            dest: Path to the destination location in the managed project.
        """
        self._echo(f"Copying {source} -> {dest}")

    def checksum_ok(self) -> None:
        """Print a confirmation that the MD5 checksums of source and copy match."""
        self._echo("✓ MD5 checksum verified")

    def symlink_created(self, link: Path, target: Path) -> None:
        """Print a confirmation that a symlink was created successfully.

        Args:
            link: Path where the symlink was created (original location in the
                target directory).
            target: Path the symlink points to (location in the managed
                project).
        """
        self._echo(f"✓ Symlink created: {link} -> {target}")

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
        self._echo(f"Warning: overwriting existing managed copy at {dest}")

    def error(self, message: str) -> None:
        """Print an error message.

        Args:
            message: Human-readable description of the error condition.
        """
        self._echo(f"Error: {message}")


# ---------------------------------------------------------------------------
# RevlinkOperation
# ---------------------------------------------------------------------------


@dataclass
class RevlinkOperation:
    """Orchestrates the copy-verify-replace workflow for a single source path.

    The operation proceeds through five internal steps — ``_validate``,
    ``_copy``, ``_verify``, ``_replace``, and ``_git_exclude`` — each of
    which returns early with exit code 1 on failure.  The public entry point
    is :meth:`run`.

    Attributes:
        source: Absolute path to the file or directory in the target directory
            that will be converted into a managed symlink.
        dest_root: ``managed_project_path`` from the resolved
            ``ConfigProject``; the destination root for the copy.
        dry_run: When ``True``, perform all validation and report what would
            happen without modifying the filesystem.
        force: When ``True``, overwrite an existing destination in the managed
            project.  MD5 verification still applies.
        formatter: Formatter instance used for all user-facing output.
    """

    source: Path
    dest_root: Path
    dry_run: bool
    force: bool
    formatter: RevlinkFormatter

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> int:
        """Execute the full revlink workflow and return an exit code.

        Derives ``dest`` as ``dest_root / source.name``, then runs the
        pre-flight validation step.  When not in dry-run mode, proceeds
        through copy, verify, replace, and git-exclude steps in order.
        When in dry-run mode, previews all steps via the formatter without
        modifying the filesystem.

        Returns:
            ``0`` on success, ``1`` if any step fails.
        """
        dest = self.dest_root / self.source.name

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

            result = self._replace(dest)
            if result != 0:
                return result

            self._git_exclude()

        return 0

    def _preview(self, dest: Path) -> None:
        """Emit dry-run preview messages for all steps without touching the filesystem.

        Called by :meth:`run` when ``dry_run=True`` and validation has passed.
        Mirrors the output of the real steps so the user can see exactly what
        would happen.

        Args:
            dest: Derived destination path (``dest_root / source.name``).
        """
        if self.force and dest.exists():
            self.formatter.force_warning(dest)
        self.formatter.copying(self.source, dest)
        self.formatter.computing_checksum(self.source)
        self.formatter.checksum_ok()
        self.formatter.symlink_created(self.source, dest)
        self._git_exclude_preview()

    # ------------------------------------------------------------------
    # Internal steps
    # ------------------------------------------------------------------

    def _validate(self, dest: Path) -> int:
        """Run pre-flight validation checks before any filesystem mutation.

        Checks are performed in order:

        1. ``source`` must exist.
        2. ``source`` must not already be a symlink.
        3. ``dest`` must not exist, unless ``--force`` is set.

        Args:
            dest: Derived destination path (``dest_root / source.name``).

        Returns:
            ``0`` if all checks pass, ``1`` on the first failing check.
        """
        if not self.source.exists():
            self.formatter.error(f"Path does not exist: {self.source}")
            return 1

        if self.source.is_symlink():
            self.formatter.error(f"Path is already a symlink: {self.source}")
            return 1

        if dest.exists() and not self.force:
            self.formatter.error(f"Destination already exists: {dest}\nUse --force to overwrite.")
            return 1

        return 0

    def _copy(self, dest: Path) -> int:
        """Copy the source file or directory to the managed project destination.

        When ``--force`` is active, emits a warning and removes any existing
        destination before copying.  Always emits a progress message showing
        the source and destination paths before the copy begins.

        For files, uses ``shutil.copy2`` to preserve metadata.  For
        directories, uses ``shutil.copytree`` to recursively copy the entire
        tree.

        Args:
            dest: Derived destination path (``dest_root / source.name``).

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

        if self.source.is_dir():
            shutil.copytree(self.source, dest)
        else:
            shutil.copy2(self.source, dest)

        return 0

    def _verify(self, dest: Path) -> int:
        """Verify the integrity of the copy by comparing MD5 checksums.

        Computes the MD5 digest of both the original source and the newly
        created copy at ``dest``.  If the digests match, emits a confirmation
        message and returns 0.  If they differ, deletes the corrupt copy,
        emits an error message, and returns 1 so the caller can abort.

        Args:
            dest: Derived destination path (``dest_root / source.name``)
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

    def _replace(self, dest: Path) -> int:
        """Remove the source and create a symlink pointing to the managed copy.

        Attempts to remove the original source path (file or directory) and
        replace it with a symlink pointing to ``dest`` in the managed project.
        Emits a success message on completion.

        Two distinct failure modes are handled:

        - **Permission error** during removal: the source is left untouched and
          an error message is emitted.
        - **OSError** during symlink creation: the source has already been
          removed at this point, leaving the filesystem in an inconsistent
          state.  An error message explicitly warns the user so they can
          recover manually.

        Args:
            dest: Derived destination path (``dest_root / source.name``) that
                the new symlink will point to.

        Returns:
            ``0`` on success, ``1`` if removal or symlink creation fails.
        """
        try:
            if self.source.is_dir():
                shutil.rmtree(self.source)
            else:
                self.source.unlink()
        except PermissionError:
            self.formatter.error(f"Permission denied removing {self.source}")
            return 1

        try:
            self.source.symlink_to(dest)
        except OSError:
            self.formatter.error(
                f"Failed to create symlink at {self.source} \u2192 {dest}. Filesystem may be in inconsistent state."
            )
            return 1

        self.formatter.symlink_created(self.source, dest)
        return 0

    def _git_exclude_preview(self) -> None:
        """Emit a dry-run preview for the git-exclude step.

        Checks whether the source's parent directory is a Git repository and
        whether the entry already exists, then reports what would happen via
        the formatter — without writing anything.
        """
        manager = GitExcludeManager(self.source.parent)
        if not manager.is_git_repo():
            return
        existing = manager.read_entries()
        if self.source.name in existing:
            self.formatter.git_exclude_exists(self.source.name)
        else:
            self.formatter.git_exclude_added(self.source.name)

    def _git_exclude(self) -> int:
        """Add the source item to ``.git/info/exclude`` if inside a Git repository.

        Instantiates a :class:`~beyond_local_file.git_manager.GitExcludeManager`
        for the source's parent directory.  If the directory is not a Git
        repository the step is silently skipped (Requirement 6.3).  Otherwise
        calls :meth:`~beyond_local_file.git_manager.GitExcludeManager.write_entries`
        with a set containing ``source.name`` and reports the outcome via the
        formatter.

        This step is non-fatal: it always returns ``0`` regardless of whether
        the entry was added, already existed, or the directory is not a Git
        repository.

        Returns:
            Always ``0``.
        """
        manager = GitExcludeManager(self.source.parent)

        if not manager.is_git_repo():
            return 0

        added_count, already_existing = manager.write_entries({self.source.name})

        if added_count > 0:
            self.formatter.git_exclude_added(self.source.name)
        elif self.source.name in already_existing:
            self.formatter.git_exclude_exists(self.source.name)

        return 0
