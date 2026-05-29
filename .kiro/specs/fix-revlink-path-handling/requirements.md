# Requirements Document

## Introduction

`revlink create` uses `source.name` (the basename) to derive the managed destination path,
which is wrong for any path that is not a direct child of CWD. The full relative path from
CWD must be preserved so the managed layout mirrors the target layout and `link sync`
produces correct symlinks. `revlink restore` has the same bug.

In addition, `CreateOperation._validate` must enforce six ordered rules. Rules 1 and 2
already exist; Rules 3–5 are new; Rule 6 (dest-exists check) is updated to use `rel_path`
as the dest key.

## Glossary

- **rel_path**: `source.relative_to(cwd)` — the path of the source relative to CWD,
  e.g. `.kiro/specs/revlink-subcommands`. This is the correct key for managed layout.
- **dest**: `managed_project_path / rel_path` — the correct managed destination.
- **matched_mapping**: The `Mapping` object whose `targets` list contains `cwd`.
- **sync-all mapping**: A mapping with `subpaths is None` — it syncs everything at the
  top level.
- **selective sync mapping**: A mapping with `subpaths is not None` — it syncs only the
  listed subpaths.

## Requirements

### Requirement 1: Correct Managed Destination Path

**User Story:** As a developer, I want `revlink create` to copy a nested file to the correct
managed location so that `link sync` produces the right symlink.

#### Acceptance Criteria

1. WHEN `revlink create` is invoked with a path that is a direct child of CWD (e.g.
   `myfile.txt`), the managed destination SHALL be `managed_project_path / myfile.txt`
   (unchanged from current behaviour).
2. WHEN `revlink create` is invoked with a nested path (e.g. `.kiro/specs/foo`), the managed
   destination SHALL be `managed_project_path / .kiro/specs/foo`, preserving the full
   directory structure.
3. WHEN `revlink create` copies a nested path, the parent directories of the managed
   destination SHALL be created automatically if they do not exist.
4. WHEN `revlink create` creates a symlink for a nested path, the symlink SHALL point to
   `managed_project_path / rel_path` (not `managed_project_path / source.name`).

---

### Requirement 2: Correct Restore Path

**User Story:** As a developer, I want `revlink restore` to find the managed copy at the
correct location so that it can dissolve a nested symlink correctly.

#### Acceptance Criteria

1. WHEN `revlink restore` is invoked with a nested path (e.g. `.kiro/specs/foo`), the
   managed copy SHALL be looked up at `managed_project_path / .kiro/specs/foo`.
2. WHEN `revlink restore` removes the managed copy, it SHALL remove
   `managed_project_path / rel_path`.
3. WHEN `revlink restore` removes the git exclude entry, the entry name SHALL be
   `str(rel_path)` (e.g. `.kiro/specs/foo`), not `source.name` (e.g. `foo`).
4. WHEN `revlink restore` removes the config subpath entry, the entry name SHALL be
   `str(rel_path)`, not `source.name`.

---

### Requirement 3: Dry-run Correctness for Nested Paths

**User Story:** As a developer, I want `--dry-run` to preview the correct managed path for
nested files so that I can verify the operation before running it.

#### Acceptance Criteria

1. WHEN `--dry-run` is active and the source is a nested path, the preview output SHALL show
   the correct managed destination (`managed_project_path / rel_path`).
2. WHEN `--dry-run` is active, the filesystem SHALL remain unchanged regardless of whether
   the source is a direct child or a nested path.

---

### Requirement 4: Git Exclude and Config Entry Use rel_path

**User Story:** As a developer, I want the git exclude entry and config subpath entry to use
the full relative path so that `link sync` and `link check` manage the correct item.

#### Acceptance Criteria

1. WHEN `revlink create` adds an entry to `.git/info/exclude`, the entry SHALL be
   `str(rel_path)` (e.g. `.kiro/specs/foo`), not `source.name` (e.g. `foo`).
2. WHEN `revlink create` adds an entry to the config subpath list, the entry SHALL be
   `str(rel_path)`, not `source.name`.

---

### Requirement 5: Source Must Exist and Must Not Be a Symlink (Rules 1–2)

**User Story:** As a developer, I want `revlink create` to reject missing or already-linked
paths immediately so that I receive a clear error before any filesystem mutation.

#### Acceptance Criteria

1. WHEN the source path does not exist, `revlink create` SHALL print an error and exit 1.
   - Message: `Error: Path does not exist: {source}`
2. WHEN the source path is already a symlink, `revlink create` SHALL print an error and exit 1.
   - Message: `Error: Path is already a symlink: {source}`
3. Rules 1 and 2 SHALL be evaluated before Rules 3–6 in all cases.

---

### Requirement 6: No Intermediate Symlink in Path (Rule 3)

**User Story:** As a developer, I want `revlink create` to detect when an ancestor directory
is already a managed symlink so that I receive a clear message instead of a confusing error.

#### Acceptance Criteria

1. WHEN an ancestor directory of `rel_path` is a symlink that resolves into
   `managed_project_path`, `revlink create` SHALL print an informational message and exit 0
   (the path is already managed through the ancestor).
   - Message: `'{anc}' is a managed symlink — '{rel_path}' is already managed through it. Nothing to do.`
2. WHEN an ancestor directory of `rel_path` is a symlink that resolves outside
   `managed_project_path`, `revlink create` SHALL print an error and exit 1.
   - Message: `Error: '{anc}' is a symlink not managed by blf. Cannot adopt a path through an unmanaged symlink.`
3. WHEN no ancestor directory of `rel_path` is a symlink, Rule 3 SHALL have no effect and
   validation SHALL continue to Rule 4.
4. Rule 3 SHALL only be evaluated when `self.context` is not `None`.

---

### Requirement 7: Sync-all Mapping Rejects Nested Paths (Rule 4)

**User Story:** As a developer, I want `revlink create` to reject nested paths when the
mapping uses sync-all so that I understand I need to switch to selective sync first.

#### Acceptance Criteria

1. WHEN the matched mapping has no `subpath` list (sync-all) and `rel_path` has more than
   one component, `revlink create` SHALL print an error and exit 1.
   - Message: `Error: '{rel_path}' is a nested path. This mapping uses sync-all — only top-level paths can be adopted directly. Add a 'subpath' entry to your config mapping first.`
2. WHEN the matched mapping has no `subpath` list and `rel_path` has exactly one component
   (direct child of CWD), Rule 4 SHALL have no effect and validation SHALL continue to Rule 5.
3. Rule 4 SHALL only be evaluated when `self.context` is not `None`.

---

### Requirement 8: Selective Sync Mapping Subpath Conflict Detection (Rule 5)

**User Story:** As a developer, I want `revlink create` to detect conflicts with existing
declared subpaths so that I receive actionable guidance instead of silently creating a
duplicate or conflicting entry.

#### Acceptance Criteria

1. WHEN the matched mapping has a `subpath` list and a declared subpath is an ancestor of
   (or equal to) `rel_path`, AND the managed copy already exists, `revlink create` SHALL
   print an error and exit 1.
   - Message: `Error: '{declared}' is already a declared subpath that covers this path, and the managed copy already exists at '{managed_copy}'. Run 'blf link sync' to create the symlink.`
2. WHEN the matched mapping has a `subpath` list and a declared subpath is an ancestor of
   (or equal to) `rel_path`, AND the managed copy does not exist, `revlink create` SHALL
   print an error and exit 1.
   - Message: `Error: '{declared}' is already a declared subpath that covers this path. Copy '{source}' to '{managed_copy}' manually, then run 'blf link sync' to create the symlink.`
3. WHEN the matched mapping has a `subpath` list and `rel_path` is an ancestor of a declared
   subpath (reverse conflict), `revlink create` SHALL print an error and exit 1.
   - Message: `Error: '{declared}' is a declared subpath under this path. Adopting '{rel_path}' would conflict with it. Remove '{declared}' from the config subpath list first, or adopt a more specific path.`
4. WHEN the matched mapping has a `subpath` list and no declared subpath conflicts with
   `rel_path`, Rule 5 SHALL have no effect and validation SHALL continue to Rule 6.
5. Rule 5 SHALL only be evaluated when `self.context` is not `None`.

---

### Requirement 9: Destination Must Not Already Exist Unless --force (Rule 6)

**User Story:** As a developer, I want `revlink create` to refuse to overwrite an existing
managed copy unless I explicitly pass `--force`, so that I never accidentally lose data.

#### Acceptance Criteria

1. WHEN the managed destination (`managed_project_path / rel_path`) already exists and
   `--force` is not set, `revlink create` SHALL print an error and exit 1.
   - Message: `Error: Destination already exists: {dest}\nUse --force to overwrite.`
2. WHEN the managed destination already exists and `--force` is set, `revlink create` SHALL
   overwrite it and proceed with the copy.
3. Rule 6 SHALL be evaluated last, after Rules 1–5 have all passed.

---

### Requirement 10: Existing Tests Remain Green

**User Story:** As a developer, I want all existing tests to continue passing after the
refactor so that I have confidence the fix does not regress existing behaviour.

#### Acceptance Criteria

1. All existing unit tests for `CreateOperation` and `RestoreOperation` SHALL pass after
   the `rel_path` field is added.
2. All existing integration tests SHALL pass after the fix.
3. For tests where `source` is a direct child of the target directory, the observable
   behaviour SHALL be identical to the current implementation.
