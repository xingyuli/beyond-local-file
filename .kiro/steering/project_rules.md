---
inclusion: always
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

`src/beyond_local_file/options.py` is the single home for two kinds of user-facing option sets:

**CLI option values** — string values typed as flags or arguments (e.g. `--format table`). Define these as `StrEnum`.
- Use `[f.value for f in MyEnum]` for `click.Choice` lists.
- Coerce raw Click strings back to the enum at the CLI boundary: `MyEnum(raw_value)`.

**Interactive prompt choices** — numeric values presented as a numbered menu (e.g. `1-skip, 2-overwrite, 3-abort`). Define these as plain `Enum` with integer values.
- Use `[str(a.value) for a in MyEnum]` for `click.Choice` lists.
- Coerce the user's input back to the enum: `MyEnum(int(choice))`.

Internal enums that are never exposed to the user belong in the module that owns the concept — not in `options.py`. Examples:
- `SyncStatus` → `sync_state.py` (computed copy-sync state)
- `LinkStrategy` → `model/processing.py` (derived from YAML config, never a CLI option)
