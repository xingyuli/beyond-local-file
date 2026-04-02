# CLI Reference

Complete command-line interface reference for `beyond-local-file`.

---

## Command Structure

```bash
beyond-local-file [GLOBAL_OPTIONS] COMMAND [COMMAND_OPTIONS] [ARGUMENTS]
```

---

## Global Options

| Option | Description |
|--------|-------------|
| `--help` | Show help message and exit |
| `--version` | Show version and exit |

**Examples:**
```bash
beyond-local-file --help
beyond-local-file --version
```

---

## Commands

### `link` — Link Management

Manage symlinks and physical copies between managed projects and target locations.

```bash
beyond-local-file link SUBCOMMAND [OPTIONS] [ARGUMENTS]
```

**Subcommands:**
- `sync` — Create symlinks and copies
- `check` — Verify status

---

## `link sync` — Create Links

Create symlinks (or physical copies for items marked with `copy: true`) from managed project directory to target locations.

### Syntax

```bash
beyond-local-file link sync [PROJECT_NAME] [OPTIONS]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `PROJECT_NAME` | No | Sync only this project; omit to sync all projects |

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `-c, --config PATH` | Path | `config.yml` | Path to configuration file |

### Behavior

**When target path doesn't exist:**
- Creates the target directory automatically

**When target item already exists:**
- Prompts for action: overwrite, skip, or abort
- For copy items: detects changes and syncs bidirectionally

**For Git repositories:**
- Automatically adds symlink names to `.git/info/exclude`

**For subpath configuration:**
- Creates only the specified subpaths
- Creates intermediate directories automatically

**For copy strategy:**
- Initial sync: copies from managed to target
- Subsequent syncs: detects changes in both locations
- Conflicts: prompts for resolution

### Examples

```bash
# Sync all projects
beyond-local-file link sync

# Sync specific project
beyond-local-file link sync my-project

# Use custom config file
beyond-local-file link sync -c custom.yml

# Sync specific project with custom config
beyond-local-file link sync my-project -c custom.yml
```

### Output

```
Syncing project-a to /Users/username/workspace/project-a
  ✓ Created: .kiro/hooks
  ✓ Created: .vscode/settings.json
  ✓ Copied: .kiro/steering/rules.md
  ✓ Added 3 entries to .git/info/exclude

Syncing project-b to /Users/username/workspace/project-b
  ✓ Already correct: .kiro/hooks
  ⚠ Skipped: .vscode (already exists)
```

---

## `link check` — Verify Status

Check the status of symlinks, copies, and Git exclude entries for each project and target location.

### Syntax

```bash
beyond-local-file link check [PROJECT_NAME] [OPTIONS]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `PROJECT_NAME` | No | Check only this project; omit to check all projects |

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `-c, --config PATH` | Path | `config.yml` | Path to configuration file |
| `--extra-exclude` | Flag | Off | Show extra entries in `.git/info/exclude` |
| `--format FORMAT` | Choice | `table` | Output format: `table` or `verbose` |

### Output Formats

#### Table Format (Default)

Compact Rich table showing status for all projects and targets.

```bash
beyond-local-file link check
```

**Output:**
```
┌─────────────┬─────────┬─────────┬──────────────────────────────────┐
│ Project     │ Symlink │ Exclude │ Target Path                      │
├─────────────┼─────────┼─────────┼──────────────────────────────────┤
│ project-a   │ ✓       │ ✓       │ /Users/user/workspace/project-a  │
│ project-b   │ ✓       │ ✓ (+1)  │ /Users/user/workspace/project-b  │
│ project-c   │ ✗ (1)   │ ✓       │ /Users/user/workspace/project-c  │
└─────────────┴─────────┴─────────┴──────────────────────────────────┘
```

**Status indicators:**
- `✓` — All items correct
- `✓ (+N)` — All correct, N extra exclude entries
- `✗ (N)` — N items missing or incorrect

#### Table Format with Extra Excludes

```bash
beyond-local-file link check --extra-exclude
```

**Output:**
```
┌─────────────┬─────────┬─────────┬──────────────────────────────────┐
│ Project     │ Symlink │ Exclude │ Target Path                      │
├─────────────┼─────────┼─────────┼──────────────────────────────────┤
│ project-a   │ ✓       │ ✓       │ /Users/user/workspace/project-a  │
│ project-b   │ ✓       │ ✓ (+1)  │ /Users/user/workspace/project-b  │
└─────────────┴─────────┴─────────┴──────────────────────────────────┘

Extra exclude entries:
  project-b: old-file.txt
```

#### Verbose Format

Detailed per-project output printed as each result is processed.

```bash
beyond-local-file link check --format verbose
```

**Output:**
```
Checking project-a → /Users/user/workspace/project-a

Symlinks:
  ✓ .kiro/hooks
  ✓ .vscode/settings.json
  ✗ docker-compose.yml (missing)

Copies:
  ✓ .kiro/steering/rules.md (in sync)

Git excludes:
  ✓ .kiro/hooks
  ✓ .vscode/settings.json
  ✓ docker-compose.yml
  ✓ .kiro/steering/rules.md

---

Checking project-b → /Users/user/workspace/project-b

Symlinks:
  ✓ .kiro/hooks

Git excludes:
  ✓ .kiro/hooks
  ⚠ Extra: old-file.txt
```

### Copy Status Indicators

For items with `copy: true`:

| Status | Description |
|--------|-------------|
| `in sync` | Files are identical |
| `managed changed` | Only managed file changed |
| `target changed` | Only target file changed |
| `conflict` | Both files changed |
| `missing` | Target file doesn't exist |

### Examples

```bash
# Check all projects (table format)
beyond-local-file link check

# Check specific project
beyond-local-file link check my-project

# Show extra exclude entries
beyond-local-file link check --extra-exclude

# Verbose output
beyond-local-file link check --format verbose

# Check specific project with verbose output
beyond-local-file link check my-project --format verbose

# Use custom config file
beyond-local-file link check -c custom.yml

# All options combined
beyond-local-file link check my-project -c custom.yml --extra-exclude --format verbose
```

---

## Exit Codes

| Code | Description |
|------|-------------|
| `0` | Success |
| `1` | Error (invalid config, file not found, etc.) |
| `2` | User aborted operation |

---

## Configuration File

The CLI reads configuration from `config.yml` in the current directory (or path specified with `-c`).

See [Configuration Reference](configuration-reference.md) for complete format documentation.

---

## Common Workflows

### Initial Setup

```bash
# 1. Create config.yml in your managed files directory
cd ~/my-dev-files
cat > config.yml << EOF
my-project: /Users/username/workspace/my-project
EOF

# 2. Sync symlinks
beyond-local-file link sync

# 3. Verify
beyond-local-file link check
```

### Daily Usage

```bash
# Sync all projects
beyond-local-file link sync

# Check status
beyond-local-file link check

# Sync specific project
beyond-local-file link sync my-project
```

### Troubleshooting

```bash
# Check status with verbose output
beyond-local-file link check --format verbose

# Check for extra exclude entries
beyond-local-file link check --extra-exclude

# Re-sync specific project
beyond-local-file link sync my-project
```

---

## Environment

### Working Directory

Commands run from your managed files directory (where `config.yml` is located).

```bash
cd ~/my-dev-files
beyond-local-file link sync
```

### Config File Location

Default: `config.yml` in current directory

Override with `-c`:
```bash
beyond-local-file link sync -c /path/to/custom.yml
```

### Git Integration

For Git repositories, symlink names are automatically added to `.git/info/exclude` (not `.gitignore`).

**Why `.git/info/exclude`?**
- Local to your repository
- Not committed to Git
- Doesn't affect other developers

---

## See Also

- **[Configuration Reference](configuration-reference.md)** - Complete configuration documentation
- **[Config Format Clarification](config-format-clarification.md)** - Format vs architecture concepts
- **[Platform Support](platform-support.md)** - Cross-platform compatibility
- **[Windows Support](windows-support.md)** - Windows-specific guide
- **[Main README](../README.md)** - Getting started guide
