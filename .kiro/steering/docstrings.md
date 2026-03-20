---
inclusion: auto
fileMatchPattern: "src/beyond_local_file/**"
---

# Docstring Conventions

## General Rules

Every public class, function, method, and module must have a complete docstring using Google style.

Docstrings should:
- Describe purpose from the caller's perspective.
- Document parameters (type, meaning, default).
- Specify return value (type and semantics).
- List possible exceptions or important edge cases.
- Avoid leaking implementation details.

Example:
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
    """
```

## Click CLI Commands

Click uses the function docstring as `--help` text. Keep it clean:

- Do NOT include an `Args:` section — Click documents arguments/options via decorators and `help=` parameters.
- Use only a short summary line and optionally a longer description paragraph.

Example:
```python
@cli.command()
@click.argument("project_name", required=False)
@click.option("--verbose", is_flag=True, help="Enable verbose output.")
def deploy(project_name, verbose):  # noqa: ANN001 -- click injects args at runtime
    """Deploy the project to the target environment.

    Reads configuration from the default config file and deploys all
    configured targets unless a specific project name is provided.
    """
```
