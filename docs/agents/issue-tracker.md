# Issue Tracker

Work items for this repo are tracked as local markdown files — not in GitHub Issues.

## Location

All tasks live under `local-file/tasks/`, organized into two groups:

- `local-file/tasks/manual/` — user-created tasks (features, bugs, usability, docs, code quality)
- `local-file/tasks/auto-review/` — auto-generated code review findings

## Reading issues

- Browse `local-file/tasks/manual/index.md` for the main task list
- Browse `local-file/tasks/auto-review/index.md` for review findings
- Read individual `*.md` files for full task detail

## Writing issues

To create a new task:
1. Create `local-file/tasks/manual/{verb}-{slug}.md` following the format in `local-file/agentic/specs/task-definition-spec.md`
2. Add a checkbox entry to `local-file/tasks/manual/index.md` under the appropriate category

For one-sentence review findings, append to `local-file/tasks/auto-review/simple_advices.md`.

## Completing issues

Update the task file's `Status` to `Completed`, mark `[x]` in the index, and add `— Completed: YYYY-MM-DD`.

## Format reference

See `local-file/agentic/specs/task-definition-spec.md` for the full task definition spec.
