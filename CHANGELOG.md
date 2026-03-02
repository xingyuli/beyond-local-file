# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
