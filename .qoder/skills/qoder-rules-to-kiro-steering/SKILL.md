---
name: qoder-rules-to-kiro-steering
description: Convert Qoder Rules (.qoder/rules/*.md) to Kiro Steering format (.kiro/steering/*.md). Use when the user asks to convert, migrate, or sync Qoder Rules to Kiro format, or mentions converting .qoder/rules/ files.
---

# Qoder Rules → Kiro Steering Conversion

Converts Qoder Rules files from `.qoder/rules/` directory to Kiro Steering format.

## Usage

Run the conversion script:

```bash
uv run .qoder/skills/qoder-rules-to-kiro-steering/scripts/convert.py
```

## Conversion Mapping

| Qoder Trigger Type | Kiro inclusion | Front-matter |
|-------------------|----------------|---------------|
| `trigger: always_on` | Always Include | `inclusion: always` |
| `trigger: model_decision` | Auto Include | `inclusion: auto` + `description: ...` |
| `trigger: manual` | Manual Include | `inclusion: manual` |
| `trigger: glob` + `glob: pattern` | Specific Files | `inclusion: fileMatch` + `fileMatchPattern: pattern` |

## Key Features

1. **1-to-1 Conversion**: Each rule file is converted independently to a steering file
2. **Preserve Description**: The description field from `model_decision` rules is fully preserved
3. **Internal Reference Replacement**: Standard Markdown links are converted to `#[[file:xxx]]` format
4. **Overwrite Same Name**: Existing files with the same name in the target directory are overwritten

## Output

- Conversion results are written to `.kiro/steering/`
- A conversion summary is printed, listing the processing result of each file
