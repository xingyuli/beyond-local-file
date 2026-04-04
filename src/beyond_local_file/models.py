"""Data models for representing projects and their items."""

from dataclasses import dataclass
from pathlib import Path

from .model.processing import ManagedProjectItem
from .options import LinkStrategy


@dataclass
class Project:
    """Represents a project with its configuration and items.

    Attributes:
        name: The project name.
        directory: Absolute path to the project directory.
        items: List of items (files and directories) in the project.
    """

    name: str
    directory: Path
    items: list[ManagedProjectItem]

    @classmethod
    def from_directory(cls, name: str, directory: Path) -> "Project":
        """Create a Project instance from a directory.

        Scans the directory and creates ProjectItem instances for each
        file and subdirectory found.

        Args:
            name: The project name.
            directory: Path to the project directory.

        Returns:
            A new Project instance with items loaded from the directory.
        """
        items = []
        if directory.exists() and directory.is_dir():
            for item in directory.iterdir():
                items.append(
                    ManagedProjectItem(
                        name=item.name,
                        path=item,
                        strategy=LinkStrategy.SYMLINK,
                    )
                )
        return cls(name=name, directory=directory, items=items)

    @classmethod
    def from_subpaths(
        cls,
        name: str,
        directory: Path,
        subpaths: list[str],
        copy_paths: set[str] | None = None,
    ) -> "Project":
        """Create a Project instance from explicit subpaths.

        Instead of scanning the top-level directory, creates ProjectItem
        entries only for the specified subpaths.

        Args:
            name: The project name.
            directory: Path to the project directory.
            subpaths: List of relative paths within the project to link.
            copy_paths: Set of subpath names that should use physical copy.

        Returns:
            A new Project instance with items for each valid subpath.
        """
        copy_set = copy_paths or set()
        items = []
        for sp in subpaths:
            source = directory / sp
            if source.exists():
                strategy = LinkStrategy.COPY if sp in copy_set else LinkStrategy.SYMLINK
                if strategy == LinkStrategy.COPY and source.is_dir():
                    # Copy strategy is only supported for single files
                    raise ValueError(f"Copy strategy is not supported for directories: {sp}")
                items.append(
                    ManagedProjectItem(
                        name=sp,
                        path=source,
                        strategy=strategy,
                    )
                )
        return cls(name=name, directory=directory, items=items)

    def get_item_names(self) -> set[str]:
        """Get all item names in the project.

        Returns:
            A set of all item names.
        """
        return {item.name for item in self.items}
