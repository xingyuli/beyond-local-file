# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-04-04

### Added
- **Subpath symlink mapping** — Support creating symlinks from a subdirectory of a managed project to a subdirectory of a target project, enabling fine-grained control over which paths are linked instead of linking entire top-level directories.
- **Single file copy to target project** — Support copying single files as physical copies instead of symlinks to address edge cases where tools don't recognize symlinks (e.g., Kiro steering files). This is intentionally limited to single files to keep symlinks as the primary workflow.

### Changed
- **Optimize overwrite prompt** — Improved the overwrite prompt to show detailed information about existing links, displaying both the expected state and actual state for better decision-making.
- **Table format output for symlink check** — Converted the check command output to a clean table format, making it easier to scan status across multiple projects and reducing visual clutter.
- **Make --config a global option** — Moved the --config option from command-specific level to the root level, following standard CLI conventions and making it more discoverable.
- **Refactor manager responsibilities for link strategy separation** — Introduced a `LinkStrategyManager` protocol to cleanly separate symlink and copy manager responsibilities, eliminating cross-manager knowledge pollution and improving adherence to SOLID principles.
- The `symlink` subcommand has been renamed to `link` to reflect broader scope (both symlinks and copies), with `symlink` kept as a hidden alias for backward compatibility.

### Documentation
- **README update - alias recommendation** — Added recommendation to alias `beyond-local-file` as `blf` for easier usage.
- **Update development installation docs** — Simplified development installation documentation to use a single recommended method with `uv run --project --no-cache`, eliminating confusion from multiple approaches.
- **Update documentation to reflect file copy feature** — Updated project documentation to explain the new file copy feature, when to use copy vs symlink, scope limitations, and configuration options.
- **Update demo tape** — Updated the demo tape to use current CLI syntax (`link` instead of `symlink`) and accurate terminology reflecting that the tool supports both symlinks and file copies.

### Notes
- One bug fix task was marked as "Won't Fix" (config path resolution with uv run) as the issue was resolved by using `uv run --project` instead of `uv run --directory`.

[0.2.0]: https://github.com/xingyuli/beyond-local-file/releases/tag/v0.2.0

## [0.1.0] - 2026-03-02

### Added
- Initial release of beyond-local-file
- CLI tool for managing symlinks across multiple projects
- Support for synchronizing local development files to target projects
- Automatic Git exclude file management
- Configuration via YAML files
- Commands: `symlink sync` and `symlink check`
- Support for single and multiple target paths per project
- Interactive prompts for handling existing files
- Comprehensive test suite with unit and property-based tests
- Full documentation in README and development guide

### Features
- Symlink creation with absolute paths
- Automatic `.git/info/exclude` entry management
- Path resolution relative to config file and working directory
- Support for both files and directories
- Conflict handling with user prompts (skip/overwrite/abort)
- Status checking for symlinks and Git exclude entries
- Project filtering by name
- Custom config file path support

[0.1.0]: https://github.com/xingyuli/beyond-local-file/releases/tag/v0.1.0
