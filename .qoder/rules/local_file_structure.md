---
trigger: always_on
---

# local-file/agentic Directory Convention

This file defines the storage specification for Kiro-generated content.

## Directory Structure

```
local-file/agentic/
├── analysis/    # Technical analysis reports (timestamped, flat structure)
├── drafts/      # Design proposals, document drafts (timestamped, flat structure)
├── summaries/   # Task completion summaries (timestamped, flat structure)
└── specs/       # Formal specification files (no timestamps, flat structure)
```

## Naming Conventions

All files in `analysis/`, `drafts/`, and `summaries/` MUST use `YYYYMMDD-HH-` prefix for chronological ordering.

Format: `YYYYMMDD-HH-descriptive-title.md`

Examples:
- `20260326-18-codebase-structure-for-copy-feature.md`
- `20260402-23-architecture-refactoring-comparison.md`
- `20260404-00-task-tracking-system-complete-redesign.md`

Files in `specs/` do NOT use timestamps (specs are timeless reference documents).

## Directory Usage

| Path | When to Write | Naming | Structure |
|------|---------------|--------|-----------|
| `agentic/analysis/` | Technical analysis, codebase exploration, investigation | `YYYYMMDD-HH-title.md` | Flat (no subdirs) |
| `agentic/drafts/` | Design proposals, document drafts, informal plans | `YYYYMMDD-HH-title.md` | Flat (no subdirs) |
| `agentic/summaries/` | Task completion summaries, work completion reports | `YYYYMMDD-HH-title.md` | Flat (no subdirs) |
| `agentic/specs/` | Formal specifications, API specs, format definitions | `name-spec.md` | Flat (no subdirs) |

## Rules

1. All files in `analysis/`, `drafts/`, `summaries/` MUST have `YYYYMMDD-HH-` prefix
2. All directories MUST be flat - NO subdirectories allowed
3. Files in `specs/` do NOT use timestamp prefix
4. Do NOT scatter files in `local-file/agentic/` root directory
5. Use descriptive titles that clearly indicate content

## Archival

During release preparation, all timestamped files between releases will be moved to:
```
local-file/tasks/releases/${VERSION}/worklog/
├── analysis/
├── drafts/
└── summaries/
```

This keeps the working directories clean and provides a historical record of work done in each release.
