# Windows Support

This document explains how to use beyond-local-file on Windows systems.

## Symbolic Link Support on Windows

Python's `Path.symlink_to()` works on Windows, but requires special permissions due to Windows security policies.

## Requirements

### Windows 10/11 (Build 1703 or later) - Recommended

**Enable Developer Mode** (one-time setup):

1. Open Settings (Win + I)
2. Go to "Update & Security"
3. Click "For developers" in the left sidebar
4. Toggle "Developer Mode" to ON
5. Confirm the prompt

Once enabled, you can create symlinks without administrator privileges.

### Older Windows Versions

Run your terminal as Administrator:

1. Search for "Command Prompt" or "PowerShell"
2. Right-click and select "Run as administrator"
3. Navigate to your managed projects directory
4. Run beyond-local-file commands

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

# Sync all projects
beyond-local-file symlink sync

# Check status
beyond-local-file symlink check
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

### "A required privilege is not held by the client"

This error means you don't have permission to create symlinks.

**Solution:**
- **Windows 10/11**: Enable Developer Mode (see Requirements above)
- **Older Windows**: Run terminal as Administrator

### "The system cannot find the path specified"

The target directory doesn't exist.

**Solution:**
```powershell
# Create the target directory first
mkdir C:\Users\YourName\workspace\project-a

# Then run sync
beyond-local-file symlink sync
```

### Symlinks Not Working in Git

Windows Git may not handle symlinks correctly by default.

**Solution:**
```powershell
# Enable symlink support in Git (run once)
git config --global core.symlinks true

# Clone repositories with symlink support
git clone -c core.symlinks=true <repository-url>
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

## Testing on Windows

To verify everything works:

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

# 5. Run sync
cd my-files
beyond-local-file symlink sync

# 6. Verify symlink
dir ..\target
# Should show: test.txt -> C:\Users\YourName\test-beyond-local-file\my-files\project-a\test.txt
```

## Known Limitations on Windows

1. **Developer Mode or Admin Required**: Unlike Unix systems, Windows requires special permissions
2. **Git Symlink Support**: May need explicit Git configuration
3. **Some Antivirus Software**: May block symlink creation (add exception if needed)
4. **WSL vs Native**: This tool works in both native Windows and WSL, but they use different symlink mechanisms

## WSL (Windows Subsystem for Linux)

If you're using WSL, the tool works exactly like on Linux:

```bash
# In WSL, no special permissions needed
uv tool install git+https://github.com/xingyuli/beyond-local-file.git
beyond-local-file symlink sync
```

**Note:** Symlinks created in WSL may not be accessible from Windows Explorer, and vice versa.

## Recommendations for Windows Users

1. **Enable Developer Mode** - Makes everything easier
2. **Use WSL** - If you're comfortable with Linux, WSL provides a better experience
3. **Use Forward Slashes** - In config.yml for better cross-platform compatibility
4. **Test First** - Try with a small test project before using on real projects

## Further Reading

- [Microsoft: Symbolic Links](https://docs.microsoft.com/en-us/windows/win32/fileio/symbolic-links)
- [Python pathlib on Windows](https://docs.python.org/3/library/pathlib.html#pathlib.Path.symlink_to)
- [Git for Windows: Symbolic Links](https://github.com/git-for-windows/git/wiki/Symbolic-Links)
