# Windows Support

**Testing Status:** Native Windows 10 has been cross-tested with the full pytest suite. The projection path is a physical copy, so Developer Mode is not required for ordinary files and directories. Enable it (Windows 10 Build 1703+) or use an elevated shell when a directory item contains nested symlink nodes, or when leftover tests still create symlink fixtures. Windows 11 is expected to work the same but has not been separately cross-tested. Report remaining issues via GitHub.

## Table of Contents

- [Requirements](#requirements)
- [Installation on Windows](#installation-on-windows)
- [Usage on Windows](#usage-on-windows)
- [Path Considerations](#path-considerations)
- [Troubleshooting](#troubleshooting)
- [Testing on Windows](#testing-on-windows)
- [Known Limitations on Windows](#known-limitations-on-windows)
- [WSL (Windows Subsystem for Linux)](#wsl-windows-subsystem-for-linux)
- [Recommendations for Windows Users](#recommendations-for-windows-users)
- [Further Reading](#further-reading)

This document explains how to use beyond-local-file on Windows systems.

## Requirements

Windows 10/11 is supported. Ordinary copy projections (regular files and directories) do not need Developer Mode or an elevated shell.

Developer Mode (or Administrator) is needed when a directory item contains nested symlink nodes (venv `python` → `python3.14` → the real interpreter). Those nested links are copied as symlinks; following them is a bug. It is also needed for leftover symlink test fixtures, or old blf symlinks on disk that the first daemon catch-up will convert to copies.

## Installation on Windows

### Using uv (Recommended)

```powershell
# Install uv first (if not already installed)
pip install uv

# Install beyond-local-file
uv tool install git+https://github.com/xingyuli/beyond-local-file.git

# Verify installation
beyond-local-file --help
```

### Using pipx

```powershell
# Install pipx first (if not already installed)
pip install pipx
pipx ensurepath

# Install beyond-local-file
pipx install git+https://github.com/xingyuli/beyond-local-file.git

# Verify installation
beyond-local-file --help
```

## Usage on Windows

The usage is identical to macOS/Linux:

```powershell
# Navigate to your managed projects directory
cd C:\Users\YourName\my-dev-files

# Start the daemon (projects copies and keeps them live)
blf daemon start

# Check status
blf link check
```

## Path Considerations

### Use Forward Slashes or Raw Strings

In `config.yml`, you can use either:

```yaml
# Option 1: Forward slashes (recommended)
project-a: C:/Users/YourName/workspace/project-a

# Option 2: Escaped backslashes
project-b: C:\\Users\\YourName\\workspace\\project-b

# Option 3: Relative paths (works the same as Unix)
project-c: ../workspace/project-c
```

Relative item names written into `subpath` lists and `.git/info/exclude` always use forward slashes (e.g. `.kiro/hooks`), even on Windows. Config I/O uses UTF-8 explicitly so locale code pages do not corrupt edits.

### Example Windows Configuration

```yaml
# config.yml on Windows
api-project:
  - C:/Users/YourName/workspace/api-v1
  - C:/Users/YourName/workspace/api-v2

frontend-project: C:/Users/YourName/workspace/frontend

# Relative paths work too
shared-configs: ../workspace/shared
```

## Troubleshooting

### "The system cannot find the path specified"

The target directory doesn't exist.

**Solution:**
```powershell
# Create the target directory first
mkdir C:\Users\YourName\workspace\project-a

# Then start the daemon
blf daemon start
```

### Command Not Found After Installation

The uv/pipx bin directory may not be in your PATH.

**Solution:**
```powershell
# Add to PATH (PowerShell)
$env:Path += ";$env:USERPROFILE\.local\bin"

# Or permanently add via System Properties:
# 1. Search for "Environment Variables"
# 2. Edit "Path" under User variables
# 3. Add: C:\Users\YourName\.local\bin
```

### "A required privilege is not held by the client"

This error is from creating a symlink: leftover test fixtures, a first catch-up converting an old blf symlink, or copying nested symlink nodes inside a directory item. Ordinary file and directory copies without nested links do not need it.

**Solution (tests / leftover conversion only):**
- **Windows 10/11**: Enable Developer Mode — Settings → Update & Security → For developers → Developer Mode
- **Older Windows**: Run the terminal as Administrator

### Git and leftover symlinks

Windows Git may not handle leftover blf symlinks correctly by default. Copy projections do not need Git symlink support. If you still have old symlinks to convert:

```powershell
# Enable symlink support in Git (run once)
git config --global core.symlinks true
```

## Testing on Windows

**Current Status:** Cross-tested on Windows 10 (full `uv run pytest` suite). Developer Mode is needed for tests that still create leftover symlink fixtures, and for projecting directory items that contain nested links.

**Reproduce locally:**

```powershell
# 1. Create a test directory
mkdir C:\Users\YourName\test-beyond-local-file
cd C:\Users\YourName\test-beyond-local-file

# 2. Create managed files
mkdir my-files\project-a
echo "test" > my-files\project-a\test.txt

# 3. Create config
@"
project-a: C:/Users/YourName/test-beyond-local-file/target
"@ | Out-File -Encoding UTF8 my-files\config.yml

# 4. Create target directory
mkdir target

# 5. Start the daemon
cd my-files
blf daemon start

# 6. Verify a regular copy (not a symlink)
dir ..\target
# Should show: test.txt as a normal file
```

**Please report regressions** by [opening an issue](https://github.com/xingyuli/beyond-local-file/issues) with:
- Windows version
- Python version
- Whether Developer Mode is enabled (relevant for nested links and leftover symlink tests)
- Any error messages

## Known Limitations on Windows

1. **Nested symlink nodes**: Developer Mode or Admin is required when a directory item contains nested links (those nodes are copied as symlinks)
2. **Leftover symlink tests**: Developer Mode or Admin is still required for tests that create symlink fixtures
3. **Git leftover symlinks**: May need explicit Git configuration if old blf symlinks remain
4. **Some antivirus software**: May still inspect or delay many small file copies
5. **WSL vs Native**: The tool works in both native Windows and WSL; copies are ordinary files in both

## WSL (Windows Subsystem for Linux)

If you're using WSL, the tool works exactly like on Linux:

```bash
# In WSL, no special permissions needed
uv tool install git+https://github.com/xingyuli/beyond-local-file.git
blf daemon start
```

Copies created in WSL are regular files and are visible from Windows Explorer.

## Recommendations for Windows Users

1. **Use Forward Slashes** - In config.yml for better cross-platform compatibility
2. **Smoke-test First** - Try with a small test project before using on real projects
3. **Developer Mode** - Not needed for ordinary copies; enable it when a tree contains nested links, or if you run the pytest suite

## Further Reading

- [Python pathlib on Windows](https://docs.python.org/3/library/pathlib.html)
- [Git for Windows: Symbolic Links](https://github.com/git-for-windows/git/wiki/Symbolic-Links) (leftover conversion / tests only)
