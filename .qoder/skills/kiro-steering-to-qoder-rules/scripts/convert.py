#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""
Kiro Steering → Qoder Rules Conversion Script

Converts .kiro/steering/*.md files to .qoder/rules/*.md format.

Usage:
    uv run .qoder/skills/kiro-steering-to-qoder-rules/scripts/convert.py
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import yaml


@dataclass
class SteeringFile:
    """Parsed Kiro Steering file"""
    filename: str
    inclusion: str
    name: Optional[str]
    description: Optional[str]
    file_match_pattern: Optional[str]
    body: str


@dataclass
class ConversionResult:
    """Conversion result"""
    source: str
    target: str
    rule_name: str
    trigger_type: str
    success: bool
    error: Optional[str] = None


def find_project_root() -> Path:
    """Find project root directory (directory containing .kiro)"""
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / ".kiro" / "steering").is_dir():
            return parent
    raise FileNotFoundError("Cannot find project root containing .kiro/steering directory")


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    Parse YAML front-matter and body content
    
    Returns:
        (front_matter_dict, body_content)
    """
    # Match YAML front-matter: ---\n...\n---
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


def parse_steering_file(filepath: Path) -> SteeringFile:
    """Parse a single Kiro Steering file"""
    content = filepath.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(content)
    
    # Get inclusion, default to always
    inclusion = frontmatter.get("inclusion", "always")
    
    # Get name, use filename (without extension) if not provided
    name = frontmatter.get("name")
    
    # Get description
    description = frontmatter.get("description")
    
    # Get fileMatchPattern (for inclusion: fileMatch)
    file_match_pattern = frontmatter.get("fileMatchPattern")
    
    return SteeringFile(
        filename=filepath.name,
        inclusion=inclusion,
        name=name,
        description=description,
        file_match_pattern=file_match_pattern,
        body=body
    )


def generate_qoder_frontmatter(steering: SteeringFile) -> str:
    """Generate Qoder front-matter based on Kiro inclusion"""
    inclusion = steering.inclusion.lower()
    
    if inclusion == "always":
        return "---\ntrigger: always_on\n---\n"
    
    elif inclusion == "auto":
        # auto rules need to preserve description fully
        if steering.description:
            # Use YAML serialization to ensure description format is correct
            fm = {"trigger": "model_decision", "description": steering.description}
            return "---\n" + yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False) + "---\n"
        else:
            return "---\ntrigger: model_decision\n---\n"
    
    elif inclusion == "manual":
        return "---\ntrigger: manual\nalwaysApply: false\n---\n"
    
    elif inclusion == "filematch":
        # fileMatch rules convert to glob
        if steering.file_match_pattern:
            fm = {"trigger": "glob", "glob": steering.file_match_pattern}
            return "---\n" + yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False) + "---\n"
        else:
            print(f"  Warning: fileMatch inclusion type missing fileMatchPattern, treating as always")
            return "---\ntrigger: always_on\n---\n"
    
    else:
        # Unknown type, default to always
        print(f"  Warning: Unknown inclusion type '{inclusion}', treating as always")
        return "---\ntrigger: always_on\n---\n"


def convert_internal_references(body: str) -> str:
    """
    Convert Kiro internal reference syntax to standard Markdown links
    
    #[[file:docs/11-module-package-spec.md]] -> [docs/11-module-package-spec.md](docs/11-module-package-spec.md)
    """
    pattern = r'#\[\[file:([^\]]+)\]\]'
    replacement = r'[\1](\1)'
    return re.sub(pattern, replacement, body)


def get_trigger_type_display(inclusion: str) -> str:
    """Get display name for trigger type"""
    mapping = {
        "always": "Always Apply",
        "auto": "Model Decision",
        "manual": "Apply Manually",
        "filematch": "Specific Files"
    }
    return mapping.get(inclusion.lower(), "Unknown")


def convert_file(steering: SteeringFile, target_dir: Path) -> ConversionResult:
    """Convert a single file and write to target directory"""
    # Determine rule name
    rule_name = steering.name if steering.name else steering.filename.replace(".md", "")

    # Generate Qoder front-matter
    qoder_frontmatter = generate_qoder_frontmatter(steering)

    # Convert internal references in body
    converted_body = convert_internal_references(steering.body)

    # Special rule: for local_file_structure.md, replace Kiro with Qoder (case-sensitive)
    if steering.filename == "local_file_structure.md":
        converted_body = converted_body.replace("Kiro", "Qoder")

    # Combine final content
    final_content = qoder_frontmatter + converted_body
    
    # Write to target file
    target_file = target_dir / steering.filename
    try:
        target_file.write_text(final_content, encoding="utf-8")
        return ConversionResult(
            source=steering.filename,
            target=steering.filename,
            rule_name=rule_name,
            trigger_type=get_trigger_type_display(steering.inclusion),
            success=True
        )
    except Exception as e:
        return ConversionResult(
            source=steering.filename,
            target=steering.filename,
            rule_name=rule_name,
            trigger_type=get_trigger_type_display(steering.inclusion),
            success=False,
            error=str(e)
        )


def main():
    """Main function"""
    print("=" * 60)
    print("Kiro Steering → Qoder Rules Conversion Tool")
    print("=" * 60)
    print()
    
    # Find project root directory
    try:
        project_root = find_project_root()
        print(f"Project root: {project_root}")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    # Source and target directories
    steering_dir = project_root / ".kiro" / "steering"
    rules_dir = project_root / ".qoder" / "rules"
    
    print(f"Source directory: {steering_dir}")
    print(f"Target directory: {rules_dir}")
    print()
    
    # Ensure target directory exists
    rules_dir.mkdir(parents=True, exist_ok=True)
    
    # Scan all .md files
    steering_files = sorted(steering_dir.glob("*.md"))
    
    if not steering_files:
        print("No .md files found")
        sys.exit(0)
    
    print(f"Found {len(steering_files)} steering files")
    print("-" * 60)
    print()
    
    # Convert all files
    results: list[ConversionResult] = []
    
    for filepath in steering_files:
        print(f"Processing: {filepath.name}")
        
        # Parse source file
        steering = parse_steering_file(filepath)
        print(f"  inclusion: {steering.inclusion}")
        print(f"  name (front-matter): {steering.name or '(none)'}")
        
        # Convert and write
        result = convert_file(steering, rules_dir)
        results.append(result)
        
        if result.success:
            print(f"  → Written: {result.target}")
            print(f"  → Rule name: {result.rule_name}")
            print(f"  → Trigger type: {result.trigger_type}")
        else:
            print(f"  ✗ Conversion failed: {result.error}")
        
        print()
    
    # Output conversion summary
    print("=" * 60)
    print("Conversion Summary")
    print("=" * 60)
    print()
    
    success_count = sum(1 for r in results if r.success)
    fail_count = len(results) - success_count
    
    print(f"Total: {len(results)} files")
    print(f"Success: {success_count}")
    print(f"Failed: {fail_count}")
    print()
    
    # Detailed list
    print("| Source | Target | Rule Name | Trigger Type | Status |")
    print("|--------|--------|-----------|--------------|--------|")
    for r in results:
        status = "✓" if r.success else f"✗ {r.error}"
        print(f"| {r.source} | {r.target} | {r.rule_name} | {r.trigger_type} | {status} |")
    
    print()
    print("Conversion complete!")
    
    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
