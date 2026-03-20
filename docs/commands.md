# Command Reference

## Global Options

```bash
beyond-local-file [OPTIONS] COMMAND
```

| Option | Description |
|--------|-------------|
| `--help` | Show help and exit |

---

## `symlink` — Symlink management

```bash
beyond-local-file symlink COMMAND
```

### `sync` — Create symlinks

Synchronizes symlinks from a managed project directory to one or more target locations.
For each target that is a Git repository, symlink names are automatically added to
`.git/info/exclude`.

When a project uses the `subpath` config format, only the specified subpaths are
synced instead of every top-level item. Intermediate parent directories are created
automatically in the target.

```bash
beyond-local-file symlink sync [PROJECT_NAME] [OPTIONS]
```

| Argument / Option | Description |
|-------------------|-------------|
| `PROJECT_NAME` | (optional) Sync only this project; omit to sync all |
| `-c, --config PATH` | Path to config file (default: `config.yml`) |

**Behavior when a path already exists at the target:**
The tool prompts you to choose: skip, overwrite, or abort.

**Example:**

```bash
cd ~/my-dev-files
beyond-local-file symlink sync              # sync all projects
beyond-local-file symlink sync project-a   # sync one project
beyond-local-file symlink sync -c custom.yml
```

---

### `check` — Verify symlink status

Checks the status of symlinks and Git exclude entries for each project and target location.

```bash
beyond-local-file symlink check [PROJECT_NAME] [OPTIONS]
```

| Argument / Option | Description |
|-------------------|-------------|
| `PROJECT_NAME` | (optional) Check only this project; omit to check all |
| `-c, --config PATH` | Path to config file (default: `config.yml`) |
| `--extra-exclude` | Show entries in `.git/info/exclude` that don't correspond to any managed file |
| `--format [table\|verbose]` | Output format (default: `table`) |

**Output formats:**

- `table` (default) — compact Rich table, one row per (project, target) pair. Extra exclude
  entries are listed below the table when `--extra-exclude` is used.
- `verbose` — detailed per-project output printed as each result is processed.

**Example:**

```bash
beyond-local-file symlink check
beyond-local-file symlink check project-a
beyond-local-file symlink check --extra-exclude
beyond-local-file symlink check --extra-exclude --format verbose
```

**Table output example:**

```
┌─────────────────┬─────────┬─────────┬──────────────────────────────────────┐
│ Project         │ Symlink │ Exclude │ Target Path                          │
├─────────────────┼─────────┼─────────┼──────────────────────────────────────┤
│ project-a       │ ✓       │ ✓       │ /Users/user/workspace/project-a      │
│ project-b       │ ✓       │ ✓ (+1)  │ /Users/user/workspace/project-b      │
│ project-c       │ ✗ (1 missing) │ ✓ │ /Users/user/workspace/project-c    │
└─────────────────┴─────────┴─────────┴──────────────────────────────────────┘

Extra exclude entries:
  project-b: docs/
```

---

For configuration format details and advanced use cases, see [advanced-usage.md](advanced-usage.md).
