# Development Guide

## Table of Contents

- [Development Installation](#development-installation)
  - [Method 1: Using uv run (Recommended)](#method-1-using-uv-run-recommended)
  - [Method 2: Using uvx with local path](#method-2-using-uvx-with-local-path)
  - [Method 3: Traditional virtual environment](#method-3-traditional-virtual-environment)
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

If you need to modify the tool code, clone the repository and use one of these methods:

### Method 1: Using `uv run` (Recommended)

```bash
git clone https://github.com/xingyuli/beyond-local-file.git
cd beyond-local-file

# Run directly from the tool repository
uv run beyond-local-file --help

# Run from your managed projects directory
cd /path/to/your/managed-projects
uv run --directory /path/to/beyond-local-file beyond-local-file link check
```

### Method 2: Using `uvx` with local path

```bash
git clone https://github.com/xingyuli/beyond-local-file.git

# Run from anywhere, pointing to local repository
uvx --from /path/to/beyond-local-file beyond-local-file --help

# Run from managed projects directory
cd /path/to/your/managed-projects
uvx --from /path/to/beyond-local-file beyond-local-file link sync
```

### Method 3: Traditional virtual environment

```bash
git clone https://github.com/xingyuli/beyond-local-file.git
cd beyond-local-file

# Create and activate virtual environment
uv venv
source .venv/bin/activate  # On macOS/Linux
# .venv\Scripts\activate   # On Windows

# Install in editable mode
uv pip install -e .

# Now the command is available in your PATH
beyond-local-file --help

# Run from managed projects directory
cd /path/to/your/managed-projects
beyond-local-file link check
```

**Note**: `uvx` creates its own isolated environments and won't see packages installed with `uv pip install -e .`. Use `uv run` or activate the virtual environment if you need the command available directly.

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
│       ├── __main__.py          # Entry point for python -m
│       ├── cli.py               # CLI interface
│       ├── config.py            # Configuration handling
│       ├── symlink.py           # Symlink operations
│       └── git_exclude.py       # Git exclude management
├── tests/
│   ├── unit/                    # Unit tests
│   ├── property/                # Property-based tests
│   └── conftest.py              # Pytest configuration
├── docs/
│   └── development.md           # This file
├── pyproject.toml               # Project configuration
└── README.md                    # User documentation
```

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
