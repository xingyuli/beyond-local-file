# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** — Nested Path Git Exclude Execution
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - Add a new class `TestRevlinkGitExcludeNestedPath` in `tests/integration/test_revlink_integration.py`
  - Set up a temporary git repo with a selective-sync mapping; create a `docs/agent` directory as the source
  - Run `blf revlink create docs/agent` against the unfixed code
  - Assert that `docs/agent` appears in `.git/info/exclude` — this assertion WILL FAIL on unfixed code
  - Also add a sub-case for `--dry-run`: run `blf revlink create --dry-run docs/agent` and assert the output contains a git exclude message — this WILL FAIL on unfixed code
  - Also add a sub-case for `restore`: pre-populate `.git/info/exclude` with `docs/agent`, run `blf revlink restore docs/agent`, and assert `docs/agent` is NO LONGER in `.git/info/exclude` — this WILL FAIL on unfixed code
  - Run tests on UNFIXED code: `uv run pytest tests/integration/test_revlink_integration.py::TestRevlinkGitExcludeNestedPath -v`
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct — it proves the bug exists)
  - Document counterexamples found (e.g. "`.git/info/exclude` does not contain `docs/agent` after create")
  - Mark task complete when tests are written, run, and failures are documented
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** — Top-Level Path Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe on UNFIXED code: run `blf revlink create myfile.txt` in a git repo — verify `myfile.txt` appears in `.git/info/exclude`
  - Observe on UNFIXED code: run `blf revlink restore myfile.txt` — verify `myfile.txt` is removed from `.git/info/exclude`
  - Write property-based tests (using Hypothesis) that generate random valid top-level filenames (single-component, no slashes) and verify:
    - After `create <name>`, `<name>` appears in `.git/info/exclude`
    - After `restore <name>` (with pre-populated exclude entry), `<name>` is removed from `.git/info/exclude`
  - Write a unit test that verifies `context is None` silently skips the git exclude step without error (for both `CreateOperation` and `RestoreOperation`)
  - Run tests on UNFIXED code: `uv run pytest tests/integration/test_revlink_integration.py::TestRevlinkGitExcludeNestedPath -k preservation -v`
  - **EXPECTED OUTCOME**: Tests PASS (this confirms the baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 3. Fix for nested path git exclude skipped silently

  - [x] 3.1 Implement the fix in `src/beyond_local_file/operations/revlink.py`
    - In `CreateOperation._git_exclude_preview` (~line 719): add `if self.context is None: return` before the `GitExcludeManager` line, then replace `GitExcludeManager(self.source.parent)` with `GitExcludeManager(self.context.cwd)`
    - In `CreateOperation._git_exclude` (~line 762): add `if self.context is None: return 0` before the `GitExcludeManager` line, then replace `GitExcludeManager(self.source.parent)` with `GitExcludeManager(self.context.cwd)`
    - In `RestoreOperation._git_exclude` (~line 1013): add `if self.context is None: return 0` before the `GitExcludeManager` line, then replace `GitExcludeManager(self.source.parent)` with `GitExcludeManager(self.context.cwd)`
    - Update docstrings for all three methods to reflect that `context.cwd` is now used as the repository root
    - Run linting: `uv run ruff check --fix .` then `uv run ruff format .`
    - _Bug_Condition: isBugCondition(source) where len(source.relative_to(context.cwd).parts) > 1_
    - _Expected_Behavior: git exclude step executes using context.cwd, adding/removing/previewing the full relative path entry_
    - _Preservation: top-level paths, context is None paths, all non-git-exclude steps unchanged_
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4_

  - [x] 3.2 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** — Nested Path Git Exclude Execution
    - **IMPORTANT**: Re-run the SAME tests from task 1 — do NOT write new tests
    - Run: `uv run pytest tests/integration/test_revlink_integration.py::TestRevlinkGitExcludeNestedPath -v`
    - **EXPECTED OUTCOME**: Tests PASS (confirms the bug is fixed for nested paths)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.3 Verify preservation tests still pass
    - **Property 2: Preservation** — Top-Level Path Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run: `uv run pytest tests/integration/test_revlink_integration.py::TestRevlinkGitExcludeNestedPath -v`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions for top-level paths)
    - Confirm all tests pass after fix

- [x] 4. Checkpoint — Ensure all tests pass
  - Run the full test suite: `uv run pytest`
  - Ensure zero failures and zero linting violations (`uv run ruff check .`)
  - Ask the user if any questions arise
