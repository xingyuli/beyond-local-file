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
| **Windows 10** | ✅ Tested & Supported | Copy projections; Developer Mode only when a tree contains nested links |
| **Windows 11** | ✅ Supported | Same as Windows 10; not separately cross-tested |
| **Windows 7/8** | ⚠️ Implemented, Not Tested | Copy projections should work without elevation |
| **WSL** | ✅ Should Work | Works like native Linux |

**Note:** Native Windows 10 has been cross-tested (full test suite). The projection path is a physical copy, so Developer Mode is not required for ordinary files and directories. Enable it (Windows 10 Build 1703+) or use an elevated shell when a directory item contains nested symlink nodes, or for leftover symlink tests. Windows 11 is expected to behave the same; feedback is welcome.

## Quick Start by Platform

### macOS / Linux

```bash
# Install
uv tool install git+https://github.com/xingyuli/beyond-local-file.git

# Use immediately
cd ~/my-dev-files
blf daemon start
blf link check
```

### Windows 10/11

```powershell
# 1. Install
uv tool install git+https://github.com/xingyuli/beyond-local-file.git

# 2. Use
cd C:\Users\YourName\my-dev-files
blf daemon start
blf link check
```

Developer Mode is not required for ordinary copy projections. Enable it when a directory item contains nested symlink nodes, or if you run leftover symlink tests.

### WSL (Windows Subsystem for Linux)

```bash
# Works exactly like Linux
uv tool install git+https://github.com/xingyuli/beyond-local-file.git
blf daemon start
```

## Platform-Specific Details

### Copy Projections

The tool writes regular files and directories at the projection path. That works out of the box on macOS, Linux, and Windows. Symlink is not a link strategy. Nested symlink nodes inside a directory item are copied as symlinks (venv interpreters); following them is a bug.

Leftover blf symlinks from older versions are converted to copies on the first daemon catch-up. Creating those test fixtures — or copying nested links — on Windows still needs Developer Mode or Administrator privileges.

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

1. **Nested symlink nodes**: Developer Mode or Admin is required when a directory item contains nested links
2. **Leftover symlink tests**: Developer Mode or Admin is still required for tests that create symlink fixtures
3. **Git leftover symlinks**: May need `git config --global core.symlinks true` if old blf symlinks remain
4. **Antivirus**: Some antivirus software may inspect many small file copies

### All Platforms

1. **Git Tracking**: Projected copies should not be committed to Git
2. **Daemon required**: Shells (`link check`, `revlink`, `remove`) fail if the daemon is down

## Testing

The project includes comprehensive tests:

```bash
# Run tests
uv run pytest

# Full suite has been run on macOS, Linux, and Windows 10
```

**Windows Testing Status:** The full pytest suite (including Hypothesis property tests) has been run successfully on Windows 10. Property-test path generators filter Windows reserved device names (`NUL`, `CON`, `COM1`, …) so the suite stays portable. Automated CI still runs on the publish workflow only — local or contributor runs on Windows remain useful. Enable Developer Mode before running leftover symlink fixture tests, and when projecting directory items that contain nested links.

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

- [x] Copy-only projections (Developer Mode not required for ordinary copies; still needed for nested links)
- [x] Cross-platform path normalization for config/exclude/display paths (`as_posix()`, UTF-8 I/O, resolved CWD)
- [ ] CI/CD testing on Windows, macOS, and Linux

## Contributing

We welcome contributions to improve platform support! See [development.md](development.md) for details.
