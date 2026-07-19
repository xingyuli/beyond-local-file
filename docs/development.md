# Development Guide

## Table of Contents

- [Development Installation](#development-installation)
- [Running Tests](#running-tests)
- [Code Quality](#code-quality)
  - [Pre-commit Hooks](#pre-commit-hooks)
- [Building the Package](#building-the-package)
- [Project Structure](#project-structure)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Release Process](#release-process)
- [Contributing](#contributing)
- [Troubleshooting Development Issues](#troubleshooting-development-issues)
- [Getting Help](#getting-help)

This guide is for developers who want to contribute to or modify the `beyond-local-file` tool itself.

## Development Installation

If you need to modify the tool code, clone the repository and run it directly from the local source:

```bash
git clone https://github.com/xingyuli/beyond-local-file.git
cd beyond-local-file

# Run directly from the tool repository
uv run --no-cache beyond-local-file --help

# Run from your managed projects directory
cd /path/to/your/managed-projects
uv run --no-cache --project /path/to/beyond-local-file beyond-local-file link check
```

### Recommended: Create a Development Alias

For convenience, add this alias to your shell configuration (`~/.bashrc`, `~/.zshrc`, etc.):

```bash
alias blf_dev='uv run --no-cache --project /path/to/beyond-local-file beyond-local-file'
```

This mirrors the production alias pattern:

```bash
alias blf='beyond-local-file'      # production (installed via uv tool install)
alias blf_dev='uv run --no-cache --project /path/to/beyond-local-file beyond-local-file'  # development
```

With the alias configured, you can use `blf_dev` from any directory:

```bash
cd /path/to/your/managed-projects
blf_dev link check
blf_dev link sync
```

### Why This Approach?

- `--no-cache` ensures you always run the latest code from your local repository
- `--project` discovers the project without changing the working directory (preserves config path resolution)
- No installation or virtual environment activation required
- Clean output without build messages
- Works from any directory

### Installing Locally as a Tool (for testing installed behavior)

To test features that depend on the tool being properly installed — such as shell completion — install your local version as a `uv` tool:

```bash
uv tool install --editable /path/to/beyond-local-file
```

The `--editable` flag means the installed binary runs your current source code directly, so changes are reflected immediately without reinstalling. This behaves identically to `uv tool install beyond-local-file` from PyPI, just pointing at your local repo.

To uninstall when done:

```bash
uv tool uninstall beyond-local-file
```

## Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test categories
uv run pytest tests/unit/
uv run pytest tests/property/

# Run with coverage
uv run pytest --cov=beyond_local_file

# Run with verbose output
uv run pytest -v
```

## Code Quality

The project uses Ruff for linting and formatting. All code must pass these checks before committing.

```bash
# Check code with ruff
uv run ruff check .

# Auto-fix issues
uv run ruff check --fix .

# Format code
uv run ruff format .
```

### Pre-commit Hooks

The project uses pre-commit hooks to ensure code quality. Install them with:

```bash
uv run pre-commit install

# Run manually on all files
uv run pre-commit run --all-files
```

## Building the Package

```bash
# Build wheel and sdist
uv build

# Inspect wheel contents
unzip -l dist/beyond_local_file-*.whl

# Clean build artifacts
rm -rf dist/ build/ *.egg-info
```

## Project Structure

```
beyond-local-file/
├── src/
│   └── beyond_local_file/
│       ├── __init__.py
│       ├── __main__.py              # Entry point for python -m
│       ├── cli.py                   # CLI interface
│       ├── config.py                # Configuration handling
│       ├── options.py               # StrEnum definitions for CLI options
│       ├── link_strategy_protocol.py # Protocol definitions and result types
│       ├── symlink_manager.py       # Symlink strategy implementation
│       ├── copy_manager.py          # Copy strategy implementation
│       ├── sync_state.py            # Copy strategy state tracking
│       ├── git_manager.py           # Git exclude management
│       ├── project_processor.py     # Config loading and ProjectProcessor orchestrator
│       ├── operations/
│       │   ├── base.py              # CmdOperation ABC
│       │   ├── link_sync.py         # SyncOperation + LinkSyncFormatter
│       │   └── link_check.py        # CheckOperation + check formatters
│       └── model/
│           ├── config.py            # Config models (YAML structure)
│           ├── processing.py        # Processing models (execution)
│           └── translator.py        # Config → Processing translation
├── tests/
│   ├── unit/                        # Unit tests
│   ├── property/                    # Property-based tests
│   └── conftest.py                  # Pytest configuration
├── docs/
│   └── development.md               # This file
├── pyproject.toml                   # Project configuration
└── README.md                        # User documentation
```

## Implementing a New Link Strategy

To add a new link strategy (e.g., hard links, junctions), implement the `LinkStrategyManager` protocol:

### 1. Create Manager Class

```python
from beyond_local_file.link_strategy_protocol import (
    LinkStrategyManager,
    LinkCreateResult,
    LinkCheckResult,
    GitExcludeAddResult,
    GitExcludeCheckResult,
    OperationProgress,
)

class HardlinkManager:
    """Manages hard link operations."""
    
    def __init__(self, items: list[ProjectItem], target_path: Path):
        self.items = items
        self.target_path = target_path
        self.git_manager = GitExcludeManager(target_path)
    
    def get_managed_items(self) -> list[ProjectItem]:
        """Return managed items."""
        return self.items
    
    def create_links(self) -> LinkCreateResult:
        """Create hard links for all items."""
        result = LinkCreateResult(
            progress=OperationProgress(total_items=len(self.items))
        )
        
        for item in self.items:
            # Implementation here
            result.created.add(item.name)
            result.progress.completed_items += 1
        
        return result
    
    def check_links(self) -> LinkCheckResult:
        """Check hard link status."""
        result = LinkCheckResult()
        
        for item in self.items:
            # Implementation here
            if link_exists:
                result.exists.append(item.name)
            else:
                result.missing.append(item.name)
        
        return result
    
    def add_git_excludes(self) -> GitExcludeAddResult:
        """Add git exclude entries.
        
        PRECONDITION: Caller has verified target is in a git repository.
        """
        entries = {item.name for item in self.items}
        return self.git_manager.add_entries(entries)
    
    def check_git_excludes(self, all_valid_entries: set[str]) -> GitExcludeCheckResult:
        """Check git exclude status.
        
        PRECONDITION: Caller has verified target is in a git repository.
        """
        entries = {item.name for item in self.items}
        return self.git_manager.check_entries(entries, all_valid_entries)
```

### 2. Key Requirements

**Protocol Methods:**
- `get_managed_items()` — Return list of managed items
- `create_links()` — Create links, return `LinkCreateResult`
- `check_links()` — Check status, return `LinkCheckResult`
- `add_git_excludes()` — Add git excludes, return `GitExcludeAddResult | None`
- `check_git_excludes(all_valid_entries)` — Check git excludes, return `GitExcludeCheckResult | None`
- `is_git_repo()` — Return whether the target is a git repository root

**Progress Tracking:**
- Initialize `OperationProgress` with `total_items`
- Increment `completed_items` as work progresses
- Set `aborted=True` if user interrupts

**Git Repo Contract:**
- `add_git_excludes()` and `check_git_excludes()` return `None` when the target is not a git repository — no guards needed at call sites
- `is_git_repo()` is available on the protocol for callers that need to branch on repo presence (e.g. formatters printing "Target is not a git repository")
- Managers implement `is_git_repo()` by delegating to their internal `git_manager`
- `git_manager` is an internal implementation detail of each manager — not part of the protocol surface

**Result Types:**
- All result types come from `link_strategy_protocol.py`
- Use composition for strategy-specific details (optional)
- Define detail classes implementing `LinkCreateDetails` or `LinkCheckDetails` protocols

### 3. Strategy-Specific Details (Optional)

If your strategy needs additional information in results:

```python
from beyond_local_file.link_strategy_protocol import LinkCreateDetails

@dataclass
class HardlinkCreateDetails:
    """Hard link specific details."""
    
    inode_count: int = 0
    
    def get_summary(self) -> str:
        return f"Inodes created: {self.inode_count}"

# Use in create_links():
result = LinkCreateResult(
    created=created_items,
    details=HardlinkCreateDetails(inode_count=5),
    progress=OperationProgress(total_items=10, completed_items=10)
)
```

### 4. Integration

Update operations in `src/beyond_local_file/operations/` to partition items for your strategy and create your manager. Add a new module (e.g., `link_hardlink.py`) if your strategy introduces a new subcommand, or extend an existing operation module if it fits an existing command.

## Coding Standards

All code must follow the project's coding standards defined in `.qoder/rules/project_rules.md`:

- Use `uv` exclusively for all Python operations
- Follow Martin Fowler's refactoring principles
- Keep code simple, readable, and maintainable
- All public APIs must have complete docstrings
- Zero Ruff violations allowed
- All documentation in English

## Testing Guidelines

- Write unit tests for all new functionality
- Use property-based tests (Hypothesis) for complex logic
- Ensure all tests pass before submitting changes
- Aim for high code coverage (>80%)

## Release Process

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md (if exists)
3. Run all tests: `uv run pytest`
4. Run code quality checks: `uv run ruff check .`
5. Build package: `uv build`
6. Create git tag: `git tag v0.1.0`
7. Push to GitHub: `git push && git push --tags`
8. Publish to PyPI (if applicable): `uv publish`

## Contributing

When contributing to this project:

1. Fork the repository
2. Create a feature branch
3. Make your changes following the coding standards
4. Add tests for new functionality
5. Ensure all tests and quality checks pass
6. Submit a pull request

## Troubleshooting Development Issues

### Import errors

If you encounter import errors:
- Ensure you're in the correct virtual environment
- Reinstall in editable mode: `uv pip install -e .`
- Check that `src/beyond_local_file/__init__.py` exists

### Tests failing

If tests fail unexpectedly:
- Clear pytest cache: `rm -rf .pytest_cache`
- Clear hypothesis cache: `rm -rf .hypothesis`
- Ensure all dependencies are installed: `uv sync`

### Ruff errors

If Ruff reports errors:
- Try auto-fixing: `uv run ruff check --fix .`
- Format code: `uv run ruff format .`
- Check `pyproject.toml` for Ruff configuration

## Getting Help

- Check existing issues on GitHub
- Review the user documentation in README.md
- Examine test files for usage examples
- Open a new issue if you encounter problems
