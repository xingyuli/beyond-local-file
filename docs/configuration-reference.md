# Configuration Reference

Complete reference for `config.yml` configuration file.

---

## Format Specifications

### Format 1: Simple String

Single target path as a string.

```yaml
project-name: /absolute/path/to/target
```

**Use when:** One project, one target, sync all files.

**Example:**
```yaml
my-tool: /Users/username/projects/my-tool
```

---

### Format 2: Simple List

Multiple target paths as a list.

```yaml
project-name:
  - /absolute/path/to/target1
  - /absolute/path/to/target2
```

**Use when:** One project, multiple targets, sync all files.

**Example:**
```yaml
api-service:
  - /Users/username/work/api-v1
  - /Users/username/work/api-v2
```

---

### Format 3: Selective Subpaths

Sync only specific files or directories.

```yaml
project-name:
  target: /absolute/path/to/target  # string or list
  subpath:
    - relative/path/to/item1
    - relative/path/to/item2
```

**Use when:** Need to sync only specific items, not everything.

**Behavior:**
- Only listed subpaths are synced
- Intermediate directories created automatically
- All items are symlinked by default

**Example:**
```yaml
frontend-app:
  target: /Users/username/work/frontend
  subpath:
    - .kiro/hooks
    - .vscode/settings.json
    - docker-compose.dev.yml
```

**With multiple targets:**
```yaml
frontend-app:
  target:
    - /Users/username/work/frontend-dev
    - /Users/username/work/frontend-staging
  subpath:
    - .kiro/hooks
    - .vscode/settings.json
```

---

### Format 4: Copy Strategy

Create physical copies instead of symlinks for specific items.

```yaml
project-name:
  target: /absolute/path/to/target  # string or list
  subpath:
    - item1                          # symlink (default)
    - path: item2                    # physical copy
      copy: true
```

**Use when:** Tools don't recognize symlinks and require physical files.

**Behavior:**
- Items without `copy: true` are symlinked (default)
- Items with `copy: true` are physically copied
- Bidirectional sync: detects changes in both locations
- Conflict resolution: prompts when both sides changed

**Example:**
```yaml
my-project:
  target: /Users/username/workspace/my-project
  subpath:
    - .kiro/hooks                    # symlink
    - .vscode                        # symlink
    - path: .kiro/steering/rules.md  # physical copy
      copy: true
```

**With multiple targets:**
```yaml
microservice:
  target:
    - /Users/username/work/service-a
    - /Users/username/work/service-b
  subpath:
    - .kiro/steering                 # symlink
    - docker-compose.dev.yml         # symlink
    - path: .qoder/rules.md          # physical copy (each target gets own copy)
      copy: true
```

---

## Configuration Rules

| Rule | Description |
|------|-------------|
| **Project names** | Directory names in your managed files location |
| **Target paths** | Must be absolute paths |
| **Subpaths** | Relative to the project directory |
| **Copy flag** | Creates physical files instead of symlinks |
| **Items** | Auto-discovered from filesystem (or specified in subpath) |
| **Target key** | Accepts string or list in all formats |

---

## Complete Examples

### Example 1: Simple Projects

```yaml
# Single target, sync everything
personal-tool: /Users/username/projects/personal-tool

# Multiple targets, sync everything
api-service:
  - /Users/username/work/api-v1
  - /Users/username/work/api-v2
```

### Example 2: Selective Sync

```yaml
# Sync only specific files
frontend-app:
  target: /Users/username/work/frontend
  subpath:
    - .kiro/hooks
    - .vscode/settings.json
    - .editorconfig

# Multiple targets with selective sync
microservice:
  target:
    - /Users/username/work/service-a
    - /Users/username/work/service-b
  subpath:
    - .kiro/steering
    - docker-compose.dev.yml
```

### Example 3: Tool Compatibility (Copy Strategy)

```yaml
# IDE requires physical steering files
my-app:
  target: /Users/username/work/my-app
  subpath:
    - .kiro/hooks                    # symlink
    - .vscode                        # symlink
    - path: .kiro/steering/rules.md  # physical copy (Kiro IDE requires physical file)
      copy: true

# Multiple targets with mixed strategies
multi-env:
  target:
    - /Users/username/work/dev
    - /Users/username/work/staging
  subpath:
    - .kiro/hooks                    # shared (symlink)
    - .vscode                        # shared (symlink)
    - path: .qoder/config.yml        # per-target (physical copy)
      copy: true
```

### Example 4: Organized by Category

```yaml
# Development tools
dev-tools: /Users/username/workspace/dev-tools

# Testing configurations
test-configs:
  - /Users/username/workspace/project-a
  - /Users/username/workspace/project-b
  - /Users/username/workspace/project-c

# IDE settings only
ide-settings:
  target:
    - /Users/username/workspace/project-a
    - /Users/username/workspace/project-b
  subpath:
    - .vscode
    - .idea

# Legacy project with selective sync
legacy-app:
  target: /Users/username/workspace/legacy
  subpath:
    - test.http
    - .env.test
```

### Example 5: Mixed Configuration

```yaml
# Simple projects
tool-a: /Users/username/projects/tool-a
tool-b: /Users/username/projects/tool-b

# Multiple targets
api-service:
  - /Users/username/work/api-v1
  - /Users/username/work/api-v2

# Selective sync
frontend:
  target: /Users/username/work/frontend
  subpath:
    - .kiro/hooks
    - .vscode

# Copy strategy
backend:
  target:
    - /Users/username/work/backend-dev
    - /Users/username/work/backend-prod
  subpath:
    - .kiro/hooks
    - path: .kiro/steering/rules.md
      copy: true
```

---

## Copy Strategy Details

### When to Use

Use `copy: true` when:
- Tools don't recognize or follow symlinks
- IDEs silently ignore symlinked configuration files
- Files must be physical for tool compatibility

**Example:** Kiro IDE requires steering files to be physical. Symlinked steering files are silently ignored.

### Scope Limitations

**Copy mode only supports single files — no directory-level copy.**

This is an intentional design constraint:
- Copy is a boundary-case escape hatch, not a general-purpose file distribution mechanism
- Keeping symlinks as the primary workflow ensures centralized management
- Directory-level copies would encourage large-scale duplication, defeating the tool's purpose

```yaml
# ✅ Correct: single file with copy
subpath:
  - path: .kiro/steering/rules.md
    copy: true

# ❌ Not supported: directory with copy
subpath:
  - path: .kiro/steering    # directories cannot use copy: true
    copy: true
```

### Sync Behavior

**Initial sync:**
- Copies from managed to target
- Records file state for change detection

**Subsequent syncs:**
- Detects changes in both locations
- Three-way comparison: managed, target, last-sync-state

**Change scenarios:**
1. **No changes:** Skip
2. **Managed changed only:** Sync managed → target
3. **Target changed only:** Sync target → managed (reverse sync)
4. **Both changed:** Conflict - prompt user for resolution

### Conflict Resolution

When both sides have changed:
```
Conflict detected: both managed and target files have changed
  managed: /path/to/managed/.kiro/steering/rules.md
  target:  /path/to/target/.kiro/steering/rules.md

Choose resolution: [m]anaged / [t]arget / [s]kip
```

**Options:**
- `m` — Use managed version (overwrite target with managed)
- `t` — Use target version (overwrite managed with target, reverse sync)
- `s` — Skip this file (keep both versions as-is, no changes)

---

## Best Practices

### 1. Use Absolute Paths

```yaml
# ✅ Recommended
project: /Users/username/workspace/project

# ❌ Avoid
project: ../workspace/project
```

### 2. Prefer Symlinks

Use copy strategy only when necessary (tool compatibility).

```yaml
# ✅ Recommended
my-project:
  target: /Users/username/workspace/my-project
  subpath:
    - .kiro/hooks                    # symlink (preferred)
    - path: .kiro/steering/rules.md  # copy (only if tool requires)
      copy: true
```

### 3. Group Related Projects

```yaml
# Personal projects
personal-tool: /Users/username/personal/tool

# Work projects
work-api: /Users/username/work/api
work-frontend: /Users/username/work/frontend
```

### 4. Use Selective Sync

Sync only what you need:

```yaml
my-project:
  target: /Users/username/workspace/my-project
  subpath:
    - .vscode
    - .kiro
    - .editorconfig
```

### 5. Document Your Config

```yaml
# Shared development configurations
dev-configs: /Users/username/workspace/shared

# Legacy project - only sync test files
legacy-app:
  target: /Users/username/workspace/legacy
  subpath:
    - test.http  # API testing
    - .env.test  # Test environment
```

---

## See Also

- **[CLI Reference](cli-reference.md)** - Complete command-line interface documentation
- **[Config Format Clarification](config-format-clarification.md)** - Format vs architecture concepts
- **[Main README](../README.md)** - Getting started guide
