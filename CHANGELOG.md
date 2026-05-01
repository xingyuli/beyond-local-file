# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.2] - 2026-05-01

### Added
- **Add --version option** — Added a `--version` global option to display the current version of the tool. Users can now quickly check their installed version with `blf --version`, which is especially important for PyPI installations where version verification is a standard expectation.

### Fixed
- **Fix symlink check to verify source path** — The `blf link check` command now verifies that symlinks point to the correct source path, not just that they exist. Previously, symlinks pointing to wrong sources would show as correct (✓) during check but trigger prompts during sync, creating confusion. Now incorrect symlinks are properly detected and reported during check operations.

### Changed
- **Refactor config and processing models** — Separated configuration models from processing models to eliminate workarounds in config loading. The config layer now purely reflects YAML grammar structure, while a new translation layer converts configurations into processing units. This eliminates synthetic project name suffixes at config load time and provides clearer semantics.
- **Unified protocol migration** — Completed comprehensive migration to unified protocol architecture across all operations. Introduced `OperationProgress` for tracking partial completion, created unified formatters (`LinkSyncFormatter`, `LinkCheckFormatter`) that handle both symlink and copy strategies, and established `link_strategy_protocol.py` as the single source of truth for all result types. Removed all legacy result types and formatters.

### Documentation
- **Enhance README with usage examples** — Added concrete usage examples and a detailed "How the author uses it" section showing real-world applications. The README now demonstrates practical use cases like syncing HTTP client files, AI agent hooks, and entire development environments across projects.
- **Add "Why not just use X?" section** — Added a dedicated section comparing `beyond-local-file` with alternatives like GNU Stow, chezmoi, and shell scripts. This proactive comparison helps users quickly understand the tool's specific niche versus dotfiles management.
- **Update documentation for unified protocol** — Updated all project documentation to reflect the unified protocol architecture, including comprehensive coverage of protocol types, design patterns, and implementation guidance.

### Removed
- **Remove legacy symlink subcommand** — Removed the hidden `symlink` subcommand alias that was kept for backward compatibility. Only the `link` command is now available (`blf link sync`, `blf link check`), simplifying the CLI codebase.

[0.2.2]: https://github.com/xingyuli/beyond-local-file/releases/tag/v0.2.2

## [0.2.1] - 2026-04-05

### Fixed
- **Fix inconsistent project numbering suffix** — When multiple target projects exist, numbering now consistently uses `#{seq}` format (1-based sequence) for all projects. Previously, the first project appeared without a suffix while others showed `#1`, creating confusion. All multi-target projects now display as `project#1`, `project#2`, etc., while single-target projects remain without suffix.
- **Fix config option placement** — Corrected test suite to reflect that `--config` is a global option at the root CLI level, not a command-specific option. Tests now properly verify the option appears in root help and use correct syntax: `blf --config custom.yml link sync`.
- **Fix mixed configuration support** — Added support for mixing simple string format with selective subpath format for a single source with multiple targets. Users can now define configurations where some targets sync everything (simple string) while others sync only specific subdirectories (dict with subpath).

### Documentation
- **Update CLI reference for v0.2.0** — Corrected CLI reference documentation to show `--config` as a global option rather than command-specific. All examples now demonstrate proper usage with global option placement before subcommands.
- **Add BNF configuration specification** — Added formal BNF (Backus-Naur Form) grammar specification to the configuration reference, providing a precise, unambiguous definition of the configuration format. This helps developers understand exact structure and valid combinations.
- **Improve configuration reference clarity** — Restructured configuration reference documentation to reflect the actual composable specification structure instead of presenting it as 5 separate formats. Documentation now clearly shows how mappings can be single or list, and each mapping can be simple string or dict with selective subpaths.

[0.2.1]: https://github.com/xingyuli/beyond-local-file/releases/tag/v0.2.1

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
