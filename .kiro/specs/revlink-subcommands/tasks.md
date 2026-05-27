# Implementation Plan: `revlink` Subcommands (`create` / `restore`)

## Overview

Restructure `blf revlink` into a subcommand group, rename the internal classes, implement the `restore` inverse operation, and add `ConfigUpdater.remove_subpath_entry()`. Work is organized into waves of parallel tasks. Each wave can begin only after all tasks in the preceding wave are complete.

## Tasks

- [x] 1. Rename `RevlinkOperation` → `CreateOperation` and `RevlinkFormatter` → `CreateFormatter`
  - [x] 1.1 Rename classes in `operations/revlink.py`
    - Rename `RevlinkOperation` → `CreateOperation` throughout `operations/revlink.py`
    - Rename `RevlinkFormatter` → `CreateFormatter` throughout `operations/revlink.py`
    - Update all internal references (dataclass fields, method bodies, docstrings)
    - _Requirements: 2.2, 2.3_

  - [x] 1.2 Update `operations/__init__.py` exports
    - Replace `from .revlink import RevlinkContext, RevlinkOperation` with `from .revlink import CreateOperation, RevlinkContext`
    - Replace `RevlinkOperation` with `CreateOperation` in `__all__`
    - _Requirements: 2.4_

  - [x] 1.3 Update `cli.py` import and usage
    - Replace `RevlinkOperation` import with `CreateOperation`
    - Replace `RevlinkFormatter` import with `CreateFormatter`
    - Update the instantiation sites in the `revlink` command handler
    - _Requirements: 2.2, 2.3_

  - [x] 1.4 Update all test files that reference `RevlinkOperation` or `RevlinkFormatter`
    - Search for all occurrences in `tests/` and update to `CreateOperation` / `CreateFormatter`
    - Verify tests still pass after rename
    - _Requirements: 2.2, 2.3_

- [x] 2. Restructure CLI — convert `revlink` command to a group with `create` subcommand

  - [x] 2.1 Convert `@cli.command()` `revlink` to `@cli.group()` `revlink` in `cli.py`
    - Change decorator from `@cli.command()` to `@cli.group()`
    - Remove `path`, `--dry-run`, `--force` parameters from the group function
    - Add a short docstring for the group (no `Args:` section per steering rules)
    - _Requirements: 1.1, 1.5_

  - [x] 2.2 Move current `revlink` command body into `@revlink.command("create")`
    - Create `revlink_create(ctx, path, dry_run, force)` function decorated with `@revlink.command("create")`
    - Move all existing logic (project resolution, `CreateOperation` instantiation) into this function
    - Retain `--dry-run` and `--force` options
    - Add Click-style docstring (no `Args:` section)
    - _Requirements: 1.2, 1.3, 1.6, 2.1, 2.5_

  - [x] 2.3 Write unit tests for CLI restructuring
    - Test `blf revlink --help` lists `create` and `restore`
    - Test `blf revlink create --help` shows `path`, `--dry-run`, `--force`
    - Test `blf revlink restore --help` shows `path`, `--dry-run` (no `--force`)
    - Test `blf revlink create <path>` invokes `CreateOperation` (existing behavior preserved)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [x] 3. Add `ConfigUpdater.remove_subpath_entry()` in `config.py`

  - [x] 3.1 Implement `remove_subpath_entry` method on `ConfigUpdater`
    - Mirror the structure of `add_subpath_entry`: load with `ruamel.yaml`, locate mapping, mutate in-place, write back
    - Locate entries by comparing plain strings AND `{"path": entry_name, ...}` dicts
    - Return `True` if file was updated, `False` if no change needed
    - If subpath list becomes empty after removal, leave the empty list in place (do not remove the `subpath` key)
    - Add Google-style docstring
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [x] 3.2 Write property test for `remove_subpath_entry` — Property 2: idempotence
    - **Property 2: `ConfigUpdater.remove_subpath_entry` is idempotent**
    - **Validates: Requirements 6.3, 6.4, 6.5**
    - Generate random config YAML with a subpath list using Hypothesis
    - Call `remove_subpath_entry` twice with the same arguments
    - Assert the config file content after the second call is identical to the content after the first call
    - Tag: `# Feature: revlink-subcommands, Property 2: remove_subpath_entry is idempotent`

  - [x] 3.3 Write unit tests for `remove_subpath_entry`
    - Test removes plain string entry when present
    - Test removes `{"path": entry_name, ...}` dict entry when present
    - Test returns `False` when entry is absent
    - Test returns `False` when mapping has no `subpath` key
    - Test leaves empty list in place when last entry is removed
    - Test preserves YAML comments and formatting (round-trip)
    - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [x] 4. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement `RestoreFormatter` and `RestoreOperation` in `operations/revlink.py`

  - [x] 5.1 Implement `RestoreFormatter` in `operations/revlink.py`
    - Add `dry_run: bool` constructor parameter; prefix all output with `[dry-run]` when active
    - Implement all formatter methods: `removing_symlink`, `copying_back`, `computing_checksum`, `checksum_ok`, `managed_copy_deleted`, `managed_copy_delete_failed`, `git_exclude_removed`, `git_exclude_not_found`, `config_entry_removed`, `error`
    - Add Google-style docstrings to the class and each method
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10_

  - [x] 5.2 Implement `RestoreOperation._validate()` in `operations/revlink.py`
    - Define `@dataclass RestoreOperation` with fields: `source`, `dest_root`, `dry_run`, `formatter`, `context`
    - Derive `managed` as `dest_root / source.name` inside `run()`
    - Implement `_validate(managed)`: check path exists, path is a symlink, managed copy exists
    - Return exit code 1 with appropriate `formatter.error()` call on each failure
    - Add Google-style docstrings
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 5.3 Implement `RestoreOperation._replace()` in `operations/revlink.py`
    - Call `formatter.removing_symlink(source)` before unlinking
    - Remove the symlink using `source.unlink(missing_ok=False)` — NEVER `shutil.rmtree`
    - Catch `PermissionError` on unlink; call `formatter.error(...)` and return 1
    - Call `formatter.copying_back(managed, source)` before copying
    - Copy managed content back using `shutil.copy2` (file) or `shutil.copytree` (directory)
    - _Requirements: 4.1, 4.2, 4.3, 7.1, 7.2_

  - [x] 5.4 Write property test for `RestoreOperation._replace` — Property 3: unlink not rmtree
    - **Property 3: `RestoreOperation._replace` never calls `rmtree` on a symlink path**
    - **Validates: Requirements 4.1**
    - Generate symlinks pointing to real directories in `tmp_path` using Hypothesis
    - Invoke `_replace` on the symlink
    - Assert the symlink target directory still exists after `_replace` completes
    - Tag: `# Feature: revlink-subcommands, Property 3: _replace uses unlink not rmtree on symlinks`

  - [x] 5.5 Implement `RestoreOperation._verify()` in `operations/revlink.py`
    - Call `formatter.computing_checksum(managed)` before computing
    - Compute `ChecksumVerifier.compute(managed)` and `ChecksumVerifier.compute(source)`
    - On mismatch: delete the restored `source` copy, call `formatter.error(...)`, return 1
    - On match: call `formatter.checksum_ok()`
    - _Requirements: 4.4, 4.5, 4.6, 7.3, 7.4_

  - [x] 5.6 Implement `RestoreOperation._delete_managed()`, `_git_exclude()`, `_remove_config()`, and `run()` in `operations/revlink.py`
    - `_delete_managed(managed)`: attempt delete with `shutil.rmtree` (dir) or `managed.unlink()` (file); on `OSError` call `formatter.managed_copy_delete_failed(managed)` and continue (non-fatal)
    - `_git_exclude()`: instantiate `GitExcludeManager(source.parent)`, check `is_git_repo()`, call `remove_entries({source.name})`; call `formatter.git_exclude_removed` or `formatter.git_exclude_not_found` based on result
    - `_remove_config()`: if `context` is not None and `context.matched_mapping.subpaths` is not None, call `ConfigUpdater.remove_subpath_entry`; call `formatter.config_entry_removed` if changed
    - `run()`: derive `managed`, call `_validate`, then if `dry_run` call `_preview`, else call `_replace → _verify → _delete_managed → _git_exclude → _remove_config` in order; return 0 on success
    - _Requirements: 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 7.5, 7.6, 7.7, 7.8, 7.9_

  - [x] 5.7 Write property test for `RestoreOperation` — Property 1: dry-run filesystem invariant
    - **Property 1: `restore` dry-run never modifies the filesystem**
    - **Validates: Requirements 3.4**
    - Generate random symlink setups in `tmp_path` using Hypothesis
    - Snapshot the directory tree before and after invoking `RestoreOperation` with `dry_run=True`
    - Assert the snapshots are identical
    - Tag: `# Feature: revlink-subcommands, Property 1: restore dry-run never modifies filesystem`

- [x] 6. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Wire `revlink restore` into `cli.py` and update `operations/__init__.py`

  - [x] 7.1 Export `RestoreOperation` from `operations/__init__.py`
    - Add `from .revlink import RestoreOperation` and include it in `__all__`
    - _Requirements: 1.1_

  - [x] 7.2 Add `@revlink.command("restore")` to `cli.py`
    - Create `revlink_restore(ctx, path, dry_run)` decorated with `@revlink.command("restore")`
    - Accept positional `path` argument and `--dry-run` flag (no `--force`)
    - Resolve `source` as `Path(path).resolve()`; call `load_config_projects`, `resolve_project_from_cwd`
    - Build `RevlinkContext` from the matched mapping (same pattern as `revlink_create`)
    - Instantiate and run `RestoreOperation(source, dest_root, dry_run, RestoreFormatter(dry_run), context)`
    - Emit correct error messages for no-match and ambiguous-match; call `ctx.exit(1)` on failure
    - Add Click-style docstring (no `Args:` section)
    - _Requirements: 1.1, 1.4, 1.7, 3.1, 3.2, 3.3_

- [x] 8. Write unit tests for `revlink restore` CLI wiring, validation, and error cases

  - [x] 8.1 Write unit tests for `revlink restore` CLI wiring and pre-flight validation
    - Test `revlink restore` is registered as a subcommand of the `revlink` group
    - Test each pre-flight error: non-existent path, not a symlink, dangling symlink
    - Test `--dry-run` flag is accepted; `--force` flag is rejected
    - _Requirements: 1.4, 1.7, 3.1, 3.2, 3.3, 3.4_

  - [x] 8.2 Write unit tests for `revlink restore` error recovery
    - Test MD5 mismatch: restored copy deleted, managed copy preserved, exit code 1
    - Test permission error on symlink unlink: error message, no copy attempted, exit code 1
    - Test permission error deleting managed copy: warning emitted, exit code 0
    - _Requirements: 4.2, 4.6, 5.2_

  - [x] 8.3 Write unit tests for `RestoreFormatter` output
    - Test each `RestoreFormatter` method produces the expected string
    - Test all methods produce `[dry-run]` prefix when `dry_run=True`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10_

- [x] 9. Write integration tests for `revlink restore`

  - [x] 9.1 Write integration tests — happy paths
    - Happy path file: symlink → `revlink restore` → real file, managed copy deleted, git exclude removed
    - Happy path directory: same for a directory tree
    - _Requirements: 4.3, 4.5, 5.1, 5.3, 5.6_

  - [x] 9.2 Write integration tests — error paths and config subpath removal
    - Dangling symlink: managed copy missing → error, CWD symlink untouched
    - Not a symlink: real file at path → error with `revlink create` suggestion
    - MD5 mismatch: restored copy deleted, managed copy preserved, error reported
    - Config subpath removal: entry removed from config when mapping uses selective sync
    - _Requirements: 3.2, 3.3, 4.6, 5.6_

- [x] 10. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Wave 0 (task 1) must complete before any other wave — the rename touches every subsequent file
- Property tests use Hypothesis with `@settings(max_examples=100)` and are tagged with `# Feature: revlink-subcommands, Property {N}: {text}`
- `RestoreOperation` follows the same standalone pattern as `CreateOperation` — no `CmdOperation` / `ProjectProcessor`
- `RevlinkContext` is reused by `RestoreOperation` unchanged — no rename needed

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "3.3"] },
    { "id": 3, "tasks": ["2.3"] },
    { "id": 4, "tasks": ["5.1", "5.2"] },
    { "id": 5, "tasks": ["5.3"] },
    { "id": 6, "tasks": ["5.4", "5.5"] },
    { "id": 7, "tasks": ["5.6"] },
    { "id": 8, "tasks": ["5.7", "7.1"] },
    { "id": 9, "tasks": ["7.2"] },
    { "id": 10, "tasks": ["8.1", "8.2", "8.3"] },
    { "id": 11, "tasks": ["9.1", "9.2"] }
  ]
}
```
