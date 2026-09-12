# Beyond Local File

![Beyond Local File](docs/assets/banner-960x540.png)

Project your local dev files across projects as physical copies — without committing them to Git.

## Table of Contents

- [What is this?](#what-is-this)
- [Why not GNU Stow or chezmoi?](#why-not-gnu-stow-or-chezmoi)
- [Architecture: Tool and Data Separation](#architecture-tool-and-data-separation)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Available Commands](#available-commands)
- [Documentation](#documentation)
- [Important Notes](#important-notes)
- [Platform Support](#platform-support)
- [Contributing](#contributing)
- [How the author uses it](#how-the-author-uses-it)
- [License](#license)

## What is this?

In real-world development, local files accumulate that are genuinely useful but shouldn't be
committed to Git: HTTP client files with private environment variables, AI agent hooks and
steering documents, task runner configs referencing local paths, debug logs, scratch specs.
You want them in your project directory — your editor, your AI tools, your task runner all
expect them there — but not in the repository.

`beyond-local-file` manages these files centrally and projects them into your target projects
as physical copies (files and directories). It also automatically adds those projections to
each project's Git exclude list, so Git never sees them.

A few concrete things it handles that are hard to do with a shell script:

- Projecting an entire directory subtree (e.g., `.kiro/hooks/`) into multiple projects at once
- Keeping each target project's copies live while a daemon observes the hub and fans updates out
- Isolating a replica that loses an update (out-of-sync) instead of overwriting it
- Checking status across all managed projects at a glance (`blf link check`)

## 🎬 Quick Demo

![Demo](demo/demo.gif)

*Watch beyond-local-file in action: install from GitHub, project files into a target, and manage Git excludes automatically.*

## Why not GNU Stow or chezmoi?

**GNU Stow** and **chezmoi** are excellent tools for dotfiles management — organizing your personal configuration files (`.bashrc`, `.vimrc`, `.gitconfig`) across machines.

- **Stow** uses a package-based approach with CLI parameters to create symlinks from a stow directory to `$HOME`.
- **chezmoi** is a comprehensive dotfiles manager with templating, encryption, password manager integration, and Git-based sync across machines.

**beyond-local-file** is designed for a different use case: per-project development files that shouldn't be committed to Git. Instead of managing `$HOME` dotfiles, it projects local dev files (HTTP client configs, AI hooks, task runner configs) across multiple projects using a centralized `config.yml`. It handles Git excludes automatically. Every projection is a physical copy, so tools that refuse workspace-escape (Kiro) can read the files inside the target project.

**Use Stow/chezmoi for:** Personal dotfiles in `$HOME`  
**Use beyond-local-file for:** Local dev files across multiple projects with different layouts

For a detailed comparison with use case examples, see [docs/alternatives-comparison.md](docs/alternatives-comparison.md).

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

# Target Projects (where physical copies are projected)
~/workspace/project-a/
└── test.http    # regular file, copied from ~/my-dev-files/project-a/test.http
```

`link` is the metaphor: a managed item is visible in a target project. The runtime is a daemon that copies, observes, and applies mapping changes. Each target project holds its own tree; there is no live inode sharing.

## Installation

### Recommended: `uv tool install` from PyPI

```bash
uv tool install beyond-local-file

# Update to latest version
uv tool install --upgrade beyond-local-file
# Or use the built-in upgrade command (auto-detects install method)
blf upgrade
```

### Alternative: `pipx` from PyPI

```bash
pipx install beyond-local-file

# Update
pipx upgrade beyond-local-file
# Or use the built-in upgrade command (auto-detects install method)
blf upgrade
```
### Install from GitHub (development version)

```bash
# Using uv
uv tool install git+https://github.com/xingyuli/beyond-local-file.git

# Using pipx
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

2. Start the daemon (the runtime that projects copies and keeps them live):

```bash
cd ~/my-dev-files
blf daemon start
```

3. Check status:

```bash
blf link check
```

`link check`, `revlink create` / `restore`, and `remove` talk to the daemon. If it is down they fail with:

```
Error: daemon is not running. Start it with: blf daemon start
```

## Configuration

The `config.yml` file maps project names to target paths. Three formats are supported:

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

### 3. Selective subpaths — project specific items only

```yaml
project-c:
  target: /Users/username/workspace/project-c
  subpath:
    - .kiro/hooks
    - .vscode/settings.json
```

Only the listed subpaths are projected. Intermediate directories are created automatically. Files and directories are both physical copies.

**Multiple targets:** The `target` key accepts a string or list in all formats.

`copy: true` is not a valid option. Every projection is already a copy; leftover `copy: true` in a mapping or subpath entry is rejected at config load:

```
Unsupported option 'copy: true' (project: my-project, mapping: 1, key: copy)
```

For detailed examples, see [docs/configuration-reference.md](docs/configuration-reference.md).

### Config File Location

By default the tool looks for `config.yml` in the current directory. You can override this with `--config`, or create `~/.blfrc` to set a persistent default:

```yaml
# ~/.blfrc — point to your managed-files config
config_file: ~/my-dev-files/config.yml

# Or combine personal and company configs
config_file:
  - ~/personal/config.yml
  - ~/company/config.yml
```

See [Config File Resolution](docs/cli-reference.md#config-file-resolution-order) in the CLI reference for full details.

## Available Commands

| Command | Description |
|---------|-------------|
| `blf daemon start` | Start the background runtime that copies, observes, and applies mappings |
| `blf daemon stop` | Stop the running daemon |
| `blf daemon status` | Show whether the daemon is running, plus out-of-sync paths and held copies |
| `blf daemon logs` | Follow the daemon log (Ctrl-C stops following, not the daemon) |
| `blf daemon reload` | Apply external mapping edits from the config file |
| `blf link check [PROJECT]` | Check copy projections and Git excludes |
| `blf revlink create PATH` | Adopt an existing file or directory as a copy projection |
| `blf revlink restore PATH` | Stop managing PATH and leave the target file in place |
| `blf remove PATH` | Permanently remove a managed item and its validated projections |
| `blf upgrade` | Upgrade to the latest version (auto-detects install method) |

There is no `link sync`. The daemon is the runtime.

### Live updates, out-of-sync, and held copies

The managed project is the hub. After a successful hub apply, the daemon fans the generation out to other in-sync replicas of that managed project except the source (the tree that already has the bytes).

If two target projects edit the same path, the first apply wins. The loser is **out-of-sync** for that path: later fan-out skips it, and further edits from it are discarded. The live path on the hub and on in-sync replicas keeps moving.

A delete past generation gap 3 still removes the live path and keeps the previous hub bytes under `.blf-held/` in the managed project (a **held copy**). `blf daemon status` lists out-of-sync paths and held copies. `start` and `reload` warn and ask you to continue; 0.5.0 does not interview you to pick winners.

### Mapping edits

Edit `config.yml` by hand, then run `blf daemon start` (if the daemon is down) or `blf daemon reload` (if it is already up). Adds apply automatically. Removals print one plan and require confirmation; decline commits nothing. The daemon does not watch the config file.

For full option details and usage examples, see [docs/cli-reference.md](docs/cli-reference.md).

## Documentation

Comprehensive documentation is available in the [docs/](docs/) directory:

- **[Documentation Hub](docs/README.md)** - Complete documentation index
- **[Configuration Reference](docs/configuration-reference.md)** - Complete configuration documentation
- **[CLI Reference](docs/cli-reference.md)** - Complete command-line interface documentation
- **[Shell Completion](docs/shell-completion.md)** - Tab completion setup for bash, zsh, and fish
- **[Config Format Guide](docs/config-format-clarification.md)** - Understanding configuration
- **[Architecture Design](docs/architecture-design.md)** - Internal architecture
- **[Platform Support](docs/platform-support.md)** - Cross-platform compatibility
- **[Windows Support](docs/windows-support.md)** - Windows-specific guide
- **[Development Guide](docs/development.md)** - Contributing and development

## Important Notes

- Every projection is a regular file or directory inside the target project
- Leftover blf symlinks from older versions become copies on the first daemon catch-up
- Only use in local development environments; do not commit projected copies to Git
- If you move the managed project, restart the daemon so catch-up can rewrite projections
- Shells (`link check`, `revlink`, `remove`) require a running daemon

## Platform Support

Tested on macOS, Linux, and Windows 10. See [docs/platform-support.md](docs/platform-support.md) for details.

Projections are copies, so Windows Developer Mode is not required for ordinary files and directories. Enable it when a directory item contains nested symlinks (venv interpreters). See [docs/windows-support.md](docs/windows-support.md) for path and install notes.

## Contributing

Contributions are welcome! See [docs/development.md](docs/development.md) for development setup and guidelines.

## How the author uses it

I maintain two managed-project repos with `beyond-local-file` — one for personal GitHub
projects (`viclau-local-files`, a private repo), one for company work. They're completely
independent, each with its own `config.yml`, and the tool doesn't need to know about either.

The company-scoped repo's most involved config entry projects an entire AI-assisted development
environment into a backend project: Kiro hooks for code review, requirement breakdown, and
weekly report generation; `.qoder` agent definitions, rules, and skills; `.vscode` settings;
a `Taskfile.yml` with build and deploy tasks; and a structured `local-file/` directory that
AI agents read and write into during development. Those trees are physical copies, including
directory items such as `.kiro/hooks`, so tools that refuse workspace-escape can read them
inside the target workspace.

The personal repo has a single entry: `beyond-local-file` itself. The tool manages its own
development environment — a local task tracker, per-release archived changelogs, and an
agentic workspace for drafts and analysis — none of it committed to the main repo.

## License

MIT License — see the LICENSE file for details.
