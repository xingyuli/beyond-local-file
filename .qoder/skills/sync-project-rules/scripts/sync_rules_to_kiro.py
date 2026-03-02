#!/usr/bin/env python3
"""
Sync Qoder project_rules to Kiro Steering format.

On the Kiro side, rules are called Steering. This script appends Qoder's rule content to Kiro's steering file,
preserving YAML frontmatter and ensuring proper formatting of rule content.
"""

import re
import sys
from pathlib import Path


def extract_frontmatter(content: str) -> tuple[str, str]:
    """
    Extract YAML frontmatter and body from content.

    Args:
        content: Original file content

    Returns:
        Tuple containing (frontmatter, body), frontmatter includes --- separators
    """
    pattern = r"^(---\n.*?\n---\n)(.*)"
    match = re.match(pattern, content, flags=re.DOTALL)
    if match:
        return match.group(1), match.group(2).lstrip("\n")
    return "", content


def sync_rules(project_dir: Path) -> int:
    """
    Sync project rules from Qoder to Kiro Steering format.

    Args:
        project_dir: Project root directory

    Returns:
        Exit code: 0=success, 1=.kiro directory not found, 2=source file not found, 3=IO error
    """
    kiro_dir = project_dir / ".kiro"
    source_file = project_dir / ".qoder" / "rules" / "project_rules.md"
    target_dir = kiro_dir / "steering"
    target_file = target_dir / "project_rules.md"

    # Check if .kiro directory exists
    if not kiro_dir.exists():
        print(f"Error: .kiro directory not found: {project_dir}", file=sys.stderr)
        print("This project is not configured with Kiro.", file=sys.stderr)
        return 1

    # Check if source file exists
    if not source_file.exists():
        print(f"Error: Source file not found: {source_file}", file=sys.stderr)
        print("Please create .qoder/rules/project_rules.md first.", file=sys.stderr)
        return 2

    try:
        # Read source file content
        source_content = source_file.read_text(encoding="utf-8")

        # Extract frontmatter and body
        frontmatter, body = extract_frontmatter(source_content)

        # If target file exists, read its frontmatter
        if target_file.exists():
            target_content = target_file.read_text(encoding="utf-8")
            existing_frontmatter, _ = extract_frontmatter(target_content)
            # Use target file's frontmatter (preserve Kiro configuration)
            if existing_frontmatter:
                frontmatter = existing_frontmatter

        # If no frontmatter, use default Kiro steering frontmatter
        if not frontmatter:
            frontmatter = "---\ninclusion: always\n---\n"

        # Combine final content
        converted = frontmatter + body

        # Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)

        # Write to target file
        target_file.write_text(converted, encoding="utf-8")

        print(f"Successfully synced project_rules to {target_file}")
        return 0

    except OSError as e:
        print(f"Error: File read/write failed: {e}", file=sys.stderr)
        return 3


def main():
    """Main function: Parse command line arguments and execute sync operation."""
    # Use current working directory or provided argument
    if len(sys.argv) > 1:
        project_dir = Path(sys.argv[1]).resolve()
    else:
        project_dir = Path.cwd()

    sys.exit(sync_rules(project_dir))


if __name__ == "__main__":
    main()
