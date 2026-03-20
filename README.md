# Beyond Local File

A command-line tool for synchronizing and managing local development files across multiple projects.

## What is this?

In real-world development, you often need to share local development files (such as development
configurations, test scripts, HTTP client test files, etc.) across multiple projects, but you
don't want to commit these files to Git repositories. `beyond-local-file` uses symbolic links
to allow you to:

- Centrally manage local development files
- Use these files across multiple target projects
- Automatically add symbolic links to Git ignore lists
- Check synchronization status

## 🎬 Quick Demo

![Demo](demo/demo.gif)

*Watch beyond-local-file in action: install from GitHub, sync files, create symlinks, and manage Git excludes automatically.*

## Architecture: Tool and Data Separation

`beyond-local-file` follows a clean separation between the **tool** (code) and **managed projects** (data):

- **The tool** is the CLI application itself — installed once via `uvx` or `uv tool install`, lives in
  Python's site-packages, contains no user data.
- **Managed projects** are your directories containing the local development files you want to share —
  live wherever you choose, can be version-controlled separately, independent of the tool.

```
# Tool (installed via uvx)
~/.local/share/uv/tools/beyond-local-file/   # managed by uv

# Managed Projects (your data, separate repository)
~/my-dev-files/
├── config.yml
├── project-a/
│   └── test.http
└── project-b/
    └── dev-config.yml

# Target Projects (where symlinks are created)
~/workspace/project-a/
└── test.http -> ~/my-dev-files/project-a/test.http
```

## Installation

### Recommended: `uv tool install`

```bash
uv tool install git+https://github.com/xingyuli/beyond-local-file.git

# Update
uv tool install --force git+https://github.com/xingyuli/beyond-local-file.git
```

### Ephemeral: `uvx`

```bash
uvx --from git+https://github.com/xingyuli/beyond-local-file.git beyond-local-file --help
```

### `pipx`

```bash
pipx install git+https://github.com/xingyuli/beyond-local-file.git
```

For development setup, see [docs/development.md](docs/development.md).

## Quick Start

1. Create a `config.yml` in your managed projects directory:

```yaml
project-a:
  - /Users/username/workspace/project-a
  - /Users/username/workspace/project-a-fork

project-b: /Users/username/workspace/project-b
```

2. Sync symlinks:

```bash
cd ~/my-dev-files
beyond-local-file symlink sync
```

3. Check status:

```bash
beyond-local-file symlink check
```

## Configuration

The `config.yml` file maps project names to target paths. Three formats are supported:

### Simplified (string) — single target

```yaml
project-b: /Users/username/workspace/project-b
```

### Simplified (list) — multiple targets

```yaml
project-a:
  - /Users/username/workspace/project-a
  - /Users/username/workspace/project-a-fork
```

### Full format — selective subpaths

When you only want to sync specific files or subdirectories instead of everything in
the project directory, use the full dict format with `target` and `subpath`:

```yaml
project-c:
  target: /Users/username/workspace/project-c
  subpath:
    - .kiro/hooks
    - .vscode/settings.json
```

This creates symlinks only for the listed subpaths (e.g. `project-c/.kiro/hooks`)
rather than every top-level item in the project directory. Intermediate directories
are created automatically in the target.

The `target` key accepts a single path or a list, just like the simplified formats:

```yaml
project-c:
  target:
    - /Users/username/workspace/project-c
    - /Users/username/workspace/project-c-fork
  subpath:
    - .kiro/hooks
```

Use `beyond-local-file symlink sync` and `beyond-local-file symlink check` as usual —
the subpath feature works transparently with both commands.

For more configuration examples, see [docs/advanced-usage.md](docs/advanced-usage.md).

## Available Commands

| Command | Description |
|---------|-------------|
| `symlink sync [PROJECT]` | Create symlinks in target directories |
| `symlink check [PROJECT]` | Check symlink and Git exclude status |

For full option details and usage examples, see [docs/commands.md](docs/commands.md).

## Important Notes

- Symbolic links use absolute paths to ensure correct targeting from different locations
- Only use in local development environments; do not commit symbolic links to Git
- If you move the source file location, re-run `sync`
- The tool is designed to run from your managed projects directory

## Platform Support

Works on macOS, Linux, and Windows. See [docs/platform-support.md](docs/platform-support.md) for details.
Windows requires Developer Mode (Windows 10/11) or Administrator privileges.

## Contributing

See [docs/development.md](docs/development.md) for development setup and guidelines.

## License

MIT License — see the LICENSE file for details.
