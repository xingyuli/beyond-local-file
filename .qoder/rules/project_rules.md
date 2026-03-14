---
trigger: always_on
---

## Python Coding Standards

### 1. Environment & Tooling
All Python development **must** use `uv` exclusively for:
- Virtual environments
- Dependency management and installation
- Package publishing (if applicable)
- Running scripts, tests, linters, and formatters

**Command examples**:
- `uv add <package>`
- `uv add --dev ruff pytest`
- `uv run ruff check --fix .`
- `uv run python script.py`

No `pip`, `venv`, `poetry`, `conda`, or manual `python -m` calls outside of `uv` wrappers.

### 2. Code Quality & Maintainability
Code **must** follow these principles:
- **Martin Fowler's refactoring principles** — favor small, safe refactorings that preserve behavior
- Keep code **simple**, **readable**, and **self-documenting**
- Prioritize **expressiveness** and **maintainability** over cleverness
- Functions and classes should have **single responsibility**
- Avoid deep nesting, magic values, and unnecessary complexity

### 3. Linting & Formatting Enforcement
All code **must** pass the project's configured **Ruff** rules with **zero violations**.

- Configuration lives in `pyproject.toml` under `[tool.ruff]`
- Use auto-fixing where possible:  
  `uv run ruff check --fix .`  
  `uv run ruff format .`
- No commits are allowed with lint errors (enforce via pre-commit hook if possible)
- When Ruff flags a rule that conflicts with readability or project needs, document the deliberate decision (e.g. `# noqa: ANN001` with comment explaining why)

### 4. Documentation Standards
Every **public** class, function, method, and module **must** have a complete docstring.

Docstrings should:
- Be written from the **user/caller's perspective**
- Clearly describe **purpose** and **responsibilities**
- Document **parameters** (type, meaning, default, required/optional)
- Specify **return value** (type and semantics)
- List **possible exceptions** or important edge cases
- Avoid leaking **implementation details**

**Language requirement**:
- All documentation — including docstrings, inline comments, README files, steering documents, commit messages, and changelogs — **must be written in English**.

**Recommended style**:
- Use **Google** or **NumPy** style docstrings (consistent within the project)
- Keep them concise yet informative
- Use Markdown formatting inside docstrings where helpful (e.g., lists, code blocks)

Example (Google style):
```python
def process_data(path: str | Path, /, *, timeout: int = 30) -> dict[str, Any]:
    """Load and process configuration from the given path.

    Args:
        path: Path to the configuration file (str or Path object).
        timeout: Maximum time in seconds to wait for I/O operations.

    Returns:
        Dictionary containing the parsed and normalized configuration.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file contains invalid YAML.
        TimeoutError: If loading exceeds the timeout.
    """
```

### 5. Click CLI Docstrings

Click uses a command function's docstring as its `--help` text. Keep CLI command docstrings clean so the help output is readable.

**Rules**:
- **Do not include an `Args:` section** in Click command docstrings. Click arguments and options are already documented via `@click.argument` and the `help=` parameter of `@click.option` — duplicating them in the docstring clutters the `--help` output.
- The docstring should contain only a short summary line and, optionally, a longer description paragraph.

**Example**:
```python
@cli.command()
@click.argument("project_name", required=False)
@click.option("--verbose", is_flag=True, help="Enable verbose output.")
def deploy(project_name, verbose):  # noqa: ANN001 -- click injects args at runtime
    """Deploy the project to the target environment.

    Reads configuration from the default config file and deploys all
    configured targets unless a specific project name is provided.
    """
    ...
```

### 6. Fixed Option Values

All fixed sets of option values (e.g. output formats, modes, strategies) **must** be defined as `StrEnum` members in `src/beyond_local_file/options.py`. Magic strings for option values are not allowed anywhere else in the codebase.

**Rules**:
- Add a new `StrEnum` class to `options.py` for each distinct option category.
- Import and reference enum members everywhere — in `@click.option` definitions, operation classes, and any conditional logic.
- Use `[f.value for f in MyEnum]` to derive the `click.Choice` list from the enum, so the CLI stays in sync automatically.
- Coerce the raw Click string back to the enum at the CLI boundary: `MyEnum(raw_value)`.

**Example**:
```python
# options.py
from enum import StrEnum

class OutputFormat(StrEnum):
    TABLE = "table"
    VERBOSE = "verbose"

# cli.py
from .options import OutputFormat

@click.option(
    "--format", "output_format",
    type=click.Choice([f.value for f in OutputFormat]),
    default=OutputFormat.TABLE,
)
def check(output_format):
    operation = CheckOperation(OutputFormat(output_format))
```
