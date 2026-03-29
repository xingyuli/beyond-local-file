---
name: kiro-steering-to-qoder-rules
description: Convert Kiro Steering rules (.kiro/steering/*.md) to Qoder Rules (.qoder/rules/*.md). Use when the user asks to convert, migrate, or sync Kiro Steering rules to Qoder format, or mentions converting .kiro/steering/ files.
---

# Kiro Steering → Qoder Rules Conversion

Converts Kiro Steering rule files from `.kiro/steering/` directory to Qoder Rules format.

## Usage

Run the conversion script:

```bash
uv run .qoder/skills/kiro-steering-to-qoder-rules/scripts/convert.py
```

## Conversion Mapping

| Kiro inclusion | Qoder Trigger Type | Front-matter |
|----------------|-------------------|---------------|
| `always` | Always Apply | `trigger: always_on` |
| `auto` | Model Decision | `trigger: model_decision` + `description: ...` |
| `manual` | Apply Manually | `trigger: manual` + `alwaysApply: false` |
| `fileMatch` + `fileMatchPattern: pattern` | Specific Files | `trigger: glob` + `glob: pattern` |

## Key Features

1. **1-to-1 Conversion**: Each steering file is converted independently to a rule file
2. **Preserve Description**: The description field from `auto` rules is fully preserved
3. **Internal Reference Replacement**: `#[[file:xxx]]` is converted to standard Markdown links
4. **Overwrite Same Name**: Existing files with the same name in the target directory are overwritten

## Output

- Conversion results are written to `.qoder/rules/`
- A conversion summary is printed, listing the processing result of each file
