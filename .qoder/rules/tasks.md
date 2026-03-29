---
trigger: manual
alwaysApply: false
---

# Task Organization

All project tasks are tracked under `local-file/tasks/`.

## Structure

- `local-file/tasks/index.md` — Main task tracker with checkable TODO lists grouped by category.
- Each task has its own markdown file in the same directory, linked from the index.

## Categories

- Features — New functionality
- Bugs — Known issues to fix
- Usability — CLI UX and output improvements
- Documentation — Docs and README updates

## Conventions

- When adding a task: create a dedicated markdown file and add a linked checkbox entry in `index.md` under the appropriate category.
- When completing a task: mark the checkbox with `[x]` and append ✅ in `index.md`.
- Each task file should include: Description, Status, Category, and any relevant details (specification, examples, implementation notes).
- Exception: `advices.md` is a lightweight running log of non-blocking code review findings (🟡 Should Fix / 🔵 Consider). It does not follow the detailed task file format. Entries are grouped by date and written as checklist items. The code review hook appends to this file automatically.
