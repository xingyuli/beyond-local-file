#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""
Kiro Steering ↔ Qoder Rules Bidirectional Sync Script

Converts rules between Kiro Steering and Qoder Rules formats.
Direction MUST be specified via --direction flag.

Usage:
    uv run .qoder/skills/sync-kiro-qoder-rules/scripts/convert.py --direction kiro-to-qoder
    uv run .qoder/skills/sync-kiro-qoder-rules/scripts/convert.py --direction qoder-to-kiro
"""

import argparse
import re
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml


class SyncDirection(StrEnum):
    """Sync direction options"""
    KIRO_TO_QODER = "kiro-to-qoder"
    QODER_TO_KIRO = "qoder-to-kiro"


@dataclass
class ParsedFile:
    """Parsed rule/steering file"""
    filename: str
    frontmatter: dict
    body: str


@dataclass
class ConversionResult:
    """Conversion result"""
    source: str
    target: str
    type_info: str
    success: bool
    error: str | None = None


def find_project_root() -> Path:
    """Find project root directory (directory containing .kiro or .qoder)"""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / ".kiro").is_dir() or (parent / ".qoder").is_dir():
            return parent
    raise FileNotFoundError("Cannot find project root containing .kiro or .qoder directory")


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    Parse YAML front-matter and body content

    Returns:
        (front_matter_dict, body_content)
    """
    pattern = r'^---\s*\n(.*?)\n---\n'
    match = re.match(pattern, content, re.DOTALL)

    if match:
        frontmatter_str = match.group(1)
        body = content[match.end():]
        try:
            frontmatter = yaml.safe_load(frontmatter_str) or {}
        except yaml.YAMLError:
            frontmatter = {}
        return frontmatter, body

    return {}, content


def parse_file(filepath: Path) -> ParsedFile:
    """Parse a single file"""
    content = filepath.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(content)
    return ParsedFile(filename=filepath.name, frontmatter=frontmatter, body=body)


# ========== Kiro → Qoder Conversion ==========

def convert_kiro_internal_refs(body: str) -> str:
    """Convert #[[file:xxx]] to [xxx](xxx)"""
    pattern = r'#\[\[file:([^\]]+)\]\]'
    replacement = r'[\1](\1)'
    return re.sub(pattern, replacement, body)


def generate_qoder_frontmatter(fm: dict) -> str:  # noqa: PLR0911
    """Generate Qoder front-matter from Kiro front-matter"""
    inclusion = fm.get("inclusion", "always").lower()

    if inclusion == "always":
        return "---\ntrigger: always_on\n---\n"

    elif inclusion == "auto":
        description = fm.get("description")
        if description:
            result = {"trigger": "model_decision", "description": description}
            return "---\n" + yaml.dump(result, allow_unicode=True, default_flow_style=False, sort_keys=False) + "---\n"
        else:
            return "---\ntrigger: model_decision\n---\n"

    elif inclusion == "manual":
        return "---\ntrigger: manual\nalwaysApply: false\n---\n"

    elif inclusion == "filematch":
        pattern = fm.get("fileMatchPattern")
        if pattern:
            result = {"trigger": "glob", "glob": pattern}
            return "---\n" + yaml.dump(result, allow_unicode=True, default_flow_style=False, sort_keys=False) + "---\n"
        else:
            print("  Warning: fileMatch missing fileMatchPattern, treating as always")
            return "---\ntrigger: always_on\n---\n"

    else:
        print(f"  Warning: Unknown inclusion type '{inclusion}', treating as always")
        return "---\ntrigger: always_on\n---\n"


def convert_kiro_to_qoder(parsed: ParsedFile, target_dir: Path) -> ConversionResult:
    """Convert Kiro steering file to Qoder rule"""
    qoder_fm = generate_qoder_frontmatter(parsed.frontmatter)
    converted_body = convert_kiro_internal_refs(parsed.body)

    # Special handling for local_file_structure.md
    if parsed.filename == "local_file_structure.md":
        converted_body = converted_body.replace("Kiro", "Qoder")

    final_content = qoder_fm + converted_body
    target_file = target_dir / parsed.filename

    inclusion = parsed.frontmatter.get("inclusion", "always")
    type_info = f"inclusion:{inclusion} → trigger"

    try:
        target_file.write_text(final_content, encoding="utf-8")
        return ConversionResult(parsed.filename, parsed.filename, type_info, True)
    except Exception as e:
        return ConversionResult(parsed.filename, parsed.filename, type_info, False, str(e))


# ========== Qoder → Kiro Conversion ==========

def convert_qoder_internal_refs(body: str) -> str:
    """Convert [path](path) to #[[file:path]]"""
    pattern = r'\[([^\]]+)\]\(\1\)'
    replacement = r'#[[file:\1]]'
    return re.sub(pattern, replacement, body)


def generate_kiro_frontmatter(fm: dict) -> str:  # noqa: PLR0911
    """Generate Kiro front-matter from Qoder front-matter"""
    trigger = fm.get("trigger", "always_on").lower()

    if trigger == "always_on":
        return "---\ninclusion: always\n---\n"

    elif trigger == "model_decision":
        description = fm.get("description")
        if description:
            result = {"inclusion": "auto", "description": description}
            return "---\n" + yaml.dump(result, allow_unicode=True, default_flow_style=False, sort_keys=False) + "---\n"
        else:
            return "---\ninclusion: auto\n---\n"

    elif trigger == "manual":
        return "---\ninclusion: manual\n---\n"

    elif trigger == "glob":
        pattern = fm.get("glob")
        if pattern:
            return f'---\ninclusion: fileMatch\nfileMatchPattern: "{pattern}"\n---\n'
        else:
            print("  Warning: glob trigger missing glob pattern, treating as always")
            return "---\ninclusion: always\n---\n"

    else:
        print(f"  Warning: Unknown trigger type '{trigger}', treating as always")
        return "---\ninclusion: always\n---\n"


def convert_qoder_to_kiro(parsed: ParsedFile, target_dir: Path) -> ConversionResult:
    """Convert Qoder rule file to Kiro steering"""
    kiro_fm = generate_kiro_frontmatter(parsed.frontmatter)
    converted_body = convert_qoder_internal_refs(parsed.body)

    # Special handling for local_file_structure.md
    if parsed.filename == "local_file_structure.md":
        converted_body = converted_body.replace("Qoder", "Kiro")

    final_content = kiro_fm + converted_body
    target_file = target_dir / parsed.filename

    trigger = parsed.frontmatter.get("trigger", "always_on")
    type_info = f"trigger:{trigger} → inclusion"

    try:
        target_file.write_text(final_content, encoding="utf-8")
        return ConversionResult(parsed.filename, parsed.filename, type_info, True)
    except Exception as e:
        return ConversionResult(parsed.filename, parsed.filename, type_info, False, str(e))


# ========== Main ==========

def main():  # noqa: PLR0915
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Bidirectional sync between Kiro Steering and Qoder Rules"
    )
    parser.add_argument(
        "--direction",
        "-d",
        type=str,
        choices=[d.value for d in SyncDirection],
        required=True,
        help="Sync direction (required): kiro-to-qoder or qoder-to-kiro",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Kiro Steering ↔ Qoder Rules Sync Tool")
    print("=" * 60)
    print()

    # Find project root
    try:
        project_root = find_project_root()
        print(f"Project root: {project_root}")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    kiro_dir = project_root / ".kiro" / "steering"
    qoder_dir = project_root / ".qoder" / "rules"

    print(f"Kiro Steering: {kiro_dir}")
    print(f"Qoder Rules:   {qoder_dir}")
    print()

    # Use specified direction
    direction = SyncDirection(args.direction)
    print(f"Direction: {direction.value}")
    print()

    # Set source and target based on direction
    if direction == SyncDirection.KIRO_TO_QODER:
        source_dir = kiro_dir
        target_dir = qoder_dir
        convert_func = convert_kiro_to_qoder
        print("Converting: Kiro Steering → Qoder Rules")
    else:
        source_dir = qoder_dir
        target_dir = kiro_dir
        convert_func = convert_qoder_to_kiro
        print("Converting: Qoder Rules → Kiro Steering")

    print("-" * 60)
    print()

    # Check source directory
    if not source_dir.is_dir():
        print(f"Error: Source directory does not exist: {source_dir}")
        sys.exit(1)

    # Ensure target directory exists
    target_dir.mkdir(parents=True, exist_ok=True)

    # Scan source files
    source_files = sorted(source_dir.glob("*.md"))

    if not source_files:
        print("No .md files found in source directory")
        sys.exit(0)

    print(f"Found {len(source_files)} files to convert")
    print()

    # Convert all files
    results: list[ConversionResult] = []

    for filepath in source_files:
        print(f"Processing: {filepath.name}")

        parsed = parse_file(filepath)
        result = convert_func(parsed, target_dir)
        results.append(result)

        if result.success:
            print(f"  → Written: {result.target}")
            print(f"  → {result.type_info}")
        else:
            print(f"  ✗ Failed: {result.error}")

        print()

    # Summary
    print("=" * 60)
    print("Conversion Summary")
    print("=" * 60)
    print()

    success_count = sum(1 for r in results if r.success)
    fail_count = len(results) - success_count

    print(f"Direction: {direction.value}")
    print(f"Total: {len(results)} files")
    print(f"Success: {success_count}")
    print(f"Failed: {fail_count}")
    print()

    print("| Source | Target | Type | Status |")
    print("|--------|--------|------|--------|")
    for r in results:
        status = "✓" if r.success else f"✗ {r.error}"
        print(f"| {r.source} | {r.target} | {r.type_info} | {status} |")

    print()
    print("Sync complete!")

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
