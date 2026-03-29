---
name: sync-kiro-qoder-rules
description: Bidirectional sync between Kiro Steering (.kiro/steering/*.md) and Qoder Rules (.qoder/rules/*.md). Recognizes sync direction from user prompt, or asks for clarification when ambiguous. Use when user mentions syncing, converting, or migrating rules between Kiro and Qoder formats.
---

# Kiro Steering ↔ Qoder Rules Sync

Bidirectional synchronization tool that converts rules between Kiro Steering format (`.kiro/steering/`) and Qoder Rules format (`.qoder/rules/`).

## Direction Recognition from User Prompt

Before running the script, you MUST determine the sync direction from the user's request.

### Kiro → Qoder Direction

Recognize this direction when the user mentions:
- "sync kiro to qoder", "kiro → qoder", "kiro steering to qoder rules"
- "convert steering to rules", "migrate from kiro"
- "update qoder rules from kiro", "sync steering files"
- References to `.kiro/steering/` as the source

### Qoder → Kiro Direction

Recognize this direction when the user mentions:
- "sync qoder to kiro", "qoder → kiro", "qoder rules to kiro steering"
- "convert rules to steering", "migrate to kiro"
- "update kiro steering from qoder", "sync rules files"
- References to `.qoder/rules/` as the source

### Ambiguous - Ask User

If the user's prompt is ambiguous (e.g., just "sync rules" without direction), you MUST ask:

> Which direction should I sync?
> 1. Kiro Steering → Qoder Rules
> 2. Qoder Rules → Kiro Steering

## Usage

Once direction is determined, run with the `--direction` flag:

```bash
# Kiro → Qoder
uv run .qoder/skills/sync-kiro-qoder-rules/scripts/convert.py --direction kiro-to-qoder

# Qoder → Kiro  
uv run .qoder/skills/sync-kiro-qoder-rules/scripts/convert.py --direction qoder-to-kiro
```

## Conversion Mapping

### Kiro → Qoder

| Kiro inclusion | Qoder Trigger Type | Front-matter |
|----------------|-------------------|---------------|
| `always` | Always Apply | `trigger: always_on` |
| `auto` | Model Decision | `trigger: model_decision` + `description: ...` |
| `manual` | Apply Manually | `trigger: manual` + `alwaysApply: false` |
| `fileMatch` + `fileMatchPattern: pattern` | Specific Files | `trigger: glob` + `glob: pattern` |

### Qoder → Kiro

| Qoder Trigger Type | Kiro inclusion | Front-matter |
|-------------------|----------------|---------------|
| `trigger: always_on` | Always Include | `inclusion: always` |
| `trigger: model_decision` | Auto Include | `inclusion: auto` + `description: ...` |
| `trigger: manual` | Manual Include | `inclusion: manual` |
| `trigger: glob` + `glob: pattern` | Specific Files | `inclusion: fileMatch` + `fileMatchPattern: pattern` |

## Key Features

1. **Auto Direction Detection**: Automatically determines sync direction based on file timestamps
2. **1-to-1 Conversion**: Each file is converted independently
3. **Preserve Description**: Description fields are fully preserved in both directions
4. **Internal Reference Conversion**: 
   - Kiro `#[[file:xxx]]` ↔ Qoder Markdown links `[xxx](xxx)`
5. **Special Handling**: `local_file_structure.md` has tool name replacement (Kiro ↔ Qoder)
6. **Overwrite Same Name**: Existing files with the same name in target directory are overwritten

## Output

- Conversion results are written to the appropriate target directory
- A conversion summary is printed, listing the processing result of each file
- Direction used is clearly displayed at the start of conversion
