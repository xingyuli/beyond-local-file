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
| **Windows 10** | ✅ Tested & Supported | Requires Developer Mode or Admin privileges for symlinks |
| **Windows 11** | ✅ Supported | Same symlink requirements as Windows 10; not separately cross-tested |
| **Windows 7/8** | ⚠️ Implemented, Not Tested | Should work with Administrator privileges |
| **WSL** | ✅ Should Work | Works like native Linux |

**Note:** Native Windows 10 has been cross-tested (full test suite). Symlink creation still needs Developer Mode (Windows 10 Build 1703+) or an elevated shell. Windows 11 is expected to behave the same; feedback is welcome.

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

Internally, relative item paths written to `config.yml` subpath lists and `.git/info/exclude` use forward slashes (`Path.as_posix()`), so the same entries compare correctly on Windows and Unix. Config files are always read and written as UTF-8. Working-directory matching for `remove` / `revlink` resolves the CWD so Windows short (8.3) vs long path forms do not break target matching.

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

# Full suite has been run on macOS, Linux, and Windows 10
```

**Windows Testing Status:** The full pytest suite (including Hypothesis property tests) has been run successfully on Windows 10 with Developer Mode enabled. Property-test path generators filter Windows reserved device names (`NUL`, `CON`, `COM1`, …) so the suite stays portable. Automated CI still runs on the publish workflow only — local or contributor runs on Windows remain useful.

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
- [x] Cross-platform path normalization for config/exclude/display paths (`as_posix()`, UTF-8 I/O, resolved CWD)
- [ ] CI/CD testing on Windows, macOS, and Linux

## Contributing

We welcome contributions to improve platform support! See [development.md](development.md) for details.
