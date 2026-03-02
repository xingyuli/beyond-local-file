# Requirements Document

## Introduction

This document specifies the requirements for converting beyond-local-file from a mixed tool-and-data repository into a standalone uvx-installable CLI tool. The tool will be separated from managed project data, allowing users to install it independently via uvx and run it from any managed projects directory. This separation enables independent iteration of the tool while allowing users to maintain their managed projects in separate repositories.

## Glossary

- **Tool**: The beyond-local-file CLI application that manages symlinks and git exclude entries
- **Managed_Projects**: User-maintained directories containing local development files to be symlinked
- **Config_File**: YAML configuration file (config.yml) that maps managed project directories to target locations
- **Target_Location**: Destination directory where symlinks are created
- **uvx**: Python package execution tool that allows running CLI tools without explicit installation
- **Package_Metadata**: Python package configuration in pyproject.toml defining entry points and dependencies
- **Entry_Point**: Console script definition that makes the CLI command available after installation

## Requirements

### Requirement 1: Package Structure

**User Story:** As a tool maintainer, I want the tool code separated from managed projects data, so that I can version and distribute the tool independently.

#### Acceptance Criteria

1. THE Tool SHALL contain only Python source code, configuration files, and documentation
2. THE Tool SHALL NOT contain any managed projects directories (academy-broom, local-file, quvanai-server-old) in the distributed package
3. THE Tool SHALL organize Python modules in a src/beyond_local_file/ package structure suitable for distribution
4. THE Package_Metadata SHALL define "beyond-local-file" as the package name
5. THE Package_Metadata SHALL specify Python 3.13+ as the minimum required version
6. THE Tool SHALL follow the standard Python src-layout with all source code in src/beyond_local_file/ directory
7. THE Tool SHALL move all Python modules (cli.py, config.py, models.py, formatters.py, git_manager.py, project_processor.py, symlink_manager.py) from root into src/beyond_local_file/

### Requirement 2: CLI Entry Point

**User Story:** As a user, I want to run the tool using a simple command name, so that I can easily invoke it from any directory.

#### Acceptance Criteria

1. THE Entry_Point SHALL register "beyond-local-file" as the console script command in pyproject.toml [project.scripts] section
2. THE Entry_Point SHALL point to the main CLI function in src/beyond_local_file/cli.py
3. WHEN a user runs "uvx beyond-local-file", THE Tool SHALL execute the CLI interface
4. THE Tool SHALL support all existing subcommands (symlink sync, symlink check)
5. THE Tool SHALL accept the --config option to specify custom Config_File paths
6. THE Tool SHALL default to "config.yml" in the current working directory when no --config is specified

### Requirement 3: Working Directory Independence

**User Story:** As a user, I want to run the tool from my managed projects directory, so that I can manage symlinks without navigating to the tool's installation location.

#### Acceptance Criteria

1. WHEN the Tool is executed, THE Tool SHALL resolve all relative paths from the current working directory
2. WHEN a Config_File path is relative, THE Tool SHALL resolve it relative to the current working directory
3. WHEN a managed project path in Config_File is relative, THE Tool SHALL resolve it relative to the Config_File location
4. THE Tool SHALL NOT depend on being executed from its own installation directory

### Requirement 4: Configuration File Discovery

**User Story:** As a user, I want the tool to find my configuration file in the current directory, so that I don't need to specify the config path every time.

#### Acceptance Criteria

1. WHEN no --config option is provided, THE Tool SHALL look for "config.yml" in the current working directory
2. IF "config.yml" does not exist in the current directory, THEN THE Tool SHALL display an error message indicating the file was not found
3. WHEN --config is provided with a relative path, THE Tool SHALL resolve it relative to the current working directory
4. WHEN --config is provided with an absolute path, THE Tool SHALL use the path as-is

### Requirement 5: Path Resolution

**User Story:** As a user, I want paths in my config file to work correctly regardless of where the tool is installed, so that I can manage symlinks reliably.

#### Acceptance Criteria

1. WHEN a managed project path in Config_File is relative, THE Tool SHALL resolve it relative to the Config_File's directory location
2. WHEN a managed project path in Config_File is absolute, THE Tool SHALL use the path as-is
3. WHEN a target location path in Config_File is relative, THE Tool SHALL resolve it relative to the current working directory
4. WHEN a target location path in Config_File is absolute, THE Tool SHALL use the path as-is
5. THE Tool SHALL use pathlib.Path for all path operations to ensure cross-platform compatibility

### Requirement 6: Package Dependencies

**User Story:** As a user, I want all required dependencies installed automatically, so that the tool works immediately after installation.

#### Acceptance Criteria

1. THE Package_Metadata SHALL declare "pyyaml>=6.0" as a runtime dependency
2. THE Package_Metadata SHALL declare "click>=8.0" as a runtime dependency
3. WHEN the Tool is installed via uvx, THE Tool SHALL have all dependencies available
4. THE Tool SHALL NOT require manual dependency installation by users

### Requirement 7: Backward Compatibility

**User Story:** As an existing user, I want my current config files and workflows to continue working, so that I don't need to modify my setup.

#### Acceptance Criteria

1. THE Tool SHALL accept Config_File in the same YAML format as the current version
2. THE Tool SHALL support the same command syntax (symlink sync, symlink check)
3. THE Tool SHALL support the same command-line options (--config, --extra-exclude, project_name argument)
4. THE Tool SHALL produce the same output format as the current version
5. THE Tool SHALL maintain the same symlink creation and git exclude management behavior

### Requirement 8: Installation via uvx

**User Story:** As a user, I want to install the tool using uvx, so that I can use it without managing virtual environments manually.

#### Acceptance Criteria

1. WHEN a user runs "uvx beyond-local-file --help", THE Tool SHALL display help information
2. THE Tool SHALL be installable from a Git repository URL via uvx
3. THE Tool SHALL be installable from PyPI via uvx (when published)
4. THE Package_Metadata SHALL include all necessary build system configuration for installation

### Requirement 9: Module Organization

**User Story:** As a tool maintainer, I want the code organized as a proper Python package, so that it can be imported and distributed correctly.

#### Acceptance Criteria

1. THE Tool SHALL organize source code in a src/ directory containing the beyond_local_file/ package
2. THE Tool SHALL include an __init__.py file in the src/beyond_local_file/ package directory
3. THE Tool SHALL define the CLI entry point in src/beyond_local_file/cli.py
4. THE Package_Metadata SHALL configure hatchling to package src/beyond_local_file/ directory
5. THE Tool SHALL use relative imports within the package (e.g., "from .config import load_config")
6. THE Tool SHALL place all Python modules (cli.py, config.py, models.py, formatters.py, git_manager.py, project_processor.py, symlink_manager.py) inside src/beyond_local_file/
7. THE Tool SHALL NOT include root-level Python modules in the distributed package

### Requirement 10: Documentation Updates

**User Story:** As a new user, I want clear installation and usage instructions, so that I can start using the tool quickly.

#### Acceptance Criteria

1. THE Tool SHALL include a README.md with uvx installation instructions
2. THE Tool SHALL document the command syntax: "uvx beyond-local-file [command]"
3. THE Tool SHALL provide example usage showing execution from a managed projects directory
4. THE Tool SHALL explain the separation between tool and managed projects
5. THE Tool SHALL include a migration guide for existing users

### Requirement 11: Development Workflow

**User Story:** As a tool maintainer, I want to test changes locally before publishing, so that I can ensure quality.

#### Acceptance Criteria

1. THE Tool SHALL support local installation via "uv pip install -e ."
2. THE Tool SHALL support running tests via "uv run pytest" (when tests are added)
3. THE Tool SHALL support linting via "uv run ruff check"
4. THE Tool SHALL support formatting via "uv run ruff format"
5. THE Tool SHALL include development dependencies in a separate dependency group

### Requirement 12: Build System Configuration

**User Story:** As a tool maintainer, I want the build system properly configured, so that the package can be built and distributed correctly.

#### Acceptance Criteria

1. THE Package_Metadata SHALL use hatchling as the build backend
2. THE Package_Metadata SHALL configure hatchling to package the src/beyond_local_file/ directory
3. THE Package_Metadata SHALL NOT include individual Python files in the packages list
4. THE Package_Metadata SHALL define [project.scripts] section with "beyond-local-file" entry point
5. WHEN the package is built, THE Tool SHALL include all modules from src/beyond_local_file/ in the wheel
6. WHEN the package is built, THE Tool SHALL NOT include root-level Python files or managed project directories
