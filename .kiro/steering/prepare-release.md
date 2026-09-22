---
inclusion: manual
description: "Archives completed tasks, generates CHANGELOG entries, and cleans up task indices for the next release"
---

You are preparing a new release for the `beyond-local-file` project. Follow these steps:

## Step 1: Determine Release Version

1. Get the latest git tag: `git describe --tags --abbrev=0`
2. Ask the user what the next version number should be (e.g., v0.2.0)
3. Store this as `NEW_VERSION`
4. Get the date of the last release tag: `git log -1 --format=%ai [last-tag]`
5. Store this as `LAST_RELEASE_DATE`

## Step 2: Validate All Tests Pass

1. Run the full test suite: `uv run pytest`
2. If any tests fail:
   - Report the failures to the user
   - STOP the release preparation process immediately
   - Inform the user they must fix all test failures before proceeding with the release
   - Do NOT continue to subsequent steps
3. Only continue to Step 3 if all tests pass successfully

## Step 3: Identify Completed Tasks

1. Read `local-file/tasks/manual/index.md`
2. Extract all lines marked with `[x]` (completed tasks)
3. For each completed task:
   - Extract the task file name from the markdown link
   - Read the full task file from `local-file/tasks/manual/[task-name].md`
   - Extract from the header: Category, Description
   - Extract from sections: Motivation, Expected Behavior
   - Use these to write clear, user-facing changelog entries

## Step 4: Identify Agentic Worklog Files to Archive

1. Find all timestamped files in `local-file/agentic/analysis/`, `local-file/agentic/drafts/`, and `local-file/agentic/summaries/`
2. For each file with `YYYYMMDD-HH-` prefix:
   - Parse the timestamp from the filename
   - If the timestamp is >= `LAST_RELEASE_DATE` and < current date, mark for archival
3. Store the list of files to archive

## Step 5: Generate CHANGELOG

Create `local-file/tasks/releases/${NEW_VERSION}/CHANGELOG.md` with this structure:

```markdown
# Release ${NEW_VERSION}

Release Date: [YYYY-MM-DD]

## Features
- [Feature title] — Brief description from task

## Bug Fixes
- [Bug title] — Brief description from task

## Usability
- [Usability improvement] — Brief description from task

## Documentation
- [Doc update] — Brief description from task

## Code Quality
- [Refactoring] — Brief description from task
```

Only include categories that have completed tasks. Use the task descriptions and motivation to write clear, user-facing changelog entries.

## Step 6: Archive Completed Tasks

1. Create directories:
   - `local-file/tasks/releases/${NEW_VERSION}/tasks/manual/`
   - `local-file/tasks/releases/${NEW_VERSION}/tasks/auto-review/` (always create — needed for simple_advices)
2. For each completed manual task file:
   - Copy the file from `local-file/tasks/manual/[task-name].md` to `local-file/tasks/releases/${NEW_VERSION}/tasks/manual/[task-name].md`
   - Delete the original from `local-file/tasks/manual/`
3. For each completed auto-review detailed task (if any):
   - Copy the file from `local-file/tasks/auto-review/[task-name].md` to `local-file/tasks/releases/${NEW_VERSION}/tasks/auto-review/[task-name].md`
   - Delete the original from `local-file/tasks/auto-review/`
4. Archive completed items from `local-file/tasks/auto-review/simple_advices.md`:
   - Read the file and collect all `[x]` items, preserving their date-group headings
   - Create `local-file/tasks/releases/${NEW_VERSION}/tasks/auto-review/simple_advices.md` with a header:
     ```markdown
     # Code Review Advices — Archived (${NEW_VERSION})

     Resolved items from `local-file/tasks/auto-review/simple_advices.md`,
     archived to ${NEW_VERSION} release on [YYYY-MM-DD].
     ```
   - Append each date-group that contains at least one `[x]` item (include only the `[x]` lines, not `[ ]` lines)
   - Rewrite the live `simple_advices.md` keeping only `[ ]` items (preserve date-group headings that still have open items; remove headings whose entire group was completed)

## Step 7: Archive Agentic Worklog Files

1. Create directories:
   - `local-file/tasks/releases/${NEW_VERSION}/worklog/analysis/`
   - `local-file/tasks/releases/${NEW_VERSION}/worklog/drafts/`
   - `local-file/tasks/releases/${NEW_VERSION}/worklog/summaries/`
2. For each agentic file marked for archival:
   - Move the file from its current location to the corresponding worklog directory
   - Preserve the filename (including timestamp prefix)
3. This keeps the working agentic directories clean for the next development cycle

## Step 8: Update Task Indices

1. Update `local-file/tasks/manual/index.md`:
   - Remove all lines marked with `[x]` (completed tasks)
   - Keep only uncompleted tasks `[ ]`
   - Preserve category structure

2. Update `local-file/tasks/index.md`:
   - Add a link to the new release under "Archived Releases" section:
     ```markdown
     - [${NEW_VERSION}](./releases/${NEW_VERSION}/CHANGELOG.md) — Released YYYY-MM-DD
     ```

## Step 9: Update Project CHANGELOG.md

1. Read the generated `local-file/tasks/releases/${NEW_VERSION}/CHANGELOG.md`
2. Prepend its content to the root `CHANGELOG.md` file
3. Ensure proper formatting and separation between releases

## Step 10: Summary

Provide a summary:
- Number of manual tasks archived
- Number of simple_advices items archived (completed `[x]` count)
- Number of detailed auto-review tasks archived (if any)
- Number of agentic worklog files archived (by type: analysis, drafts, summaries)
- Categories affected
- Location of generated CHANGELOG
- Suggested next steps — present these as a numbered checklist the user can follow in order:
  1. Review the generated `local-file/tasks/releases/${NEW_VERSION}/CHANGELOG.md` and the root `CHANGELOG.md` — edit wording if needed
  2. Bump the version in `pyproject.toml` to the new version number (e.g. `version = "0.3.0"`)
  3. Commit all changes: `git add -A && git commit -m "chore: release ${NEW_VERSION}"`
  4. Create the git tag: `git tag ${NEW_VERSION}`
  5. Push commits and tag: `git push && git push --tags`
  6. On GitHub: go to Releases → "Draft a new release" → select the `${NEW_VERSION}` tag → paste the CHANGELOG entries as the release description → click "Publish release" (this triggers the GitHub Actions workflow that publishes to PyPI)
  7. Verify the PyPI publish succeeded: check the Actions tab on GitHub, then confirm the new version appears at https://pypi.org/project/beyond-local-file/
  8. Verify installation from PyPI: `uv tool install --upgrade beyond-local-file && beyond-local-file --version`

## Important Notes

- Do NOT create a git tag — the user will do this manually after review
- Do NOT commit changes — let the user review first
- Preserve the structure and formatting of all markdown files
- If no completed tasks exist, inform the user and exit gracefully
- Auto-review findings in `local-file/tasks/auto-review/simple_advices.md`: completed `[x]` items ARE archived to `local-file/tasks/releases/${NEW_VERSION}/tasks/auto-review/simple_advices.md`; open `[ ]` items remain in the live file as a continuing log
- Detailed auto-review tasks (if any exist and are completed) CAN be archived like manual tasks
- Agentic worklog files are MOVED (not copied) to keep working directories clean
- Only archive agentic files between the last release date and current date
