---
name: sync-project-rules
description: |
  [project] Syncs Qoder project_rules to other Agentic Tools by converting format as needed.
  Currently supports Trae CN (removes YAML frontmatter) and Kiro (preserves YAML frontmatter as Steering).
  Use when project_rules content changes, user requests "sync rules", "sync project rules",
  or mentions syncing/updating rules to other tools.
---

# Sync Project Rules

This skill synchronizes project rules from Qoder format to other Agentic Tools.

## Supported Tools

| Tool | Target Location | Format Conversion |
|------|-----------------|-------------------|
| Trae CN | `.trae/rules/project_rules.md` | Remove YAML frontmatter |
| Kiro | `.kiro/steering/project_rules.md` | Keep YAML frontmatter (as Steering config) |

## Format Difference

| Source | Format |
|--------|--------|
| Qoder (`.qoder/rules/project_rules.md`) | Markdown with YAML frontmatter |
| Trae CN (`.trae/rules/project_rules.md`) | Pure Markdown (no frontmatter) |
| Kiro (`.kiro/steering/project_rules.md`) | Markdown with YAML frontmatter (Steering format) |

## Execution Steps

### Step 1: Check Prerequisites

Before running the sync script, verify:
1. Target tool directory exists (e.g., `.trae` for Trae CN)
2. Source file exists at `.qoder/rules/project_rules.md`

```bash
# Check .trae directory
ls -la .trae/

# Check source file
ls -la .qoder/rules/project_rules.md
```

### Step 2: Run Sync Script

Execute the Python conversion script for the target tool:

**For Trae CN:**
```bash
uv run .qoder/skills/sync-project-rules/scripts/sync_rules_to_trae.py
```

**For Kiro:**
```bash
uv run .qoder/skills/sync-project-rules/scripts/sync_rules_to_kiro.py
```

### Step 3: Verify Result

After successful sync:

**For Trae CN:**
- Confirm target file exists: `.trae/rules/project_rules.md`
- Verify no YAML frontmatter (file should NOT start with `---`)
- Check Markdown content is preserved

**For Kiro:**
- Confirm target file exists: `.kiro/steering/project_rules.md`
- Verify YAML frontmatter exists (file should start with `---`)
- Check frontmatter contains `inclusion: always` (or existing config)
- Check Markdown content is preserved

## Exit Codes

| Code | Meaning | User Action |
|------|---------|-------------|
| 0 | Success | Sync completed |
| 1 | Target directory not found | Initialize target tool for this project |
| 2 | Source file not found | Create `.qoder/rules/project_rules.md` first |
| 3 | File read/write error | Check file permissions |

## Error Handling

### No Target Directory

If the project doesn't have the target tool directory, inform the user:

**For Trae CN:**
> "This project is not configured for Trae CN. Please initialize the .trae directory first."

**For Kiro:**
> "This project is not configured for Kiro. Please initialize the .kiro directory first."

### No Source File

If `.qoder/rules/project_rules.md` doesn't exist:
> "Qoder rules file not found. Please create .qoder/rules/project_rules.md before syncing."

### Permission Error

If file operations fail:
> "Unable to read/write files. Please check directory permissions."
