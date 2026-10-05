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
blf_dev daemon start
blf_dev link check
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
# Run all tests (parallel execution is default)
uv run pytest

# Run specific test categories
uv run pytest tests/unit/
uv run pytest tests/property/

# Run with coverage
uv run pytest --cov=beyond_local_file

# Run with verbose output
uv run pytest -v

# Override parallel execution (run sequentially)
uv run pytest -n 0
```

The suite is intended to pass on macOS, Linux, and Windows 10. Property tests share filters in `tests/path_strategies.py` so Hypothesis does not generate Windows-reserved names (`NUL`, `CON`, `COM1`, …). Ordinary copy projections do not need Developer Mode. On Windows, enable Developer Mode (or use an elevated shell) when a directory item contains nested symlink nodes, and before running leftover tests that still create symlink fixtures.

**Performance:** Tests run in parallel by default using `pytest-xdist` (`-n auto`), typically completing the full suite in ~60 seconds. To run sequentially, use `uv run pytest -n 0`.

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
│       ├── projection.py            # copy_projection
│       ├── sync_state.py            # Copy hash / baseline tracking
│       ├── git_manager.py           # Git exclude management
│       ├── project_processor.py     # Config loading and ProjectProcessor orchestrator
│       ├── operations/
│       │   ├── base.py              # CmdOperation ABC
│       │   ├── daemon.py            # daemon start|stop|status|logs|reload
│       │   ├── link_check.py        # CheckOperation + check formatters
│       │   ├── revlink.py           # revlink create / restore
│       │   └── remove.py            # remove operation
│       ├── daemon/                  # Runtime process, catch-up, live observe
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

## Projections

Every link is a physical copy (`copy_projection` in `projection.py`). Nested symlink nodes inside a directory item are copied as symlinks. A leftover blf symlink at the projection path becomes a copy on catch-up. There is no second projection mechanism and no strategy protocol.

Git exclude lives in `GitExcludeManager`. Catch-up and revlink call it directly.

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
