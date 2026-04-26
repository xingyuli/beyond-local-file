# Platform Support

## Table of Contents

- [Supported Platforms](#supported-platforms)
- [Quick Start by Platform](#quick-start-by-platform)
- [Platform-Specific Details](#platform-specific-details)
- [Known Limitations](#known-limitations)
- [Testing](#testing)
- [Documentation](#documentation)
- [Reporting Issues](#reporting-issues)
- [Future Improvements](#future-improvements)
- [Contributing](#contributing)

beyond-local-file is designed to work across all major operating systems.

## Supported Platforms

| Platform | Status | Notes |
|----------|--------|-------|
| **macOS** | ✅ Tested & Supported | No special configuration needed |
| **Linux** | ✅ Tested & Supported | No special configuration needed |
| **Windows 10/11** | ⚠️ Implemented, Not Tested | Should work with Developer Mode or Admin privileges |
| **Windows 7/8** | ⚠️ Implemented, Not Tested | Should work with Administrator privileges |
| **WSL** | ✅ Should Work | Works like native Linux |

**Note:** Windows support is implemented but has not been tested yet. The code uses Python's standard `pathlib` for symlink creation, which should work on Windows with proper permissions. Feedback from Windows users is welcome!

## Quick Start by Platform

### macOS / Linux

```bash
# Install
uv tool install git+https://github.com/xingyuli/beyond-local-file.git

# Use immediately
cd ~/my-dev-files
blf link sync
```

### Windows 10/11

```powershell
# 1. Enable Developer Mode (one-time)
#    Settings → Update & Security → For developers → Developer Mode

# 2. Install
uv tool install git+https://github.com/xingyuli/beyond-local-file.git

# 3. Use
cd C:\Users\YourName\my-dev-files
blf link sync
```

### WSL (Windows Subsystem for Linux)

```bash
# Works exactly like Linux
uv tool install git+https://github.com/xingyuli/beyond-local-file.git
blf link sync
```

## Platform-Specific Details

### Symbolic Link Creation

The tool uses Python's `pathlib.Path.symlink_to()` which:

- **macOS/Linux**: Works out of the box, no special permissions needed
- **Windows**: Requires either:
  - Developer Mode enabled (Windows 10 Build 1703+), or
  - Administrator privileges (older versions)

### Path Handling

The tool automatically handles platform-specific path differences:

```yaml
# config.yml works on all platforms

# Unix-style (macOS/Linux)
project-a: /home/user/workspace/project-a

# Windows-style (both work)
project-b: C:/Users/User/workspace/project-b
project-c: C:\Users\User\workspace\project-c

# Relative paths (work everywhere)
project-d: ../workspace/project-d
```

## Known Limitations

### Windows-Specific

1. **Permissions**: Requires Developer Mode or Admin (unlike Unix)
2. **Git Integration**: May need `git config --global core.symlinks true`
3. **Antivirus**: Some antivirus software may block symlink creation

### All Platforms

1. **Absolute Paths**: Symlinks use absolute paths (by design)
2. **Git Tracking**: Symlinks should not be committed to Git
3. **Cross-Platform**: Symlinks created on one OS may not work on another

## Testing

The project includes comprehensive tests:

```bash
# Run tests
uv run pytest

# All tests pass on macOS and Linux
# Windows testing status: Not yet tested, feedback welcome
```

**Windows Testing Status:** The codebase uses Python's standard library (`pathlib`) for cross-platform compatibility, and Windows-specific symlink handling is implemented. However, it has not been tested on actual Windows systems yet. If you're a Windows user, please try it out and report any issues!

## Documentation

- [Windows Support Guide](windows-support.md) - Detailed Windows setup
- [Development Guide](development.md) - For contributors
- [README](../README.md) - General usage

## Reporting Issues

If you encounter platform-specific issues:

1. Check the [Windows Support Guide](windows-support.md) for Windows
2. Search [existing issues](https://github.com/xingyuli/beyond-local-file/issues)
3. Open a new issue with:
   - Operating system and version
   - Python version
   - Error message
   - Steps to reproduce

## Future Improvements

Potential enhancements for better cross-platform support:

- [ ] Automatic detection of Windows Developer Mode status
- [ ] Better error messages for Windows permission issues
- [ ] Optional hard links or junctions on Windows (as fallback)
- [ ] Cross-platform path normalization in config files
- [ ] CI/CD testing on Windows, macOS, and Linux

## Contributing

We welcome contributions to improve platform support! See [development.md](development.md) for details.
