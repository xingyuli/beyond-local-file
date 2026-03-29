#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""
Qoder Rules → Kiro Steering Conversion Script

Converts .qoder/rules/*.md files to .kiro/steering/*.md format.

Usage:
    uv run .qoder/skills/qoder-rules-to-kiro-steering/scripts/convert.py
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import yaml


@dataclass
class RuleFile:
    """Parsed Qoder Rule file"""
    filename: str
    trigger: str
    description: Optional[str]
    glob_pattern: Optional[str]
    body: str


@dataclass
class ConversionResult:
    """Conversion result"""
    source: str
    target: str
    inclusion_type: str
    success: bool
    error: Optional[str] = None


def find_project_root() -> Path:
    """Find project root directory (directory containing .qoder)"""
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / ".qoder" / "rules").is_dir():
            return parent
    raise FileNotFoundError("Cannot find project root containing .qoder/rules directory")


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


def parse_rule_file(filepath: Path) -> RuleFile:
    """Parse a single Qoder Rule file"""
    content = filepath.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(content)
    
    # Get trigger, default to always_on
    trigger = frontmatter.get("trigger", "always_on")
    
    # Get description
    description = frontmatter.get("description")
    
    # Get glob pattern (for trigger: glob)
    glob_pattern = frontmatter.get("glob")
    
    return RuleFile(
        filename=filepath.name,
        trigger=trigger,
        description=description,
        glob_pattern=glob_pattern,
        body=body
    )


def generate_kiro_frontmatter(rule: RuleFile) -> str:
    """Generate Kiro front-matter based on Qoder trigger"""
    trigger = rule.trigger.lower()
    
    if trigger == "always_on":
        return "---\ninclusion: always\n---\n"
    
    elif trigger == "model_decision":
        # model_decision rules need to preserve description fully
        if rule.description:
            # Use YAML serialization to ensure description format is correct
            fm = {"inclusion": "auto", "description": rule.description}
            return "---\n" + yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False) + "---\n"
        else:
            return "---\ninclusion: auto\n---\n"
    
    elif trigger == "manual":
        return "---\ninclusion: manual\n---\n"
    
    elif trigger == "glob":
        # glob rules convert to fileMatch
        if rule.glob_pattern:
            # Manually construct YAML to ensure fileMatchPattern value is wrapped in double quotes
            return f"---\ninclusion: fileMatch\nfileMatchPattern: \"{rule.glob_pattern}\"\n---\n"
        else:
            print(f"  Warning: glob trigger type missing glob pattern, treating as always")
            return "---\ninclusion: always\n---\n"
    
    else:
        # Unknown type, default to always
        print(f"  Warning: Unknown trigger type '{trigger}', treating as always")
        return "---\ninclusion: always\n---\n"


def convert_internal_references(body: str) -> str:
    """
    Convert standard Markdown links to Kiro internal reference syntax
    
    [docs/11-module-package-spec.md](docs/11-module-package-spec.md) -> #[[file:docs/11-module-package-spec.md]]
    
    Only converts Markdown links where link text and URL are identical (indicating file references)
    """
    # Match [path](path) format where link text and URL are the same
    pattern = r'\[([^\]]+)\]\(\1\)'
    replacement = r'#[[file:\1]]'
    return re.sub(pattern, replacement, body)


def get_inclusion_type_display(trigger: str) -> str:
    """Get display name for inclusion type"""
    mapping = {
        "always_on": "Always Include",
        "model_decision": "Auto Include",
        "manual": "Manual Include",
        "glob": "File Match"
    }
    return mapping.get(trigger.lower(), "Unknown")


def convert_file(rule: RuleFile, target_dir: Path) -> ConversionResult:
    """Convert a single file and write to target directory"""
    # Generate Kiro front-matter
    kiro_frontmatter = generate_kiro_frontmatter(rule)

    # Convert internal references in body
    converted_body = convert_internal_references(rule.body)

    # Special rule: for local_file_structure.md, replace Qoder with Kiro (case-sensitive)
    if rule.filename == "local_file_structure.md":
        converted_body = converted_body.replace("Qoder", "Kiro")

    # Combine final content
    final_content = kiro_frontmatter + converted_body
    
    # Write to target file
    target_file = target_dir / rule.filename
    try:
        target_file.write_text(final_content, encoding="utf-8")
        return ConversionResult(
            source=rule.filename,
            target=rule.filename,
            inclusion_type=get_inclusion_type_display(rule.trigger),
            success=True
        )
    except Exception as e:
        return ConversionResult(
            source=rule.filename,
            target=rule.filename,
            inclusion_type=get_inclusion_type_display(rule.trigger),
            success=False,
            error=str(e)
        )


def main():
    """Main function"""
    print("=" * 60)
    print("Qoder Rules → Kiro Steering Conversion Tool")
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
    rules_dir = project_root / ".qoder" / "rules"
    steering_dir = project_root / ".kiro" / "steering"
    
    print(f"Source directory: {rules_dir}")
    print(f"Target directory: {steering_dir}")
    print()
    
    # Ensure target directory exists
    steering_dir.mkdir(parents=True, exist_ok=True)
    
    # Scan all .md files
    rule_files = sorted(rules_dir.glob("*.md"))
    
    if not rule_files:
        print("No .md files found")
        sys.exit(0)
    
    print(f"Found {len(rule_files)} rule files")
    print("-" * 60)
    print()
    
    # Convert all files
    results: list[ConversionResult] = []
    
    for filepath in rule_files:
        print(f"Processing: {filepath.name}")
        
        # Parse source file
        rule = parse_rule_file(filepath)
        print(f"  trigger: {rule.trigger}")
        
        # Convert and write
        result = convert_file(rule, steering_dir)
        results.append(result)
        
        if result.success:
            print(f"  → Written: {result.target}")
            print(f"  → Inclusion type: {result.inclusion_type}")
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
    print("| Source | Target | Inclusion Type | Status |")
    print("|--------|--------|----------------|--------|")
    for r in results:
        status = "✓" if r.success else f"✗ {r.error}"
        print(f"| {r.source} | {r.target} | {r.inclusion_type} | {status} |")
    
    print()
    print("Conversion complete!")
    
    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
