# Implementation Plan: Fix `revlink create/restore` Path Handling

## Overview

The fix has three parts: (1) add `rel_path` to both operation dataclasses and update all
internal uses of `source.name`, (2) add Rules 3–5 to `CreateOperation._validate`, and (3)
update `cli.py` to compute and pass `rel_path`. Existing tests need their operation
constructors updated; new tests cover the new validation rules and nested-path correctness.

## Tasks

- [x] 1. Add `rel_path` field to `CreateOperation` and fix all internal uses
  - [x] 1.1 Add `rel_path: Path` field to `CreateOperation` dataclass
    - Insert `rel_path: Path` after `dest_root: Path` in the dataclass definition
    - Update the class docstring `Attributes` section to document `rel_path`
    - _Requirements: 1, 3, 4_

  - [x] 1.2 Update `CreateOperation.run()` to derive dest from `rel_path`
    - Change `dest = self.dest_root / self.source.name` to `dest = self.dest_root / self.rel_path`
    - Update the `run()` docstring to reflect the new dest derivation
    - _Requirements: 1.2, 1.3, 1.4_

  - [x] 1.3 Update `CreateOperation._preview()` to use `rel_path`
    - Change `dest = self.dest_root / self.source.name` to `dest = self.dest_root / self.rel_path`
    - Update the config-update preview line: use `str(self.rel_path)` instead of `self.source.name`
    - _Requirements: 3.1_

  - [x] 1.4 Update `CreateOperation._git_exclude()` and `_git_exclude_preview()` to use `rel_path`
    - Replace all uses of `self.source.name` with `str(self.rel_path)` as the entry name
    - Update docstrings to reflect the change
    - _Requirements: 4.1_

  - [x] 1.5 Update `CreateOperation._update_config()` to use `rel_path`
    - Replace `self.source.name` with `str(self.rel_path)` in the `add_subpath_entry` call
    - Update the `config_updated` formatter call to use `str(self.rel_path)`
    - _Requirements: 4.2_

- [x] 2. Add `rel_path` field to `RestoreOperation` and fix all internal uses
  - [x] 2.1 Add `rel_path: Path` field to `RestoreOperation` dataclass
    - Insert `rel_path: Path` after `dest_root: Path` in the dataclass definition
    - Update the class docstring `Attributes` section to document `rel_path`
    - _Requirements: 2_

  - [x] 2.2 Update `RestoreOperation.run()` to derive managed path from `rel_path`
    - Change `managed = self.dest_root / self.source.name` to `managed = self.dest_root / self.rel_path`
    - Update the `run()` docstring to reflect the new managed path derivation
    - _Requirements: 2.1, 2.2_

  - [x] 2.3 Update `RestoreOperation._git_exclude()` and `_remove_config()` to use `rel_path`
    - Replace all uses of `self.source.name` with `str(self.rel_path)` as the entry name
    - Update docstrings to reflect the change
    - _Requirements: 2.3, 2.4_

- [x] 3. Update `cli.py` to compute and pass `rel_path`
  - [x] 3.1 Compute `rel_path` in `revlink_create` and pass it to `CreateOperation`
    - After `source = Path(path).resolve()`, add `rel_path = source.relative_to(cwd)`
    - Pass `rel_path=rel_path` to the `CreateOperation` constructor
    - _Requirements: 1, 3, 4_

  - [x] 3.2 Compute `rel_path` in `revlink_restore` and pass it to `RestoreOperation`
    - After `source = (cwd / path).absolute()`, add `rel_path = Path(path)`
    - Pass `rel_path=rel_path` to the `RestoreOperation` constructor
    - _Requirements: 2_

- [x] 4. Add Rules 3–5 to `CreateOperation._validate`
  - [x] 4.1 Implement Rule 3 — no intermediate symlink in the path
    - Walk ancestors of `self.rel_path` from shallowest to deepest (excluding `Path('.')`)
    - For each ancestor `anc`, compute `candidate = self.context.cwd / anc`
    - If `candidate.is_symlink()` and `candidate.resolve().is_relative_to(self.dest_root)`:
      print info message and return 0
    - If `candidate.is_symlink()` and not relative to managed project: print error and return 1
    - Skip entirely when `self.context is None`
    - _Requirements: 5_

  - [x] 4.2 Implement Rule 4 — sync-all mapping rejects nested paths
    - After Rule 3, check `self.context.matched_mapping.subpaths is None`
    - If `len(self.rel_path.parts) > 1`: print error and return 1
    - Skip entirely when `self.context is None`
    - _Requirements: 6_

  - [x] 4.3 Implement Rule 5 — selective sync subpath conflict detection
    - After Rule 4, check `self.context.matched_mapping.subpaths is not None`
    - For each `declared` in `matched_mapping.subpaths`:
      - 5a: if `rel_path == declared_path or rel_path.is_relative_to(declared_path)`:
        check `managed_copy.exists()` and print the appropriate error; return 1
      - 5b: if `declared_path.is_relative_to(rel_path)` and `declared_path != rel_path`:
        print reverse-conflict error; return 1
    - Skip entirely when `self.context is None`
    - _Requirements: 7_

  - [x] 4.4 Update `_validate` docstring to document all six rules
    - Replace the existing three-rule docstring with a six-rule description
    - Document the `self.context is None` skip condition for Rules 3–5
    - _Requirements: 5, 6, 7_

- [x] 5. Update existing tests to pass the new `rel_path` field
  - [x] 5.1 Update `tests/unit/test_revlink_operation.py`
    - Add `rel_path=Path(source.name)` to all `CreateOperation(...)` constructor calls in
      `_make_operation` helper and any direct instantiations
    - Verify all tests still pass without behaviour change
    - _Requirements: 8_

  - [x] 5.2 Update `tests/unit/test_revlink_failure_modes.py`
    - Add `rel_path=Path(source.name)` to all `CreateOperation(...)` constructor calls in
      `_make_operation` helper
    - Verify all tests still pass without behaviour change
    - _Requirements: 8_

  - [x] 5.3 Update `tests/unit/test_revlink_cli.py`
    - Review all tests that invoke `revlink create` via the CLI runner — these go through
      `cli.py` which now computes `rel_path`, so no direct operation constructor changes
      are needed here; verify all tests still pass
    - _Requirements: 8_

  - [x] 5.4 Update `tests/unit/test_restore_cli.py` and `tests/unit/test_restore_failure_modes.py`
    - Add `rel_path=Path(source.name)` to all `RestoreOperation(...)` constructor calls
    - Verify all tests still pass without behaviour change
    - _Requirements: 8_

- [x] 6. Write new unit tests for the new validation rules
  - [x] 6.1 Write unit tests for Rule 3 (intermediate symlink)
    - Test: ancestor symlink resolves into managed project → exit 0 with info message
    - Test: ancestor symlink resolves outside managed project → exit 1 with error message
    - Test: no ancestor symlink → Rule 3 has no effect, validation continues
    - Test: `context is None` → Rule 3 is skipped entirely
    - _Requirements: 5_

  - [x] 6.2 Write unit tests for Rule 4 (sync-all + nested path)
    - Test: sync-all mapping + `rel_path` with 2 parts → exit 1 with error message
    - Test: sync-all mapping + `rel_path` with 1 part → Rule 4 has no effect
    - Test: `context is None` → Rule 4 is skipped entirely
    - _Requirements: 6_

  - [x] 6.3 Write unit tests for Rule 5 (selective sync subpath conflicts)
    - Test 5a (copy exists): declared ancestor subpath, managed copy present → exit 1
    - Test 5a (copy missing): declared ancestor subpath, managed copy absent → exit 1
    - Test 5b: `rel_path` is ancestor of declared subpath → exit 1
    - Test: no conflict → Rule 5 has no effect, validation continues
    - Test: `context is None` → Rule 5 is skipped entirely
    - _Requirements: 7_

  - [x] 6.4 Write unit tests for dest path correctness with nested `rel_path`
    - Test: `CreateOperation.run` with `rel_path = Path(".kiro/specs/foo")` → managed copy
      at `dest_root / .kiro/specs/foo` (not `dest_root / foo`)
    - Test: `CreateOperation._git_exclude` with nested `rel_path` → entry name is
      `.kiro/specs/foo`, not `foo`
    - Test: `CreateOperation._update_config` with nested `rel_path` → entry name is
      `.kiro/specs/foo`, not `foo`
    - _Requirements: 1.2, 1.4, 4.1, 4.2_

- [x] 7. Write integration tests for nested path handling
  - [x] 7.1 Write integration test: `revlink create` with nested path
    - Set up a selective sync config with no existing subpaths
    - Run `revlink create .kiro/specs/foo` from the target directory
    - Assert: managed copy at `managed/.kiro/specs/foo`
    - Assert: symlink at `target/.kiro/specs/foo` pointing to `managed/.kiro/specs/foo`
    - Assert: config subpath list contains `.kiro/specs/foo`
    - _Requirements: 1.2, 1.3, 1.4, 4.2_

  - [x] 7.2 Write integration test: `revlink restore` with nested path
    - Set up a managed copy at `managed/.kiro/specs/foo` and a symlink at
      `target/.kiro/specs/foo`
    - Run `revlink restore .kiro/specs/foo` from the target directory
    - Assert: real file restored at `target/.kiro/specs/foo`
    - Assert: managed copy at `managed/.kiro/specs/foo` deleted
    - _Requirements: 2.1, 2.2_

- [x] 8. Final checkpoint — ensure all tests pass
  - Run `uv run pytest` and confirm zero failures
  - Run `uv run ruff check --fix .` and `uv run ruff format .` and confirm zero violations
  - _Requirements: 8_

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5", "2.2", "2.3"] },
    { "id": 2, "tasks": ["3.1", "3.2"] },
    { "id": 3, "tasks": ["4.1"] },
    { "id": 4, "tasks": ["4.2"] },
    { "id": 5, "tasks": ["4.3", "4.4"] },
    { "id": 6, "tasks": ["5.1", "5.2", "5.3", "5.4"] },
    { "id": 7, "tasks": ["6.1", "6.2", "6.3", "6.4"] },
    { "id": 8, "tasks": ["7.1", "7.2"] },
    { "id": 9, "tasks": ["8"] }
  ]
}
```

## Notes

- All operation constructor calls in tests must add `rel_path=Path(source.name)` for
  direct-child cases — behaviour is identical, only the field is new.
- Rules 3–5 in `_validate` are skipped when `self.context is None`. Tests that pass no
  context are not exercising config-aware validation; this is intentional.
- `revlink restore` does **not** gain Rules 3–5. The source is already a symlink (Rule 2
  catches non-symlinks) and the managed-copy-exists check already confirms the path is
  managed.
- Use `uv run pytest` and `uv run ruff check --fix . && uv run ruff format .` throughout.
- All new tests follow the existing patterns in `tests/unit/test_revlink_failure_modes.py`
  and `tests/integration/test_revlink_integration.py`.
