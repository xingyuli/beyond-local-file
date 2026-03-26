"""Data models for representing projects and their items."""

from dataclasses import dataclass
from pathlib import Path

from .options import LinkStrategy


@dataclass
class ProjectItem:
    """Represents a single file or directory item in a project.

    Attributes:
        name: The name of the item.
        is_directory: True if the item is a directory, False if it's a file.
        source_path: Absolute path to the source item.
        strategy: How this item should be linked — symlink (default) or copy.
    """

    name: str
    is_directory: bool
    source_path: Path
    strategy: LinkStrategy = LinkStrategy.SYMLINK

    def link_path(self, target_dir: Path) -> Path:
        """Get the path where the symlink should be created in target directory.

        Args:
            target_dir: The target directory where symlinks are created.

        Returns:
            Path where the symlink will be created.
        """
        return target_dir / self.name


@dataclass
class ProjectConfiguration:
    """Represents the configuration for a single project.

    This model encapsulates the project's source directory and its target
    deployment locations, providing a clear alternative to nested dictionaries.

    Attributes:
        name: The project name.
        project_path: Absolute path to the project's source directory.
        targets: List of absolute paths where symlinks should be created.
        subpaths: Optional list of relative subpaths to link instead of top-level items.
        copy_paths: Set of subpath names that should use physical copy instead of symlink.
    """

    name: str
    project_path: Path
    targets: list[Path]
    subpaths: list[str] | None = None
    copy_paths: set[str] | None = None


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
    items: list[ProjectItem]

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
                items.append(ProjectItem(name=item.name, is_directory=item.is_dir(), source_path=item))
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
                items.append(ProjectItem(name=sp, is_directory=source.is_dir(), source_path=source, strategy=strategy))
        return cls(name=name, directory=directory, items=items)

    def get_item_names(self) -> set[str]:
        """Get all item names in the project.

        Returns:
            A set of all item names.
        """
        return {item.name for item in self.items}
