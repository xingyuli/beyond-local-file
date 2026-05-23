# Requirements Document

## Introduction

The `revlink` command converts an existing file or directory in the current working directory into a managed symlink. Where `link sync` pushes symlinks from a managed project into target directories, `revlink` works in reverse: it takes a path that already exists in a target directory, copies it to the appropriate managed project location, verifies the copy via MD5 checksum, replaces the original with a symlink, and optionally records the item in `.git/info/exclude`. This lets users adopt existing files into the managed workflow without manual copy-delete-link steps.

## Glossary

- **BLF**: The `beyond-local-file` CLI tool (`blf`).
- **Managed_Project**: A directory tracked by BLF as the authoritative source of truth for a set of files (e.g. `~/my-local-files/my-project/`).
- **Target_Directory**: The working directory from which `revlink` is invoked — the project that currently owns the file.
- **Config**: The YAML configuration file resolved via `--config`, `~/.blfrc`, or the default `config.yml` in the current directory.
- **Revlink_Command**: The `blf revlink` CLI subcommand defined in this document.
- **Checksum_Verifier**: The component responsible for computing and comparing MD5 checksums of files and directories.
- **RevlinkOperation**: The internal class that orchestrates the copy-verify-replace workflow for a single path argument.
- **Git_Exclude_Manager**: The existing `GitExcludeManager` class in `git_manager.py` that reads and writes `.git/info/exclude`.

## Requirements

### Requirement 1: Command Registration and Invocation

**User Story:** As a developer, I want to invoke `blf revlink <path>` from my target project directory, so that I can convert an existing file or directory into a managed symlink with a single command.

#### Acceptance Criteria

1. THE Revlink_Command SHALL be registered as a top-level subcommand of the `blf` CLI group (not under the `link` subgroup).
2. THE Revlink_Command SHALL accept exactly one required positional argument: the path of the file or directory to convert.
3. THE Revlink_Command SHALL accept a `--dry-run` flag that, when set, previews all actions without modifying the filesystem.
4. THE Revlink_Command SHALL accept a `--force` flag that, when set, overwrites an existing destination in the managed project. MD5 checksum verification still applies.
5. THE Revlink_Command SHALL accept a `-c` / `--config` option (inherited from the CLI group context) to specify a custom config file path.
6. WHEN `blf revlink --help` is invoked, THE Revlink_Command SHALL display a concise description, the path argument, and all supported options.

---

### Requirement 2: Config Loading and Managed Project Resolution

**User Story:** As a developer, I want `revlink` to automatically determine the correct managed project location from my config, so that I do not have to specify the destination path manually.

#### Acceptance Criteria

1. WHEN `revlink` is invoked, THE Revlink_Command SHALL load the config using the same resolution order as other BLF commands: explicit `--config` flag, then `~/.blfrc`, then `config.yml` in the current directory.
2. WHEN the config is loaded, THE Revlink_Command SHALL identify the managed project whose target paths include the current working directory.
3. WHEN exactly one matching managed project is found, THE Revlink_Command SHALL use that project's `managed_project_path` as the destination root for the copy.
4. WHEN no managed project's target paths match the current working directory, THE Revlink_Command SHALL print a descriptive error message that includes suggestions for how to configure a matching project or use `--config` to specify the correct config file, and exit with a non-zero status code.
5. WHEN exactly one managed project's target paths match the current working directory, THE Revlink_Command SHALL proceed with the copy operation using that project's `managed_project_path`.
6. WHEN multiple managed projects' target paths match the current working directory, THE Revlink_Command SHALL print a descriptive error message listing the ambiguous projects and exit with a non-zero status code.
6. IF the config file cannot be loaded or does not exist, THEN THE Revlink_Command SHALL print a descriptive error message and exit with a non-zero status code.

---

### Requirement 3: Pre-flight Validation

**User Story:** As a developer, I want `revlink` to validate the input path before making any changes, so that I receive clear errors early and the filesystem is never left in a partial state.

#### Acceptance Criteria

1. WHEN the path argument does not exist in the current working directory, THE Revlink_Command SHALL print a descriptive error message and exit with a non-zero status code without modifying the filesystem.
2. WHEN the path argument is already a symlink, THE Revlink_Command SHALL print a descriptive error message indicating the path is already a symlink and exit with a non-zero status code without modifying the filesystem.
3. WHEN the destination path in the managed project already exists and `--force` is not set, THE Revlink_Command SHALL print a descriptive error message and exit with a non-zero status code without modifying the filesystem.
3a. WHEN the destination path in the managed project already exists and `--force` is set, THE Revlink_Command SHALL overwrite the existing destination with the current content of the source path.
4. WHEN `--dry-run` is active, THE Revlink_Command SHALL perform all validation checks and report what would happen, but SHALL NOT modify the filesystem.

---

### Requirement 4: Copy and Checksum Verification

**User Story:** As a developer, I want `revlink` to verify the integrity of the copy before replacing the original, so that I never lose data due to a failed or partial copy.

#### Acceptance Criteria

1. WHEN the pre-flight checks pass, THE Revlink_Command SHALL copy the source file or directory tree to the destination path in the managed project, preserving all file contents and directory structure.
2. WHEN the copy completes, THE Checksum_Verifier SHALL compute the MD5 checksum of the original source and the copy, then compare them.
3. WHEN the MD5 checksums match, THE Revlink_Command SHALL proceed to the replace step.
4. WHEN the MD5 checksums do not match, THE Revlink_Command SHALL delete the failed copy, leave the source file untouched, print a descriptive error message, and exit with a non-zero status code.
5. WHEN `--force` is set and the destination already exists, THE Revlink_Command SHALL overwrite it before copying, then apply MD5 verification as normal.
6. THE Checksum_Verifier SHALL compute a single MD5 digest that covers all file contents within a directory tree when the source is a directory, producing a deterministic result regardless of filesystem traversal order.

---

### Requirement 5: Symlink Replacement

**User Story:** As a developer, I want `revlink` to atomically replace the original file with a symlink pointing to the managed copy, so that my project continues to work without interruption.

#### Acceptance Criteria

1. WHEN the copy is verified (or `--force` is set), THE Revlink_Command SHALL remove the original file or directory from the target directory.
2. WHEN the original is removed, THE Revlink_Command SHALL create a symlink at the original path pointing to the managed project copy.
3. WHEN the symlink is created successfully, THE Revlink_Command SHALL print a confirmation message showing the symlink path and its target.
4. IF removing the original fails due to a permission error, THEN THE Revlink_Command SHALL print a descriptive error message and exit with a non-zero status code without modifying the filesystem further.
5. IF removing the original succeeds but creating the symlink fails, THEN THE Revlink_Command SHALL print a descriptive error message indicating the filesystem is in an inconsistent state (original removed, symlink not created) and exit with a non-zero status code.

---

### Requirement 6: Git Exclude Integration

**User Story:** As a developer, I want `revlink` to automatically add the converted item to `.git/info/exclude`, so that Git does not track the symlink in my target project.

#### Acceptance Criteria

1. WHEN the symlink is created and the target directory is inside a Git repository, THE Git_Exclude_Manager SHALL add the item name to `.git/info/exclude`.
2. WHEN the item name is already present in `.git/info/exclude`, THE Git_Exclude_Manager SHALL leave the file unchanged and report that the entry already exists.
3. WHEN the target directory is not inside a Git repository, THE Revlink_Command SHALL skip the git exclude step without error.
4. WHEN `--dry-run` is active, THE Revlink_Command SHALL report whether the item would be added to `.git/info/exclude` without modifying the file.

---

### Requirement 7: Output and Progress Reporting

**User Story:** As a developer, I want `revlink` to print clear, step-by-step progress messages, so that I can follow what the command is doing and understand the outcome.

#### Acceptance Criteria

1. WHEN `revlink` begins processing, THE Revlink_Command SHALL print a message indicating it is computing the checksum of the source path.
2. WHEN the copy starts, THE Revlink_Command SHALL print a message showing the source path and the destination managed project path.
3. WHEN checksum verification completes successfully, THE Revlink_Command SHALL print a confirmation message indicating the MD5 match.
4. WHEN the symlink is created, THE Revlink_Command SHALL print a confirmation message in the format: `✓ Symlink created: <path> -> <managed_path>`.
5. WHEN the git exclude entry is added, THE Revlink_Command SHALL print a confirmation message indicating the item was added to `.git/info/exclude`.
6. WHEN `--dry-run` is active, THE Revlink_Command SHALL prefix all output lines with a `[dry-run]` indicator so the user can distinguish preview output from real output.
7. WHEN `--force` is set, THE Revlink_Command SHALL print a warning message indicating that any existing managed copy will be overwritten.
