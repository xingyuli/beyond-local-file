#!/usr/bin/env python3
"""
Sync Qoder project_rules to Trae CN format.

Converts Qoder rules (with YAML frontmatter) to Trae CN format (pure Markdown).
"""

import re
import sys
from pathlib import Path


def remove_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from Markdown content."""
    pattern = r"^---\n.*?\n---\n*"
    return re.sub(pattern, "", content, flags=re.DOTALL).lstrip("\n")


def sync_rules(project_dir: Path) -> int:
    """
    Sync project_rules from Qoder to Trae format.

    Args:
        project_dir: Project root directory

    Returns:
        Exit code: 0=success, 1=no .trae dir, 2=no source file, 3=IO error
    """
    trae_dir = project_dir / ".trae"
    source_file = project_dir / ".qoder" / "rules" / "project_rules.md"
    target_dir = trae_dir / "rules"
    target_file = target_dir / "project_rules.md"

    # Check .trae directory exists
    if not trae_dir.exists():
        print(f"Error: .trae directory not found in {project_dir}", file=sys.stderr)
        print("This project is not configured for Trae CN.", file=sys.stderr)
        return 1

    # Check source file exists
    if not source_file.exists():
        print(f"Error: Source file not found: {source_file}", file=sys.stderr)
        print("Please create .qoder/rules/project_rules.md first.", file=sys.stderr)
        return 2

    try:
        # Read source content
        content = source_file.read_text(encoding="utf-8")

        # Remove frontmatter
        converted = remove_frontmatter(content)

        # Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)

        # Write target file
        target_file.write_text(converted, encoding="utf-8")

        print(f"Successfully synced project_rules to {target_file}")
        return 0

    except OSError as e:
        print(f"Error: Failed to read/write files: {e}", file=sys.stderr)
        return 3


def main():
    # Use current working directory or provided argument
    if len(sys.argv) > 1:
        project_dir = Path(sys.argv[1]).resolve()
    else:
        project_dir = Path.cwd()

    sys.exit(sync_rules(project_dir))


if __name__ == "__main__":
    main()
