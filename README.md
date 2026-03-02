# Beyond Local File

A command-line tool for synchronizing and managing local development files across multiple projects.

## What is this?

In real-world development, you often need to share local development files (such as development configurations, test scripts, HTTP client test files, etc.) across multiple projects, but you don't want to commit these files to Git repositories. `beyond-local-file` uses symbolic links to allow you to:

- Centrally manage local development files
- Use these files across multiple target projects
- Automatically add symbolic links to Git ignore lists
- Check synchronization status

## 🎬 Quick Demo

![Demo](demo/demo.gif)

*Watch beyond-local-file in action: install from GitHub, sync files, create symlinks, and manage Git excludes automatically.*

## Architecture: Tool and Data Separation

`beyond-local-file` follows a clean separation between the **tool** (code) and **managed projects** (data):

### The Tool (Code)

The tool is the CLI application itself - the Python package that provides the `beyond-local-file` command. It contains:
- Command-line interface and logic
- Symlink management functionality
- Git exclude file handling
- Configuration file parsing

**Key characteristics:**
- Installed independently via `uvx` or `pip`
- Lives in Python's site-packages (or runs ephemerally with `uvx`)
- Can be updated independently of your projects
- Contains no user data or project-specific files

### Managed Projects (Data)

Managed projects are your directories containing the local development files you want to share across projects. They include:
- Your local development files organized in subdirectories
- A `config.yml` file mapping these directories to target locations
- Any project-specific configurations

**Key characteristics:**
- Live in a directory you control (anywhere on your filesystem)
- Can be version-controlled in a separate Git repository
- Can be shared across teams or kept private
- Independent of the tool's installation location

### Why This Separation Matters

1. **Independent Installation**: Install the tool once via `uvx`, use it across all your managed project directories
2. **Separate Repositories**: Keep the tool code in one repository, your managed projects in another (or multiple others)
3. **Team Collaboration**: Share managed projects with your team without requiring them to clone the tool's source code
4. **Easy Updates**: Update the tool without affecting your managed projects, and vice versa
5. **Flexibility**: Maintain multiple managed project directories for different purposes (work, personal, client projects)

### Example Structure

```
# Tool (installed via uvx)
~/.local/pipx/venvs/beyond-local-file/  # Tool installation (managed by uvx)

# Managed Projects (your data, separate repository)
~/my-dev-files/                         # Your managed projects directory
├── config.yml                          # Configuration file
├── project-a/                          # Managed project directory
│   ├── local-file/
│   └── test.http
└── project-b/                          # Another managed project
    └── dev-config.yml

# Target Projects (where symlinks are created)
~/workspace/project-a/                  # Target project
├── local-file -> ~/my-dev-files/project-a/local-file
└── test.http -> ~/my-dev-files/project-a/test.http
```

In this example:
- The tool is installed once and available system-wide
- Your managed projects live in `~/my-dev-files/` (could be a Git repository)
- Target projects in `~/workspace/` receive symlinks to your managed files
- You can run `uvx beyond-local-file` from `~/my-dev-files/` to manage all symlinks

## Installation

Since this package is not yet published to PyPI, you can install it directly from the Git repository using one of these methods:

### Method 1: Using `uv tool install` (Recommended)

Install once, use everywhere:

```bash
# Install from Git repository
uv tool install git+https://github.com/xingyuli/beyond-local-file.git

# Now you can use it directly from any directory
beyond-local-file --help

# Example: Check symlink status
cd /path/to/your/managed-projects
beyond-local-file symlink check

# To update to the latest version
uv tool install --force git+https://github.com/xingyuli/beyond-local-file.git
```

### Method 2: Using `pipx`

If you prefer `pipx`:

```bash
# Install once
pipx install git+https://github.com/xingyuli/beyond-local-file.git

# Use directly
beyond-local-file --help

# Update when needed
pipx upgrade beyond-local-file
# or reinstall: pipx install --force git+https://github.com/xingyuli/beyond-local-file.git
```

### Method 3: Using `uvx` (ephemeral, no installation)

If you want to run without installing:

```bash
# Run directly (downloads and runs each time)
uvx --from git+https://github.com/xingyuli/beyond-local-file.git beyond-local-file --help

# Tip: Create a shell alias to avoid typing the full command
alias beyond-local-file='uvx --from git+https://github.com/xingyuli/beyond-local-file.git beyond-local-file'
```

**Recommendation**: Use Method 1 (`uv tool install`) for the best experience - install once and use like any other command-line tool.

For development setup, see [docs/development.md](docs/development.md).

## Usage Examples

### Basic Workflow

The tool is designed to be run from your managed projects directory, where you keep your local development files organized. Here's a typical workflow:

#### 1. Set up your managed projects directory

Create a directory structure for your local development files:

```
my-managed-projects/
├── config.yml
├── project-a/
│   ├── local-file/
│   ├── .qoder/
│   └── test.http
└── project-b/
    ├── scripts/
    └── dev-config.yml
```

#### 2. Create a configuration file

In your managed projects directory, create a `config.yml` file that maps your local file directories to target project locations:

```yaml
# Map managed project directories to target locations
project-a:
  - /Users/username/workspace/project-a
  - /Users/username/workspace/project-a-fork

project-b:
  - /Users/username/workspace/project-b

# You can use relative paths for targets (resolved from current directory)
project-c: ../workspace/project-c

# Multiple targets for the same managed project
shared-configs:
  - /Users/username/workspace/api-server
  - /Users/username/workspace/web-app
  - /Users/username/workspace/mobile-backend
```

**Configuration format:**
- **Keys**: Directory names in your managed projects directory (relative to config file location)
- **Values**: Target project paths (can be absolute or relative to current working directory)
- **Single target**: Use a string value
- **Multiple targets**: Use a list of strings

#### 3. Sync files to target projects

Run the tool from your managed projects directory:

```bash
# Navigate to your managed projects directory
cd ~/my-managed-projects

# Sync all projects defined in config.yml
uvx beyond-local-file symlink sync

# Sync a specific project only
uvx beyond-local-file symlink sync project-a

# Use a custom config file
uvx beyond-local-file symlink sync -c custom-config.yml
```

**What happens during sync:**
- Creates symbolic links in target directories pointing to your managed files
- If target is a Git repository, adds symlink names to `.git/info/exclude`
- Prompts for action if a file/directory already exists at the target location
- Reports created, skipped, and failed symlinks

#### 4. Check synchronization status

```bash
# Check all projects
uvx beyond-local-file symlink check

# Check a specific project
uvx beyond-local-file symlink check project-a

# Show extra entries in git exclude files
uvx beyond-local-file symlink check --extra-exclude
```

**Check output shows:**
- ✓ Existing symlinks (correctly synced)
- ✗ Missing symlinks (need to be created)
- Git exclude entries (present, missing, or extra)

### Example: Managing HTTP Test Files

Suppose you have HTTP test files that you want to use across multiple API projects:

```bash
# Your managed projects directory structure
~/dev-files/
├── config.yml
└── api-tests/
    ├── auth.http
    ├── users.http
    └── products.http

# config.yml content
api-tests:
  - ~/workspace/api-v1
  - ~/workspace/api-v2
  - ~/workspace/api-staging

# Run from managed projects directory
cd ~/dev-files
uvx beyond-local-file symlink sync api-tests
```

Result: The `auth.http`, `users.http`, and `products.http` files will be symlinked into all three target projects, and automatically added to their Git exclude files.

### Example: Development Configuration Files

Share development configurations across related projects:

```bash
# Managed projects structure
~/local-configs/
├── config.yml
├── backend-dev/
│   ├── .env.local
│   ├── debug.config.json
│   └── local-overrides.yml
└── frontend-dev/
    ├── .env.development.local
    └── proxy.config.js

# config.yml
backend-dev: /Users/username/projects/my-backend
frontend-dev: /Users/username/projects/my-frontend

# Sync from managed projects directory
cd ~/local-configs
uvx beyond-local-file symlink sync
```

### Working from Different Directories

The tool resolves paths intelligently based on where you run it:

```bash
# Run from managed projects directory (recommended)
cd ~/my-managed-projects
uvx beyond-local-file symlink sync

# Run from a different directory with explicit config path
cd ~/workspace/some-project
uvx beyond-local-file symlink sync -c ~/my-managed-projects/config.yml

# Run from anywhere with absolute config path
uvx beyond-local-file symlink sync -c /Users/username/my-managed-projects/config.yml
```

**Path resolution rules:**
- Config file path: Resolved relative to current working directory
- Managed project paths: Resolved relative to config file location
- Target paths: Resolved relative to current working directory

## How It Works

1. **Organization**: Create subdirectories in your managed projects directory (e.g., `project-a`, `project-b`) to store your local development files

2. **Synchronization**: Run the `sync` command, and the tool creates symbolic links in target projects pointing to your managed files

3. **Git Integration**: If the target project is a Git repository, the tool automatically adds symlink names to `.git/info/exclude`, ensuring these links are not tracked by Git

4. **Conflict Handling**: If a file with the same name already exists at the target location, the tool prompts you to choose: skip, overwrite, or abort

## Use Cases

- Manage HTTP client test files (such as `.http` files)
- Share development tool scripts across projects
- Synchronize local development configurations
- Manage test data files
- Share editor/IDE configurations for local development
- Distribute local-only documentation and notes

## Important Notes

- Symbolic links use absolute paths to ensure correct targeting from different locations
- Only use in local development environments; do not commit symbolic links to Git
- If you move the source file location, you need to re-run the `sync` command
- The tool is designed to run from your managed projects directory, not from its installation location

### Windows Support

The tool works on Windows with the following requirements:

**Windows 10/11 (Build 1703 or later):**
- Enable Developer Mode: Settings → Update & Security → For developers → Developer Mode
- No administrator privileges required once Developer Mode is enabled

**Older Windows versions:**
- Requires running the command prompt or terminal as Administrator
- Right-click Command Prompt/PowerShell → "Run as administrator"

**Note:** If you encounter permission errors on Windows, ensure Developer Mode is enabled or run as Administrator.

## Command Reference

### Sync Command

```bash
uvx beyond-local-file symlink sync [PROJECT_NAME] [OPTIONS]
```

**Arguments:**
- `PROJECT_NAME` (optional): Sync only the specified project; if omitted, syncs all projects

**Options:**
- `-c, --config PATH`: Path to config file (default: `config.yml` in current directory)

### Check Command

```bash
uvx beyond-local-file symlink check [PROJECT_NAME] [OPTIONS]
```

**Arguments:**
- `PROJECT_NAME` (optional): Check only the specified project; if omitted, checks all projects

**Options:**
- `-c, --config PATH`: Path to config file (default: `config.yml` in current directory)
- `--extra-exclude`: Show extra entries in git exclude files that don't correspond to managed files

## Troubleshooting

**Config file not found:**
- Ensure you're running the command from the directory containing `config.yml`, or use the `-c` option to specify the config file path

**Paths not resolving correctly:**
- Managed project paths are resolved relative to the config file location
- Target paths are resolved relative to your current working directory
- Use absolute paths if relative path resolution is unclear
- Run `uvx beyond-local-file symlink check` to verify paths before syncing

**Command not found:**
- Ensure `uvx` is installed: `pip install uv` or follow [uv installation instructions](https://github.com/astral-sh/uv)
- Try running with full Git URL: `uvx --from git+https://github.com/xingyuli/beyond-local-file.git beyond-local-file`

**Permission errors:**
- Ensure you have write permissions in the target directories
- On Windows:
  - **Windows 10/11 (Build 1703+)**: Enable Developer Mode in Settings → Update & Security → For developers
  - **Older Windows**: Run terminal as Administrator (Right-click → "Run as administrator")
  - See [Windows symlink documentation](https://docs.microsoft.com/en-us/windows/win32/fileio/symbolic-links) for details
- On macOS/Linux: Check that target directories exist and are accessible

## Contributing

Contributions are welcome! Please see [docs/development.md](docs/development.md) for development setup and guidelines.

## Platform Support

beyond-local-file works on macOS, Linux, and Windows. See [docs/platform-support.md](docs/platform-support.md) for details.

For Windows-specific setup instructions, see [docs/windows-support.md](docs/windows-support.md).

## License

MIT License - see the LICENSE file for details.
