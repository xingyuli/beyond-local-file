"""Allow ``python -m beyond_local_file`` to run the CLI."""

from .cli import cli

if __name__ == "__main__":
    cli()
