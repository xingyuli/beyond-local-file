# Implementation Plan: uvx-installable-tool

## Overview

This plan transforms beyond-local-file from a mixed tool-and-data repository into a standalone, uvx-installable CLI tool. The implementation follows a phased approach: first creating the package structure, then migrating modules with updated imports, configuring the build system and entry points, implementing property-based tests for path resolution, and finally updating documentation. Each phase builds incrementally to ensure the tool remains functional throughout the transformation.

## Tasks

- [ ] 1. Create package structure and initialize package
  - [x] 1.1 Create src/beyond_local_file/ directory structure
    - Create src/ directory at repository root
    - Create beyond_local_file/ package directory inside src/
    - _Requirements: 1.3, 1.6, 9.1_
  
  - [x] 1.2 Create package __init__.py
    - Create src/beyond_local_file/__init__.py with package metadata
    - Define __version__ variable
    - _Requirements: 9.2_

- [ ] 2. Migrate modules to package structure
  - [x] 2.1 Move models.py to package with minimal changes
    - Copy models.py to src/beyond_local_file/models.py
    - Verify no external imports need updating (models.py has no internal imports)
    - _Requirements: 1.7, 9.6_
  
  - [x] 2.2 Move git_manager.py to package with minimal changes
    - Copy git_manager.py to src/beyond_local_file/git_manager.py
    - Verify no external imports need updating (git_manager.py has no internal imports)
    - _Requirements: 1.7, 9.6_
  
  - [x] 2.3 Move config.py to package and update imports
    - Copy config.py to src/beyond_local_file/config.py
    - No import changes needed (config.py has no internal imports)
    - _Requirements: 1.7, 9.5, 9.6_
  
  - [x] 2.4 Move symlink_manager.py to package and update imports
    - Copy symlink_manager.py to src/beyond_local_file/symlink_manager.py
    - Update imports: "from git_manager import" → "from .git_manager import"
    - Update imports: "from models import" → "from .models import"
    - _Requirements: 1.7, 9.5, 9.6_
  
  - [x] 2.5 Move formatters.py to package and update imports
    - Copy formatters.py to src/beyond_local_file/formatters.py
    - Update imports: "from models import" → "from .models import"
    - Update imports: "from symlink_manager import" → "from .symlink_manager import"
    - _Requirements: 1.7, 9.5, 9.6_
  
  - [x] 2.6 Move project_processor.py to package and update imports
    - Copy project_processor.py to src/beyond_local_file/project_processor.py
    - Update imports: "from config import" → "from .config import"
    - Update imports: "from formatters import" → "from .formatters import"
    - Update imports: "from models import" → "from .models import"
    - Update imports: "from symlink_manager import" → "from .symlink_manager import"
    - _Requirements: 1.7, 9.5, 9.6_
  
  - [x] 2.7 Move cli.py to package and update imports
    - Copy cli.py to src/beyond_local_file/cli.py
    - Update imports: "from project_processor import" → "from .project_processor import"
    - Update imports: "from symlink_manager import" → "from .symlink_manager import"
    - _Requirements: 1.7, 9.3, 9.5, 9.6_

- [ ] 3. Configure build system and entry points
  - [x] 3.1 Update pyproject.toml with package metadata
    - Set package name to "beyond-local-file"
    - Set Python version requirement to ">=3.13"
    - Add pyyaml>=6.0 and click>=8.0 as dependencies
    - _Requirements: 1.4, 1.5, 6.1, 6.2, 6.3_
  
  - [x] 3.2 Configure hatchling build backend
    - Set build-system.requires = ["hatchling"]
    - Set build-system.build-backend = "hatchling.build"
    - Configure [tool.hatch.build.targets.wheel] with packages = ["src/beyond_local_file"]
    - _Requirements: 12.1, 12.2, 12.3, 9.4_
  
  - [x] 3.3 Configure CLI entry point
    - Add [project.scripts] section to pyproject.toml
    - Define "beyond-local-file = beyond_local_file.cli:cli"
    - _Requirements: 2.1, 2.2, 12.4_
  
  - [x] 3.4 Add development dependencies group
    - Create [dependency-groups] section in pyproject.toml
    - Add dev group with ruff, pytest, hypothesis
    - _Requirements: 11.5_

- [ ] 4. Verify package installation and CLI functionality
  - [x] 4.1 Test local editable installation
    - Run "uv pip install -e ." from repository root
    - Verify beyond-local-file command is available
    - Verify "beyond-local-file --help" displays help
    - _Requirements: 11.1, 2.3, 8.1_
  
  - [x] 4.2 Test CLI commands and options
    - Verify "beyond-local-file symlink sync" command exists
    - Verify "beyond-local-file symlink check" command exists
    - Verify --config option is accepted
    - Verify project_name argument is accepted
    - _Requirements: 2.4, 2.5, 7.2, 7.3_
  
  - [x] 4.3 Test default config file discovery
    - Create test directory with config.yml
    - Run "beyond-local-file symlink check" without --config
    - Verify tool finds config.yml in current directory
    - _Requirements: 2.6, 4.1_

- [x] 5. Checkpoint - Ensure basic functionality works
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement property-based tests for path resolution
  - [x] 6.1 Set up property testing infrastructure
    - Create tests/property/ directory
    - Create tests/conftest.py with shared fixtures
    - Install hypothesis as dev dependency
    - _Requirements: Testing Strategy_
  
  - [x] 6.2 Write property test for config file path resolution
    - **Property 1: Config File Path Resolution**
    - **Validates: Requirements 3.2, 4.3**
    - Generate random relative config paths and CWD paths
    - Test that config path is resolved relative to CWD
    - Tag: "# Feature: uvx-installable-tool, Property 1: Config File Path Resolution"
  
  - [x] 6.3 Write property test for project path resolution
    - **Property 2: Project Path Resolution**
    - **Validates: Requirements 3.3, 5.1**
    - Generate random relative project paths and config file locations
    - Test that project path is resolved relative to config file directory
    - Tag: "# Feature: uvx-installable-tool, Property 2: Project Path Resolution"
    - **Note:** Implementation was fixed to resolve project paths relative to config file directory
  
  - [x] 6.4 Write property test for absolute path preservation
    - **Property 3: Absolute Path Preservation**
    - **Validates: Requirements 4.4, 5.2, 5.4**
    - Generate random absolute paths for configs, projects, and targets
    - Test that resolved path equals input path
    - Tag: "# Feature: uvx-installable-tool, Property 3: Absolute Path Preservation"
  
  - [x] 6.5 Write property test for target path resolution
    - **Property 4: Target Path Resolution**
    - **Validates: Requirements 5.3**
    - Generate random relative target paths and CWD paths
    - Test that target path is resolved relative to CWD
    - Tag: "# Feature: uvx-installable-tool, Property 4: Target Path Resolution"
  
  - [x] 6.6 Write property test for working directory independence
    - **Property 5: Working Directory Independence**
    - **Validates: Requirements 3.1, 3.4**
    - Generate random valid configs and execution directories
    - Test that tool loads config and resolves paths correctly from any directory
    - Tag: "# Feature: uvx-installable-tool, Property 5: Working Directory Independence"

- [x] 7. Write unit tests for package structure and metadata
  - [x] 7.1 Write tests for package structure validation
    - Test that built wheel contains only src/beyond_local_file/ package
    - Test that all modules exist in src/beyond_local_file/
    - Test that __init__.py exists in package
    - Test that root-level modules are excluded from package
    - _Requirements: 1.1, 1.2, 1.3, 1.7, 9.2, 9.6, 9.7, 12.6_
  
  - [x] 7.2 Write tests for metadata validation
    - Test package name is "beyond-local-file"
    - Test Python version requirement is ">=3.13"
    - Test pyyaml>=6.0 dependency
    - Test click>=8.0 dependency
    - Test hatchling build backend
    - Test entry point configuration
    - _Requirements: 1.4, 1.5, 6.1, 6.2, 12.1, 2.1, 2.2, 12.4_
  
  - [x] 7.3 Write tests for CLI functionality
    - Test "beyond-local-file --help" displays help
    - Test "symlink sync" and "symlink check" commands exist
    - Test --config option accepted
    - Test default config is "config.yml" in CWD
    - Test error message when config not found
    - _Requirements: 2.3, 8.1, 2.4, 7.2, 2.5, 7.3, 2.6, 4.1, 4.2_
  
  - [x] 7.4 Write tests for backward compatibility
    - Test existing config files work
    - Test same output format
    - Test same symlink behavior
    - _Requirements: 7.1, 7.4, 7.5_

- [x] 8. Update documentation
  - [x] 8.1 Update README.md with uvx installation instructions
    - Add section explaining uvx installation: "uvx beyond-local-file"
    - Add section explaining installation from git URL
    - Document command syntax: "uvx beyond-local-file [command]"
    - _Requirements: 10.1, 10.2, 8.2_
  
  - [x] 8.2 Add usage examples to README.md
    - Provide example showing execution from managed projects directory
    - Show example config.yml structure
    - Show example sync and check commands
    - _Requirements: 10.3_
  
  - [x] 8.3 Document tool/data separation in README.md
    - Explain separation between tool and managed projects
    - Explain that tool can be installed independently
    - Explain that managed projects can be in separate repositories
    - _Requirements: 10.4_
  
  - [x] 8.4 Add migration guide to README.md
    - Document steps for existing users to migrate
    - Explain that config files don't need changes
    - Explain new installation method
    - Provide troubleshooting tips
    - _Requirements: 10.5_

- [x] 9. Clean up root-level modules
  - [x] 9.1 Remove or archive root-level Python modules
    - Move root-level .py files to archive/ or delete them
    - Ensure only src/beyond_local_file/ contains Python modules
    - _Requirements: 1.1, 1.2, 9.7, 12.6_
  
  - [x] 9.2 Verify package build excludes managed projects
    - Build wheel with "uv build"
    - Inspect wheel contents to verify no managed project directories
    - Verify only src/beyond_local_file/ is included
    - _Requirements: 1.2, 12.5, 12.6_

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at key milestones
- Property tests validate universal correctness properties across all inputs
- Unit tests validate specific examples, edge cases, and error conditions
- The implementation maintains backward compatibility throughout
- All path operations use pathlib.Path for cross-platform compatibility
