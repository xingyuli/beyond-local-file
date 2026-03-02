"""Data models for representing projects and their items."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProjectItem:
    """Represents a single file or directory item in a project.

    Attributes:
        name: The name of the item.
        is_directory: True if the item is a directory, False if it's a file.
        source_path: Absolute path to the source item.
    """

    name: str
    is_directory: bool
    source_path: Path

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
    """

    name: str
    project_path: Path
    targets: list[Path]


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

    def get_item_names(self) -> set[str]:
        """Get all item names in the project.

        Returns:
            A set of all item names.
        """
        return {item.name for item in self.items}
