---
trigger: always_on
---

# Project Rules

## 1. Environment & Tooling

All Python development must use `uv` exclusively. No `pip`, `venv`, `poetry`, `conda`, or manual `python -m` calls.

Common commands:
- `uv add <package>` / `uv add --dev <package>`
- `uv run ruff check --fix .` / `uv run ruff format .`
- `uv run pytest`
- `uv run python script.py`

## 2. Code Quality

- Follow Martin Fowler's refactoring principles — small, safe, behavior-preserving changes.
- Keep code simple, readable, and self-documenting.
- Single responsibility for functions and classes.
- Avoid deep nesting, magic values, and unnecessary complexity.

## 3. Linting & Formatting

All code must pass Ruff with zero violations. Configuration lives in `pyproject.toml` under `[tool.ruff]`.

- Auto-fix: `uv run ruff check --fix .` then `uv run ruff format .`
- When suppressing a rule, add a comment explaining why (e.g. `# noqa: ANN001 -- click injects args at runtime`).

## 4. Language

All files — code, documentation, configuration, scripts, and any generated content — must be written in English unless the user explicitly requests Chinese.

## 5. Fixed Option Values

All fixed sets of option values (output formats, modes, strategies) must be defined as `StrEnum` members in `src/beyond_local_file/options.py`. No magic strings elsewhere.

- Use `[f.value for f in MyEnum]` for `click.Choice` lists.
- Coerce raw Click strings back to the enum at the CLI boundary: `MyEnum(raw_value)`.
