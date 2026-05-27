# Requirements Document

## Introduction

This document covers the evolution of `blf revlink` from a flat command into a subcommand group. The change introduces `blf revlink create <path>` (a rename of the existing command with no behavioral change) and `blf revlink restore <path>` (the exact inverse operation: dissolves a managed symlink and recovers the real file from the managed location). It also adds `ConfigUpdater.remove_subpath_entry()` as the counterpart to the existing `add_subpath_entry()`, and renames the internal classes `RevlinkOperation` → `CreateOperation` and `RevlinkFormatter` → `CreateFormatter`.

## Glossary

- **BLF**: The `beyond-local-file` CLI tool (`blf`).
- **Revlink_Group**: The `blf revlink` Click group defined in this document.
- **Create_Command**: The `blf revlink create` subcommand — identical to the former `blf revlink` command.
- **Restore_Command**: The `blf revlink restore` subcommand — the exact inverse of `create`.
- **CreateOperation**: The renamed `RevlinkOperation` class in `operations/revlink.py`.
- **CreateFormatter**: The renamed `RevlinkFormatter` class in `operations/revlink.py`.
- **RestoreOperation**: The new operation class that orchestrates the restore workflow.
- **RestoreFormatter**: The new formatter class for restore-specific output messages.
- **Config_Updater**: The `ConfigUpdater` class in `config.py`.
- **Git_Exclude_Manager**: The existing `GitExcludeManager` class in `git_manager.py`.
- **Managed_Copy**: The real file or directory stored in the managed project path (the symlink target).
- **CWD_Path**: The path in the current working directory that is currently a symlink pointing to the Managed_Copy.
- **RevlinkContext**: The existing dataclass grouping config-resolution context; reused by both `CreateOperation` and `RestoreOperation`.

## Requirements

### Requirement 1: CLI Restructuring — `revlink` Becomes a Group

**User Story:** As a developer, I want `blf revlink` to be a subcommand group, so that `create` and `restore` are clearly distinct operations with their own help text and options.

#### Acceptance Criteria

1. THE Revlink_Group SHALL be registered as a top-level Click group under the `blf` CLI (not under the `link` subgroup).
2. THE Revlink_Group SHALL expose two subcommands: `create` and `restore`.
3. THE Create_Command SHALL accept one required positional argument (the path), a `--dry-run` flag, and a `--force` flag.
4. THE Restore_Command SHALL accept one required positional argument (the path) and a `--dry-run` flag. THE Restore_Command SHALL NOT accept a `--force` flag.
5. WHEN `blf revlink --help` is invoked, THE Revlink_Group SHALL display the group description and list both `create` and `restore` subcommands.
6. WHEN `blf revlink create --help` is invoked, THE Create_Command SHALL display its description and all supported options.
7. WHEN `blf revlink restore --help` is invoked, THE Restore_Command SHALL display its description and all supported options.

---

### Requirement 2: `revlink create` — Rename with No Behavioral Change

**User Story:** As a developer, I want `blf revlink create <path>` to behave exactly like the former `blf revlink <path>`, so that my existing workflow is unaffected.

#### Acceptance Criteria

1. THE Create_Command SHALL behave identically to the former `blf revlink` command in all respects: config loading, project resolution, pre-flight validation, copy, MD5 verification, symlink replacement, git exclude update, and config subpath update.
2. THE codebase SHALL rename `RevlinkOperation` to `CreateOperation` in `operations/revlink.py`, `operations/__init__.py`, `cli.py`, and all test files that reference it.
3. THE codebase SHALL rename `RevlinkFormatter` to `CreateFormatter` in `operations/revlink.py`, `cli.py`, and all test files that reference it.
4. THE `operations/__init__.py` SHALL export `CreateOperation` (replacing the former `RevlinkOperation` export) and update `__all__` accordingly.
5. WHEN `blf revlink create <path>` is invoked, THE Create_Command SHALL resolve the managed project from the current working directory using the same logic as the former `revlink` command.

---

### Requirement 3: `revlink restore` — Validation

**User Story:** As a developer, I want `revlink restore` to validate the path before making any changes, so that I receive clear errors early and the filesystem is never left in a partial state.

#### Acceptance Criteria

1. WHEN the path argument does not exist, THE Restore_Command SHALL print a descriptive error message and exit with a non-zero status code without modifying the filesystem.
2. WHEN the path argument exists but is not a symlink, THE Restore_Command SHALL print a descriptive error message suggesting `revlink create` instead, and exit with a non-zero status code without modifying the filesystem.
3. WHEN the path is a symlink but its target (the Managed_Copy) does not exist, THE Restore_Command SHALL print a descriptive error message indicating a dangling symlink, and exit with a non-zero status code without modifying the filesystem.
4. WHEN `--dry-run` is active, THE Restore_Command SHALL perform all validation checks and report what would happen, but SHALL NOT modify the filesystem.

---

### Requirement 4: `revlink restore` — Copy Back and Verify

**User Story:** As a developer, I want `revlink restore` to copy the managed file back to my project and verify its integrity, so that I never lose data during the restore.

#### Acceptance Criteria

1. WHEN validation passes, THE RestoreOperation SHALL remove the symlink at the CWD_Path using `Path.unlink()` — never `shutil.rmtree()` — before copying the Managed_Copy back.
2. WHEN removing the symlink fails due to a permission error, THE RestoreOperation SHALL print a descriptive error message and exit with a non-zero status code without copying any files.
3. WHEN the symlink is removed, THE RestoreOperation SHALL copy the Managed_Copy to the CWD_Path using `shutil.copy2` for files and `shutil.copytree` for directories.
4. WHEN the copy completes, THE RestoreOperation SHALL compute the MD5 checksum of the Managed_Copy and the restored CWD_Path and compare them.
5. WHEN the MD5 checksums match, THE RestoreOperation SHALL proceed to delete the Managed_Copy.
6. WHEN the MD5 checksums do not match, THE RestoreOperation SHALL delete the restored CWD_Path, leave the Managed_Copy untouched, print a descriptive error message, and exit with a non-zero status code.

---

### Requirement 5: `revlink restore` — Cleanup

**User Story:** As a developer, I want `revlink restore` to clean up the managed copy, git exclude entry, and config subpath entry after a successful restore, so that the managed project is left in a consistent state.

#### Acceptance Criteria

1. WHEN the MD5 checksums match, THE RestoreOperation SHALL attempt to delete the Managed_Copy.
2. WHEN deleting the Managed_Copy fails (e.g. permission error), THE RestoreOperation SHALL print a warning message and continue — the restore to CWD has already succeeded and this failure is non-fatal.
3. WHEN the restore succeeds and the CWD_Path is inside a Git repository, THE Git_Exclude_Manager SHALL remove the item name from `.git/info/exclude`.
4. WHEN the item name is not present in `.git/info/exclude`, THE Git_Exclude_Manager SHALL silently skip the removal without error.
5. WHEN the CWD_Path is not inside a Git repository, THE Restore_Command SHALL skip the git exclude step without error.
6. WHEN the restore succeeds and the matched mapping uses selective sync (has a `subpath` list), THE Config_Updater SHALL remove the item name from the config subpath list.
7. WHEN the item name is not present in the config subpath list, THE Config_Updater SHALL perform no update and return without error.

---

### Requirement 6: `ConfigUpdater.remove_subpath_entry` — New Config API

**User Story:** As a developer, I want `ConfigUpdater` to support removing a subpath entry, so that `revlink restore` can undo the config change made by `revlink create`.

#### Acceptance Criteria

1. THE Config_Updater SHALL expose a `remove_subpath_entry(project_name, cwd, entry_name)` method that removes `entry_name` from the subpath list of the mapping that targets `cwd`.
2. WHEN the matched mapping has no `subpath` key, THE Config_Updater SHALL return `False` without modifying the file.
3. WHEN `entry_name` is not present in the subpath list, THE Config_Updater SHALL return `False` without modifying the file.
4. WHEN `entry_name` is present as a plain string in the subpath list, THE Config_Updater SHALL remove it, write the file, and return `True`.
5. WHEN `entry_name` is present as a `{"path": entry_name, ...}` dict in the subpath list, THE Config_Updater SHALL remove that dict entry, write the file, and return `True`.
6. WHEN the subpath list becomes empty after removal, THE Config_Updater SHALL leave the empty list in place — it SHALL NOT remove the `subpath` key, as doing so would change the mapping semantics from selective sync to sync-all.
7. THE Config_Updater SHALL preserve all YAML comments, blank lines, and indentation when writing the updated file (using `ruamel.yaml` round-trip editing, consistent with `add_subpath_entry`).

---

### Requirement 7: Output and Progress Reporting for `revlink restore`

**User Story:** As a developer, I want `revlink restore` to print clear, step-by-step progress messages, so that I can follow what the command is doing and understand the outcome.

#### Acceptance Criteria

1. WHEN the symlink is being removed, THE RestoreFormatter SHALL print a message indicating the symlink is being removed.
2. WHEN the copy back begins, THE RestoreFormatter SHALL print a message showing the source (Managed_Copy) and destination (CWD_Path).
3. WHEN checksum computation begins, THE RestoreFormatter SHALL print a message indicating the checksum is being computed.
4. WHEN checksum verification succeeds, THE RestoreFormatter SHALL print a confirmation message.
5. WHEN the Managed_Copy is deleted successfully, THE RestoreFormatter SHALL print a confirmation message.
6. WHEN the Managed_Copy deletion fails, THE RestoreFormatter SHALL print a warning message (non-fatal).
7. WHEN the git exclude entry is removed, THE RestoreFormatter SHALL print a confirmation message.
8. WHEN the git exclude entry is not found, THE RestoreFormatter SHALL print an informational message.
9. WHEN the config subpath entry is removed, THE RestoreFormatter SHALL print a confirmation message.
10. WHEN `--dry-run` is active, THE Restore_Command SHALL prefix all output lines with `[dry-run]` so the user can distinguish preview output from real output.
