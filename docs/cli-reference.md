# CLI Reference

Complete command-line interface reference for `beyond-local-file` (aliased as `blf`).

---

## Command Structure

```bash
blf [GLOBAL_OPTIONS] COMMAND [COMMAND_OPTIONS] [ARGUMENTS]
```

---

## Global Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `-c, --config PATH` | Path | `config.yml` | Path to configuration file |
| `--help` | Flag | - | Show help message and exit |

**Examples:**
```bash
blf --help
blf -c custom.yml link sync
blf --config /path/to/config.yml link check
```

---

## Commands

### `link` — Link Management

Manage symlinks and physical copies between managed projects and target locations.

```bash
blf link SUBCOMMAND [OPTIONS] [ARGUMENTS]
```

**Subcommands:**
- `sync` — Create symlinks and copies
- `check` — Verify status

---

## `link sync` — Create Links

Create symlinks (or physical copies for items marked with `copy: true`) from managed project directory to target locations.

### Syntax

```bash
blf link sync [PROJECT_NAME] [OPTIONS]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `PROJECT_NAME` | No | Sync only this project; omit to sync all projects |

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
blf link sync

# Sync specific project
blf link sync my-project

# Use custom config file (global option)
blf -c custom.yml link sync

# Sync specific project with custom config
blf --config custom.yml link sync my-project
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

### Progress Tracking

If you abort an operation (e.g., choose "Abort" when prompted about conflicts), the tool displays progress:

```
Operation aborted: 5/10 items processed
```

This shows how many items were successfully processed before the interruption.

---

## `link check` — Verify Status

Check the status of symlinks, copies, and Git exclude entries for each project and target location.

### Syntax

```bash
blf link check [PROJECT_NAME] [OPTIONS]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `PROJECT_NAME` | No | Check only this project; omit to check all projects |

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--extra-exclude` | Flag | Off | Show extra entries in `.git/info/exclude` |
| `--format FORMAT` | Choice | `table` | Output format: `table` or `verbose` |

### Output Formats

#### Table Format (Default)

Compact Rich table showing status for all projects and targets.

```bash
blf link check
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
- `⚠ (N incorrect)` — N items exist but point to wrong source (symlinks only)
- `✗ (N missing)` — N items missing
- `✗ (N missing, M incorrect)` — N items missing and M items incorrect

#### Table Format with Extra Excludes

```bash
blf link check --extra-exclude
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
blf link check --format verbose
```

**Output:**
```
Checking project-a → /Users/user/workspace/project-a

Symlinks:
  ✓ .kiro/hooks
  ✓ .vscode/settings.json
  ✗ docker-compose.yml (missing)
  ⚠ .env (points to wrong source)

Copies:
  ✓ .kiro/steering/rules.md (in sync)

Git excludes:
  ✓ .kiro/hooks
  ✓ .vscode/settings.json
  ✓ docker-compose.yml
  ✓ .env
  ✓ .kiro/steering/rules.md

---

Checking project-b → /Users/user/workspace/project-b

Symlinks:
  ✓ .kiro/hooks

Git excludes:
  ✓ .kiro/hooks
  ⚠ Extra: old-file.txt
```

### Symlink Status Indicators

| Status | Description |
|--------|-------------|
| `✓` | Symlink exists and points to correct source |
| `⚠ (points to wrong source)` | Symlink exists but points to incorrect source |
| `✗ (missing)` | Symlink doesn't exist |

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
blf link check

# Check specific project
blf link check my-project

# Show extra exclude entries
blf link check --extra-exclude

# Verbose output
blf link check --format verbose

# Check specific project with verbose output
blf link check my-project --format verbose

# Use custom config file (global option)
blf -c custom.yml link check

# All options combined
blf --config custom.yml link check my-project --extra-exclude --format verbose
```

## `revlink` — Adopt an Existing File into Managed Workflow

Convert an existing file or directory in the current working directory into a managed symlink.
Where `link sync` pushes symlinks from a managed project into target directories, `revlink`
works in reverse: it copies the path to the managed project, verifies the copy via MD5
checksum, replaces the original with a symlink, and optionally records the item in
`.git/info/exclude`.

### Syntax

```bash
blf revlink [OPTIONS] PATH
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `PATH` | Yes | File or directory in the current working directory to convert |

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--dry-run` | Flag | Off | Preview all actions without modifying the filesystem |
| `--force` | Flag | Off | Overwrite an existing destination in the managed project |

### Behavior

1. Loads config using the standard resolution order (`--config` → `~/.blfrc` → `config.yml`).
2. Identifies the managed project whose target paths include the current working directory.
3. Validates the source path (must exist, must not already be a symlink).
4. Copies the source to `<managed_project_path>/<name>`.
5. Verifies the copy via MD5 checksum; aborts and deletes the copy on mismatch.
6. Removes the original and creates a symlink pointing to the managed copy.
7. Adds the item name to `.git/info/exclude` if the current directory is a Git repository.
8. If the matched mapping uses selective sync (`subpath` list), appends the item name to that list in the config file so that `link sync` and `link check` will manage it going forward. Mappings that sync everything (no `subpath`) are unaffected.

### Examples

```bash
# Adopt a file into the managed project
blf revlink myfile.txt

# Adopt a directory
blf revlink .kiro/hooks

# Preview without making changes
blf revlink --dry-run myfile.txt

# Overwrite an existing managed copy
blf revlink --force myfile.txt

# Use a custom config file
blf -c ~/my-files/config.yml revlink myfile.txt
```

### Output

```
Copying /Users/user/project/myfile.txt -> /Users/user/my-files/project/myfile.txt
Computing checksum of /Users/user/project/myfile.txt
✓ MD5 checksum verified
✓ Symlink created: /Users/user/project/myfile.txt -> /Users/user/my-files/project/myfile.txt
Added 'myfile.txt' to .git/info/exclude
```

With `--dry-run`:

```
[dry-run] Copying /Users/user/project/myfile.txt -> /Users/user/my-files/project/myfile.txt
[dry-run] Computing checksum of /Users/user/project/myfile.txt
[dry-run] ✓ MD5 checksum verified
[dry-run] ✓ Symlink created: /Users/user/project/myfile.txt -> /Users/user/my-files/project/myfile.txt
[dry-run] Added 'myfile.txt' to .git/info/exclude
```

### Error Cases

| Condition | Message |
|-----------|---------|
| PATH does not exist | `Error: Path does not exist: <path>` |
| PATH is already a symlink | `Error: Path is already a symlink: <path>` |
| Destination exists and `--force` not set | `Error: Destination already exists: <path>` |
| No managed project targets CWD | `No managed project found for current directory: <cwd>` |
| Multiple projects target CWD | `Ambiguous: multiple projects target <cwd>: <names>` |
| MD5 checksum mismatch | `Error: Checksum mismatch — copy may be corrupt. Destination deleted.` |
| Permission denied removing source | `Error: Permission denied removing <path>` |

---

## `upgrade` — Self-Upgrade

Upgrade beyond-local-file to the latest version. Automatically detects whether the tool was
installed via `uv tool` or `pipx` and runs the appropriate upgrade command.

### Syntax

```bash
blf upgrade [OPTIONS]
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--dry-run` | Flag | Off | Show the upgrade command without executing it |

### Detection Logic

The command inspects the active Python interpreter path (`sys.executable`) to determine the
install method:

| Detected path pattern | Install method | Upgrade command run |
|-----------------------|----------------|---------------------|
| `…/uv/tools/beyond-local-file/…` | `uv tool` | `uv tool install --upgrade beyond-local-file` |
| `…/pipx/venvs/beyond-local-file/…` | `pipx` | `pipx upgrade beyond-local-file` |
| Anything else | unknown | Prints manual instructions and exits 1 |

### Examples

```bash
# Upgrade to latest version
blf upgrade

# Preview what would be run (no changes made)
blf upgrade --dry-run
```

### Output

```
Detected install method: uv tool
Running: uv tool install --upgrade beyond-local-file
```

When the install method cannot be determined:

```
Cannot determine install method.
sys.executable: /path/to/python

Upgrade manually using the command that matches how you installed the tool:

  uv tool install --upgrade beyond-local-file
  pipx upgrade beyond-local-file
  uv tool install --upgrade git+https://github.com/xingyuli/beyond-local-file.git
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

### Config File Resolution Order

The tool resolves the config file in this order:

1. **`-c / --config` flag** — explicit path always wins
2. **`~/.blfrc`** — if present and contains a `config_file` field
3. **`config.yml`** in the current directory — default fallback

### `~/.blfrc` — Centralized Config Pointer

Create `~/.blfrc` to avoid specifying `--config` on every invocation, or to combine multiple config files (e.g., personal and company projects):

```yaml
# Single config file
config_file: ~/my-dev-files/config.yml

# OR multiple config files (personal + company)
config_file:
  - ~/personal/config.yml
  - ~/company/config.yml
```

**Path formats supported:** absolute (`/path/to/config.yml`), tilde (`~/path/to/config.yml`), or relative to home directory (`path/to/config.yml`).

**Disabling temporarily:** Comment out `config_file` to fall back to `config.yml` in CWD — no need to rename or delete the file:

```yaml
# config_file: ~/my-dev-files/config.yml  # temporarily disabled
```

**Multiple config files:** Each managed project must appear in exactly one config file (identified by its absolute path). Duplicate managed project paths across files are an error.

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
blf link sync

# 3. Verify
blf link check
```

### Daily Usage

```bash
# Sync all projects
blf link sync

# Check status
blf link check

# Sync specific project
blf link sync my-project
```

### Troubleshooting

```bash
# Check status with verbose output
blf link check --format verbose

# Check for extra exclude entries
blf link check --extra-exclude

# Re-sync specific project
blf link sync my-project
```

---

## Environment

### Working Directory

Commands run from your managed files directory (where `config.yml` is located).

```bash
cd ~/my-dev-files
blf link sync
```

### Config File Location

Default: `config.yml` in current directory

Override with `-c` or `--config` (global option):
```bash
blf -c /path/to/custom.yml link sync
blf --config /path/to/custom.yml link check
```

### Git Integration

For Git repositories, all linked items (both symlinks and copies) are automatically added to `.git/info/exclude` (not `.gitignore`).

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
