# Fix: revlink git exclude skipped for nested paths — Bugfix Design

## Overview

`GitExcludeManager` is instantiated with `self.source.parent` in three methods of `revlink.py`.
For nested paths (e.g. `docs/agent`), `source.parent` is `docs/` — which has no `.git` — so
`is_git_repo()` returns `False` and the step is silently skipped. The fix replaces
`self.source.parent` with `self.context.cwd` (the project root) in all three locations.
`self.context.cwd` is already available on both `CreateOperation` and `RestoreOperation` and
is always the directory that contains `.git`.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — the source path has more than one
  component (i.e. it is nested), causing `source.parent` to resolve to a subdirectory rather
  than the project root.
- **Property (P)**: The desired behavior — the git exclude step executes correctly regardless of
  path depth, using the project root (`context.cwd`) as the `GitExcludeManager` target.
- **Preservation**: Existing behaviour for top-level paths, `context is None` paths, and
  all non-git-exclude steps must remain completely unchanged.
- **`GitExcludeManager`**: Class in `src/beyond_local_file/git_manager.py` that reads and writes
  `.git/info/exclude`. Its `is_git_repo()` method returns `True` only when the supplied
  directory is (or contains) a `.git` folder.
- **`CreateOperation._git_exclude`**: The method in `revlink.py` (~line 762) that adds an entry
  to `.git/info/exclude` during a real `create` run.
- **`CreateOperation._git_exclude_preview`**: The method in `revlink.py` (~line 719) that
  previews the git exclude step during `create --dry-run`.
- **`RestoreOperation._git_exclude`**: The method in `revlink.py` (~line 1013) that removes an
  entry from `.git/info/exclude` during a `restore` run.
- **`self.context.cwd`**: The resolved current working directory on `RevlinkContext`; always the
  project root that contains `.git`.
- **`self.source.parent`**: The immediate parent directory of the source path; for nested paths
  this is a subdirectory, not the project root.

## Bug Details

### Bug Condition

The bug manifests whenever the source path supplied to `blf revlink create` or
`blf revlink restore` has more than one component — i.e. the path is nested. All three affected
methods use `self.source.parent` instead of `self.context.cwd` to construct the
`GitExcludeManager`, so the manager's `is_git_repo()` check fails for any directory that is not
the project root.

**Formal Specification:**

```
FUNCTION isBugCondition(source)
  INPUT: source of type Path (absolute path to the file or directory being adopted/restored)
  OUTPUT: boolean

  RETURN len(source.relative_to(context.cwd).parts) > 1
         // i.e. source.parent != context.cwd
         // i.e. the path is nested at least one level below the project root
END FUNCTION
```

### Examples

- `blf revlink create docs/agent` — `source.parent` is `<cwd>/docs/`, no `.git` there;
  `is_git_repo()` returns `False`; no exclude entry written (BUG)
- `blf revlink create .kiro/specs/foo` — `source.parent` is `<cwd>/.kiro/specs/`, no `.git`;
  silently skipped (BUG)
- `blf revlink create myfile.txt` — `source.parent` is `<cwd>/`, `.git` found;
  `is_git_repo()` returns `True`; entry written correctly (NOT affected)
- `blf revlink restore docs/agent` — same failure path; no exclude entry removed (BUG)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Top-level `create` paths continue to have their exclude entries written correctly.
- Top-level `restore` paths continue to have their exclude entries removed correctly.
- `create --dry-run` preview output for top-level paths remains unchanged.
- When `self.context is None`, the git exclude step continues to be silently skipped
  (this is the test-only escape hatch; it must not be broken).
- All other steps of `create` and `restore` (copy, verify, replace, checksum, config update)
  are completely unaffected.

**Scope:**
All inputs where `isBugCondition` returns `False` — i.e. top-level paths — must produce
identical output before and after the fix. The only behavioral change is that nested paths now
correctly execute the git exclude step instead of silently skipping it.

## Hypothesized Root Cause

There is a single root cause with no ambiguity:

1. **Wrong reference directory for `GitExcludeManager`**: All three methods pass
   `self.source.parent` to `GitExcludeManager`. This works for top-level paths because
   `source.parent == context.cwd` (the project root), but fails for nested paths because
   `source.parent` resolves to an intermediate subdirectory that has no `.git` folder.
   The fix is mechanical: replace `self.source.parent` with `self.context.cwd` and add a
   `context is None` guard (mirroring the existing escape hatch used by `_update_config`
   and `_remove_config`).

## Correctness Properties

Property 1: Bug Condition — Nested Path Git Exclude Execution

_For any_ source path where the bug condition holds (the path is nested — `isBugCondition`
returns `True`), the fixed `_git_exclude` and `_git_exclude_preview` methods SHALL correctly
execute the git exclude step using `context.cwd` as the repository root, adding/removing/
previewing the full relative path entry in `.git/info/exclude`.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation — Top-Level Path Behavior Unchanged

_For any_ source path where the bug condition does NOT hold (the path is top-level —
`isBugCondition` returns `False`), the fixed methods SHALL produce exactly the same
behaviour as the original methods, preserving the git exclude write, remove, and preview
actions for top-level paths without regression.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

## Fix Implementation

### Changes Required

**File:** `src/beyond_local_file/operations/revlink.py`

All three changes are identical in structure: add a `context is None` early return, then
replace `self.source.parent` with `self.context.cwd`.

**1. `CreateOperation._git_exclude_preview` (~line 719):**

```python
# Before
manager = GitExcludeManager(self.source.parent)
if not manager.is_git_repo():
    return

# After
if self.context is None:
    return
manager = GitExcludeManager(self.context.cwd)
if not manager.is_git_repo():
    return
```

**2. `CreateOperation._git_exclude` (~line 762):**

```python
# Before
manager = GitExcludeManager(self.source.parent)
if not manager.is_git_repo():
    return 0

# After
if self.context is None:
    return 0
manager = GitExcludeManager(self.context.cwd)
if not manager.is_git_repo():
    return 0
```

**3. `RestoreOperation._git_exclude` (~line 1013):**

```python
# Before
manager = GitExcludeManager(self.source.parent)
if not manager.is_git_repo():
    return 0

# After
if self.context is None:
    return 0
manager = GitExcludeManager(self.context.cwd)
if not manager.is_git_repo():
    return 0
```

No changes to `GitExcludeManager`, `RevlinkContext`, or any other module are required.

## Testing Strategy

### Validation Approach

The testing strategy follows the two-phase bugfix approach: first surface counterexamples
on unfixed code to confirm the bug, then verify the fix and check for regressions.
Tests live in `tests/integration/test_revlink_integration.py` in a new class
`TestRevlinkGitExcludeNestedPath`.

### Exploratory Bug Condition Checking

**Goal:** Surface counterexamples that demonstrate the bug BEFORE implementing the fix.
Confirm the root cause: `_git_exclude` silently skips for nested paths.

**Test Plan:** Set up a temporary git repo with a selective-sync mapping. Run `create` with
a nested path (e.g. `docs/agent`). Assert the path appears in `.git/info/exclude`. On unfixed
code, this assertion will FAIL — the entry will not be present.

**Test Cases:**
1. **Nested create test**: `create docs/agent` in a selective-sync mapping — assert
   `docs/agent` in `.git/info/exclude` (will FAIL on unfixed code)
2. **Nested dry-run test**: `create --dry-run docs/agent` — assert preview output contains
   a git exclude message (will FAIL on unfixed code)
3. **Nested restore test**: set up exclude entry manually, run `restore docs/agent` —
   assert `docs/agent` NOT in `.git/info/exclude` (will FAIL on unfixed code)

**Expected Counterexamples:**
- `.git/info/exclude` does not contain the nested path entry after `create`
- Dry-run output contains no mention of git exclude action
- `.git/info/exclude` still contains the nested path entry after `restore`

### Fix Checking

**Goal:** Verify that for all nested path inputs where the bug condition holds, the fixed
methods produce the expected behavior.

**Pseudocode:**

```
FOR ALL source WHERE isBugCondition(source) DO
  result := revlink_create_fixed(source)
  ASSERT str(source.relative_to(cwd)) IN read_git_exclude(cwd)
END FOR
```

### Preservation Checking

**Goal:** Verify that for all top-level path inputs where the bug condition does NOT hold,
the fixed methods produce the same result as the original methods.

**Pseudocode:**

```
FOR ALL source WHERE NOT isBugCondition(source) DO
  ASSERT revlink_create_original(source) == revlink_create_fixed(source)
  // i.e. str(source.name) IN read_git_exclude(cwd) in both cases
END FOR
```

**Testing Approach:** Property-based testing is recommended for preservation checking
because it generates many top-level path variations automatically, catching any regression
across different filenames, extensions, and edge-case names.

**Test Cases:**
1. **Top-level create preservation**: Observe `myfile.txt` added to exclude on unfixed code,
   then write property-based test verifying any single-component path still gets excluded
   after the fix.
2. **Top-level restore preservation**: Observe `myfile.txt` removed from exclude on unfixed
   code, then write property-based test verifying any single-component path entry is still
   removed correctly after the fix.
3. **Top-level dry-run preservation**: Verify dry-run preview for top-level paths still
   mentions the git exclude action.

### Unit Tests

- Test `_git_exclude` directly with a mocked `GitExcludeManager` and a nested `rel_path`
- Test `_git_exclude_preview` with a nested path and dry-run mode
- Test that `context is None` skips the step without error for both operations

### Property-Based Tests

- Generate random top-level filenames and verify that after `create`, the entry appears in
  `.git/info/exclude` (preservation property across name variations)
- Generate random top-level filenames and verify that after `restore`, the entry is removed
  from `.git/info/exclude`

### Integration Tests

- Full `create` → `restore` round-trip for a nested path: verify exclude entry is added by
  `create` and removed by `restore`
- Full `create --dry-run` for a nested path: verify preview output includes the git exclude
  message without modifying the filesystem
