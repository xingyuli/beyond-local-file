---
inclusion: manual
description: "Archives completed tasks, writes the changelog in a chosen gathering mode, bumps pyproject.toml and uv.lock, and cleans up task indices for the next release"
---

You are preparing a new release for the `beyond-local-file` project. Follow these steps:

## Step 1: Determine Release Version

1. Get the latest git tag: `git describe --tags --abbrev=0`
2. Ask the user what the next version number should be (e.g., v0.2.0)
3. Store this as `NEW_VERSION` (keep the leading `v`; the git tag and release directory use it)
4. Store `VERSION_NUMBER` as `NEW_VERSION` without the leading `v` (`v0.8.0` → `0.8.0`). `pyproject.toml` and `uv.lock` use this form
5. Get the date of the last release tag: `git log -1 --format=%ai [last-tag]`
6. Store this as `LAST_RELEASE_DATE`

## Step 2: Validate All Tests Pass

1. Run the full test suite: `uv run pytest` (runs in parallel by default)
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
4. If no completed tasks exist, inform the user and exit gracefully. Do not bump the version or write a changelog
5. Do not write changelog entries yet

## Step 4: Understand Changes Since the Last Release

Read the product delta before choosing how to write the changelog.

1. List commits since the last tag: `git log [last-tag]..HEAD --format='%h %s'`
2. Read the bodies of feature and fix commits
3. For a change that looks like a fix, compare behavior at the last tag with `HEAD`. Decide which of these it is:
   - A fix of behavior that already shipped in the last release
   - A fix or completion of a feature introduced after the last release
4. Separate the range into three groups:
   - User-visible changes since the last release (commands, output, sync behavior, notices, logs)
   - Fixes of features introduced after the last release
   - Internal work (refactors, module moves, IPC shape, tests, chores, docs that only record structure)
5. Keep this classification. Do not write the changelog yet

## Step 5: Recommend a CHANGELOG Gathering Mode

Recommend one mode, with the reason tied to the classification from Step 4. Then ask the user to choose. Do not continue to Step 6 until the user has chosen.

Recommend **end user perspective** when the range contains internal work, commits that only finish or fix a feature introduced after the last tag, or several tickets that are one behavior. Recommend **ticket list merge** when each completed task is its own user-facing change and there is little internal-only work.

### Ticket list merge

One changelog entry per completed task, grouped by the task's category. The release notes are a record of those tasks.

- Use the task title, Description, Motivation, and Expected Behavior
- Keep every completed task, including internal ones
- Include a category only when it has completed tasks: Features, Bug Fixes, Usability, Documentation, Code Quality

### End user perspective

Write what changes for someone upgrading from the last release.

- A commit that only finishes or fixes a feature introduced after the last release is part of that feature, not its own entry
- A fix of behavior that already shipped in the last release stays a bug fix
- A change to an existing command is a change. A new command or a new capability is a feature
- Omit internal work that does not change what the user runs, sees, or how files sync
- Mention a small visible side effect (for example a line that disappeared from command output) only when a user would notice it. Otherwise tell the user you left it out
- Use only the categories that have user-visible entries. Do not add Code Quality for internal work

## Step 6: Generate CHANGELOG

Create `local-file/tasks/releases/${NEW_VERSION}/CHANGELOG.md`.

Ticket list merge uses this structure. Omit empty categories.

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

End user perspective uses the same release heading and date, and the same category headings that apply (Features, Bug Fixes, Usability, Documentation). Write each entry as the upgrade outcome, not as a restatement of the ticket title. Do not add a Code Quality section.

## Step 7: Archive Completed Tasks

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

## Step 8: Archive Agentic Worklog Files

1. Find all timestamped files in `local-file/agentic/analysis/`, `local-file/agentic/drafts/`, and `local-file/agentic/summaries/`
2. For each file with `YYYYMMDD-HH-` prefix:
   - Parse the timestamp from the filename
   - If the timestamp is >= `LAST_RELEASE_DATE` and < current date, mark for archival
3. Store the list of files to archive
4. Create directories:
   - `local-file/tasks/releases/${NEW_VERSION}/worklog/analysis/`
   - `local-file/tasks/releases/${NEW_VERSION}/worklog/drafts/`
   - `local-file/tasks/releases/${NEW_VERSION}/worklog/summaries/`
5. For each agentic file marked for archival:
   - Move the file from its current location to the corresponding worklog directory
   - Preserve the filename (including timestamp prefix)
6. This keeps the working agentic directories clean for the next development cycle

## Step 9: Update Task Indices

1. Update `local-file/tasks/manual/index.md`:
   - Remove all lines marked with `[x]` (completed tasks)
   - Keep only uncompleted tasks `[ ]`
   - Preserve category structure

2. Update `local-file/tasks/index.md`:
   - Add a link to the new release under "Archived Releases" section:
     ```markdown
     - [${NEW_VERSION}](./releases/${NEW_VERSION}/CHANGELOG.md) — Released YYYY-MM-DD
     ```

## Step 10: Update Project CHANGELOG.md

The root `CHANGELOG.md` stays [Keep a Changelog](https://keepachangelog.com/en/1.0.0/). Prepend a section for this release. Do not paste the release file's category headings into it.

```markdown
## [${VERSION_NUMBER}] - [YYYY-MM-DD]

### Added

### Changed

### Fixed

[${VERSION_NUMBER}]: https://github.com/xingyuli/beyond-local-file/releases/tag/${NEW_VERSION}
```

Omit empty headings. Place the compare link after the new section, before the previous release.

Map entries into those headings:

- Ticket list merge: Features → Added, Bug Fixes → Fixed, Usability, Documentation, and Code Quality → Changed
- End user perspective: new commands and new capabilities → Added, changes to existing commands or output → Changed, fixes of behavior that shipped in the last release → Fixed

Use the same wording as the release changelog.

## Step 11: Update pyproject.toml and uv.lock

Do this as part of release preparation. Do not leave the bump for the user.

1. Set `version` in `pyproject.toml` to `VERSION_NUMBER`. Change that field only
2. Refresh the lock: `uv lock`
   - Do not pass `--upgrade`
   - Do not edit `uv.lock` by hand
3. Confirm the `[[package]]` named `beyond-local-file` has `version` equal to `VERSION_NUMBER`
4. If `uv lock` changes any dependency version, stop and show the user that diff. A dependency upgrade is not part of the release

## Step 12: Summary

Provide a summary:
- CHANGELOG gathering mode used
- Number of manual tasks archived
- Number of simple_advices items archived (completed `[x]` count)
- Number of detailed auto-review tasks archived (if any)
- Number of agentic worklog files archived (by type: analysis, drafts, summaries)
- Categories affected
- Location of generated CHANGELOG
- `VERSION_NUMBER` now in `pyproject.toml` and `uv.lock`
- Suggested next steps — present these as a numbered checklist the user can follow in order:
  1. Review `local-file/tasks/releases/${NEW_VERSION}/CHANGELOG.md` and the root `CHANGELOG.md` — edit wording if needed
  2. Commit all changes: `git add -A && git commit -m "chore: release ${NEW_VERSION}"`. `local-file/` is excluded in this clone, so the archive stays local. The commit carries the root `CHANGELOG.md`, `pyproject.toml`, and `uv.lock`
  3. Create the git tag: `git tag ${NEW_VERSION}`
  4. Push commits and tag: `git push && git push --tags`
  5. On GitHub: go to Releases → "Draft a new release" → select the `${NEW_VERSION}` tag → paste the CHANGELOG entries as the release description → click "Publish release" (this triggers the GitHub Actions workflow that publishes to PyPI)
  6. Verify the PyPI publish succeeded: check the Actions tab on GitHub, then confirm the new version appears at https://pypi.org/project/beyond-local-file/
  7. Verify installation from PyPI: `uv tool install --upgrade beyond-local-file && beyond-local-file --version`

## Important Notes

- Do NOT create a git tag — the user will do this manually after review
- Do NOT commit changes — let the user review first
- Do NOT write the changelog before the user chooses the gathering mode in Step 5
- Preserve the structure and formatting of all markdown files
- If no completed tasks exist, inform the user and exit gracefully
- Auto-review findings in `local-file/tasks/auto-review/simple_advices.md`: completed `[x]` items ARE archived to `local-file/tasks/releases/${NEW_VERSION}/tasks/auto-review/simple_advices.md`; open `[ ]` items remain in the live file as a continuing log
- Detailed auto-review tasks (if any exist and are completed) CAN be archived like manual tasks
- Agentic worklog files are MOVED (not copied) to keep working directories clean
- Only archive agentic files between the last release date and current date
- `NEW_VERSION` keeps the leading `v`. `pyproject.toml` and `uv.lock` store `VERSION_NUMBER` without it
