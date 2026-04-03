# Beyond Local File

A command-line tool for synchronizing and managing local development files across multiple projects.

## Table of Contents

- [What is this?](#what-is-this)
- [Architecture: Tool and Data Separation](#architecture-tool-and-data-separation)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Available Commands](#available-commands)
- [Documentation](#documentation)
- [Important Notes](#important-notes)
- [Platform Support](#platform-support)
- [Contributing](#contributing)
- [License](#license)

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

## Recommended: Create an Alias

The command name `beyond-local-file` is long. For convenience, create an alias:

```bash
# Add to your ~/.bashrc, ~/.zshrc, or equivalent
alias blf='beyond-local-file'
```

This documentation uses `blf` in all examples.

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
blf link sync
```

3. Check status:

```bash
blf link check
```

## Configuration

The `config.yml` file maps project names to target paths. Four formats are supported:

### 1. Simple string — single target

```yaml
project-a: /Users/username/workspace/project-a
```

### 2. Simple list — multiple targets

```yaml
project-b:
  - /Users/username/workspace/project-b
  - /Users/username/workspace/project-b-fork
```

### 3. Selective subpaths — sync specific items only

```yaml
project-c:
  target: /Users/username/workspace/project-c
  subpath:
    - .kiro/hooks
    - .vscode/settings.json
```

Only the listed subpaths are synced. Intermediate directories are created automatically.

### 4. Copy strategy — physical files for tool compatibility

Some tools don't recognize symlinks. Use `copy: true` for files that must be physical:

```yaml
project-d:
  target: /Users/username/workspace/project-d
  subpath:
    - .kiro/hooks                    # symlink (default)
    - path: .kiro/steering/rules.md  # physical copy
      copy: true
```

**Copy behavior:** Bidirectional sync with conflict detection. Changes in either location are detected and can be synced.

**Limitation:** Copy mode only supports single files, not directories. This is intentional — symlinks remain the primary workflow.

**Multiple targets:** The `target` key accepts a string or list in all formats.

For detailed examples, see [docs/configuration-reference.md](docs/configuration-reference.md).

## Available Commands

| Command | Description |
|---------|-------------|
| `blf link sync [PROJECT]` | Create symlinks or copies in target directories |
| `blf link check [PROJECT]` | Check link status and Git excludes |

For full option details and usage examples, see [docs/cli-reference.md](docs/cli-reference.md).

## Documentation

Comprehensive documentation is available in the [docs/](docs/) directory:

- **[Documentation Hub](docs/README.md)** - Complete documentation index
- **[Configuration Reference](docs/configuration-reference.md)** - Complete configuration documentation
- **[CLI Reference](docs/cli-reference.md)** - Complete command-line interface documentation
- **[Config Format Guide](docs/config-format-clarification.md)** - Understanding configuration
- **[Architecture Design](docs/architecture-design.md)** - Internal architecture
- **[Platform Support](docs/platform-support.md)** - Cross-platform compatibility
- **[Windows Support](docs/windows-support.md)** - Windows-specific guide
- **[Development Guide](docs/development.md)** - Contributing and development

## Important Notes

- Symbolic links use absolute paths to ensure correct targeting from different locations
- Only use in local development environments; do not commit symbolic links to Git
- If you move the source file location, re-run `sync`
- The tool is designed to run from your managed projects directory

## Platform Support

Works on macOS, Linux, and Windows. See [docs/platform-support.md](docs/platform-support.md) for details.
Windows requires Developer Mode (Windows 10/11) or Administrator privileges. See [docs/windows-support.md](docs/windows-support.md) for setup instructions.

## Contributing

Contributions are welcome! See [docs/development.md](docs/development.md) for development setup and guidelines.

## License

MIT License — see the LICENSE file for details.
