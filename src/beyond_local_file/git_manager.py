"""Git exclude file management for symlink targets."""

from pathlib import Path


class GitExcludeManager:
    """Manages the .git/info/exclude file for symlink entries.

    This class provides functionality to read, write, and remove entries
    from the Git exclude file, which prevents Git from tracking symlinks
    that point outside the repository.

    Attributes:
        target_dir: The target directory where symlinks are created.
        git_dir: Path to the .git directory in the target.
        exclude_file: Path to the .git/info/exclude file.
    """

    GIT_DIR = ".git"
    EXCLUDE_FILE = "info/exclude"

    def __init__(self, target_dir: Path):
        """Initialize the GitExcludeManager for a target directory.

        Args:
            target_dir: The directory where symlinks are being created.
        """
        self.target_dir = Path(target_dir)
        self.git_dir = self.target_dir / self.GIT_DIR
        self.exclude_file = self.git_dir / self.EXCLUDE_FILE

    def is_git_repo(self) -> bool:
        """Check if the target directory is a Git repository.

        Returns:
            True if the target directory contains a .git directory.
        """
        return self.git_dir.exists() and self.git_dir.is_dir()

    def read_entries(self) -> set[str]:
        """Read all entries from the exclude file.

        Returns:
            Set of exclude entries (excluding comments and blank lines).
        """
        if not self.exclude_file.exists():
            return set()

        content = self.exclude_file.read_text()
        return {line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")}

    def write_entries(self, entries: set[str]) -> tuple[int, set[str]]:
        """Write entries to the exclude file.

        Adds new entries to the exclude file while preserving existing ones.

        Args:
            entries: Set of entry names to add to the exclude file.

        Returns:
            Tuple of (number of newly added entries, set of already existing entries).
        """
        self.exclude_file.parent.mkdir(parents=True, exist_ok=True)

        existing_entries = self.read_entries()
        new_entries = existing_entries | entries
        added_entries = entries - existing_entries
        already_existing = entries & existing_entries

        self.exclude_file.write_text("\n".join(sorted(new_entries)) + "\n")

        return len(added_entries), already_existing

    def remove_entries(self, entries: set[str]) -> set[str]:
        """Remove entries from the exclude file.

        Args:
            entries: Set of entry names to remove.

        Returns:
            Set of entries that were actually removed.
        """
        if not self.exclude_file.exists():
            return set()

        current_entries = self.read_entries()
        remaining = current_entries - entries

        self.exclude_file.write_text("\n".join(sorted(remaining)) + "\n")

        return current_entries & entries
