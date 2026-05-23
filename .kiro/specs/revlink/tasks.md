# Implementation Plan: `revlink` Command

## Overview

Implement the `revlink` command as a standalone top-level `blf` subcommand. The work breaks into four main areas: the project resolver function, the core operation classes (`RevlinkOperation`, `ChecksumVerifier`, `RevlinkFormatter`), the CLI wiring, and the test suite. Each step builds on the previous and ends with everything wired together.

## Tasks

- [x] 1. Add `resolve_project_from_cwd` to `project_processor.py`
  - [x] 1.1 Implement `resolve_project_from_cwd(config_projects, cwd)` in `project_processor.py`
    - Iterate all `ConfigProject` instances and collect those whose `Mapping.targets` contain `cwd`
    - Return `ConfigProject` for exactly one match, `None` for no match, `list[ConfigProject]` for multiple matches
    - Add Google-style docstring documenting the union return type and each branch
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 1.2 Write property test for `resolve_project_from_cwd` — Property 1: unique match
    - **Property 1: Project resolver returns the unique matching project**
    - **Validates: Requirements 2.2, 2.3, 2.5**
    - Use `hypothesis` `st.builds` to generate arbitrary `ConfigProject` lists with random `Path` targets
    - Assert the function returns the single matching `ConfigProject` when exactly one project contains `cwd`

  - [x] 1.3 Write property test for `resolve_project_from_cwd` — Property 2: no match
    - **Property 2: Project resolver signals no-match correctly**
    - **Validates: Requirements 2.4**
    - Generate `ConfigProject` lists where `cwd` does not appear in any mapping's targets
    - Assert the function returns `None`

  - [x] 1.4 Write property test for `resolve_project_from_cwd` — Property 3: ambiguous match
    - **Property 3: Project resolver signals ambiguity correctly**
    - **Validates: Requirements 2.6**
    - Generate `ConfigProject` lists where two or more projects share the same target path
    - Assert the function returns a list containing all matching projects

- [x] 2. Implement `ChecksumVerifier` and `RevlinkFormatter` in `operations/revlink.py`
  - [x] 2.1 Create `operations/revlink.py` with `ChecksumVerifier` class
    - Implement `ChecksumVerifier.compute(path: Path) -> str` as a `@staticmethod`
    - For files: MD5 of file contents
    - For directories: MD5 of sorted `(relative_path_str + file_bytes)` concatenation using `path.rglob("*")`
    - Add Google-style docstring
    - _Requirements: 4.2, 4.6_

  - [x] 2.2 Write property test for `ChecksumVerifier` — Property 4: determinism
    - **Property 4: Checksum verifier is deterministic for directory trees**
    - **Validates: Requirements 4.6**
    - Use `tmp_path` with `hypothesis` `st.binary()` and `st.lists(st.text())` to generate random file trees
    - Assert `ChecksumVerifier.compute` returns the same digest on two consecutive calls

  - [x] 2.3 Write property test for `ChecksumVerifier` — Property 5: copy identity
    - **Property 5: Checksum verifier produces matching digests for identical content**
    - **Validates: Requirements 4.2, 4.6**
    - Generate random file trees in `tmp_path`, copy with `shutil.copy2` / `shutil.copytree`
    - Assert `ChecksumVerifier.compute(original) == ChecksumVerifier.compute(copy)`

  - [x] 2.4 Implement `RevlinkFormatter` in `operations/revlink.py`
    - Add `dry_run: bool` constructor parameter; prefix all output with `[dry-run]` when active
    - Implement all formatter methods: `computing_checksum`, `copying`, `checksum_ok`, `symlink_created`, `git_exclude_added`, `git_exclude_exists`, `force_warning`, `error`
    - Add Google-style docstrings to the class and each method
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [x] 3. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement `RevlinkOperation` in `operations/revlink.py`
  - [x] 4.1 Define `RevlinkOperation` dataclass and `_validate()` step
    - Define `@dataclass` with fields: `source`, `dest_root`, `dry_run`, `force`, `formatter`
    - Derive `dest` as `dest_root / source.name` inside `run()`
    - Implement `_validate()`: check source exists, source is not a symlink, dest does not exist (unless `--force`)
    - Return exit code 1 with appropriate `formatter.error()` call on each failure
    - Add Google-style docstrings
    - _Requirements: 3.1, 3.2, 3.3, 3.3a_

  - [x] 4.2 Implement `_copy()` step in `RevlinkOperation`
    - Use `shutil.copy2` for files, `shutil.copytree` for directories
    - If `--force` and dest exists, remove it before copying (`shutil.rmtree` / `Path.unlink`)
    - Call `formatter.force_warning(dest)` when `--force` is active
    - Call `formatter.copying(source, dest)` before the copy
    - _Requirements: 4.1, 4.5, 7.2, 7.7_

  - [x] 4.3 Implement `_verify()` step in `RevlinkOperation`
    - Call `formatter.computing_checksum(source)` before computing
    - Compute `ChecksumVerifier.compute(source)` and `ChecksumVerifier.compute(dest)`
    - On mismatch: delete the copy, call `formatter.error(...)`, return 1
    - On match: call `formatter.checksum_ok()`
    - _Requirements: 4.2, 4.3, 4.4, 7.1, 7.3_

  - [x] 4.4 Implement `_replace()` step in `RevlinkOperation`
    - Remove source with `shutil.rmtree` (dir) or `Path.unlink` (file); catch `PermissionError`
    - Create symlink with `source.symlink_to(dest)`; catch any `OSError`
    - Call `formatter.symlink_created(source, dest)` on success
    - Emit appropriate error messages for permission failure and inconsistent-state failure
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 7.4_

  - [x] 4.5 Implement `_git_exclude()` step and `run()` orchestration in `RevlinkOperation`
    - In `_git_exclude()`: instantiate `GitExcludeManager(source.parent)`, check `is_git_repo()`, call `write_entries({source.name})`
    - Call `formatter.git_exclude_added` or `formatter.git_exclude_exists` based on the result
    - In `run()`: call steps in order (`_validate`, `_copy`, `_verify`, `_replace`, `_git_exclude`), skip filesystem steps when `dry_run=True`, return 0 on success
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.5_

  - [x] 4.6 Write property test for `RevlinkOperation` — Property 6: dry-run filesystem invariant
    - **Property 6: Dry-run never modifies the filesystem**
    - **Validates: Requirements 3.4, 6.4**
    - Generate random valid source paths in `tmp_path` using Hypothesis
    - Snapshot the directory tree before and after invoking `RevlinkOperation` with `dry_run=True`
    - Assert the snapshots are identical

- [x] 5. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Wire `revlink` into `cli.py` and `operations/__init__.py`
  - [x] 6.1 Register `RevlinkOperation` export in `operations/__init__.py`
    - Add `from .revlink import RevlinkOperation` and include it in `__all__`
    - _Requirements: 1.1_

  - [x] 6.2 Add `revlink` Click command to `cli.py`
    - Register as `@cli.command()` (top-level, not under `link` group)
    - Accept positional `path` argument, `--dry-run` flag, `--force` flag
    - Resolve `source` as `Path(path).resolve()`; call `load_config_projects`, `resolve_project_from_cwd`, then `RevlinkOperation(...).run()`
    - Emit correct error messages for no-match and ambiguous-match resolver results; call `ctx.exit(1)` on failure
    - Add Click-style docstring (no `Args:` section per steering rules)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.4, 2.6, 2.7_

- [x] 7. Write unit tests for `revlink`
  - [x] 7.1 Write unit tests for CLI wiring and pre-flight validation
    - Test `revlink` is registered as a top-level command; `--help` shows path, `--dry-run`, `--force`
    - Test each pre-flight error: non-existent path, already-a-symlink, dest exists without `--force`
    - Test `--force` allows overwrite
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 3.1, 3.2, 3.3, 3.3a_

  - [x] 7.2 Write unit tests for MD5 mismatch recovery and permission errors
    - Test MD5 mismatch: failed copy is deleted, source is untouched, exit code 1
    - Test permission error on remove: correct error message, no further changes
    - Test symlink creation failure: inconsistent-state error message, exit code 1
    - _Requirements: 4.3, 4.4, 5.4, 5.5_

  - [x] 7.3 Write unit tests for git exclude integration and output formatting
    - Test entry added when in git repo; skipped when not in git repo; idempotent when already present
    - Test each `RevlinkFormatter` method produces the expected string with and without `[dry-run]` prefix
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [x] 8. Write integration tests for `revlink`
  - [x] 8.1 Write end-to-end integration tests
    - Happy path: file in a temp git repo → `revlink` → symlink created, git exclude updated
    - Directory tree: directory → `revlink` → symlink created
    - `--force` end-to-end: existing destination overwritten, symlink created
    - Config resolution: `--config` flag, `~/.blfrc`, default `config.yml` all resolve correctly
    - _Requirements: 1.5, 4.1, 4.5, 5.2, 5.3, 6.1_

- [x] 9. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- `revlink` does **not** use `CmdOperation` / `ProjectProcessor` — it has its own standalone execution path
- Property tests use Hypothesis with `@settings(max_examples=100)` and are tagged with `# Feature: revlink, Property {N}: {text}`
- Checkpoints ensure incremental validation at natural boundaries

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "2.1", "2.4"] },
    { "id": 2, "tasks": ["2.2", "2.3", "4.1"] },
    { "id": 3, "tasks": ["4.2", "4.3"] },
    { "id": 4, "tasks": ["4.4"] },
    { "id": 5, "tasks": ["4.5", "4.6"] },
    { "id": 6, "tasks": ["6.1"] },
    { "id": 7, "tasks": ["6.2"] },
    { "id": 8, "tasks": ["7.1", "7.2", "7.3"] },
    { "id": 9, "tasks": ["8.1"] }
  ]
}
```
