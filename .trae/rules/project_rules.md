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
