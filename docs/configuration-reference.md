# Configuration Reference

Complete reference for `config.yml` configuration file.

---

## Configuration Structure

The configuration file maps managed project names to their target locations. Each project can have one or more mappings to target locations.

### Basic Structure

```yaml
project-name: <mapping>
```

Where `<mapping>` can be:
- **Single mapping:** One mapping between managed project and target
- **List of mappings:** Multiple mappings for the same managed project

### Mapping Types

Each mapping can be defined in two forms:

#### 1. Simple String Mapping

Syncs everything from the managed project to the target.

```yaml
/absolute/path/to/target
```

#### 2. Dict Mapping

Supports selective subpath sync and copy strategy.

```yaml
target: /absolute/path/to/target  # can be string or list
subpath:                          # optional: sync only these items
  - relative/path/to/item1
  - path: relative/path/to/item2  # optional: use copy instead of symlink
    copy: true
```

---

## Formal Grammar

This section provides a formal specification of the configuration format using YAML-aware grammar notation.

### Grammar Definition

```
<config>          ::= <project-entry>+

<project-entry>   ::= <project-name>: <mapping>

<mapping>         ::= <single-mapping> | <mapping-list>

<single-mapping>  ::= <string-mapping> | <dict-mapping>

<mapping-list>    ::= - <single-mapping>
                      (- <single-mapping>)*

<string-mapping>  ::= <absolute-path>

<dict-mapping>    ::= target: <target>
                      [subpath: <subpath-list>]

<target>          ::= <absolute-path> | <path-list>

<path-list>       ::= - <absolute-path>
                      (- <absolute-path>)*

<subpath-list>    ::= - <subpath-item>
                      (- <subpath-item>)*

<subpath-item>    ::= <relative-path> | <copy-item>

<copy-item>       ::= path: <relative-path>
                      copy: true

<project-name>    ::= <identifier>
<absolute-path>   ::= <string>
<relative-path>   ::= <string>
<identifier>      ::= <string>
```

**Notation:**
- `<angle-brackets>` denote non-terminals (grammar rules)
- `::=` means "is defined as"
- `|` means "or" (alternative)
- `[]` means optional (in grammar, not YAML syntax)
- `()*` means zero or more repetitions
- `+` means one or more repetitions
- `:` and `-` are actual YAML syntax

### Grammar Examples

Each production rule demonstrated with concrete YAML examples:

#### `<string-mapping>` - Simple string mapping

```yaml
my-project: /absolute/path/to/target
```

#### `<dict-mapping>` - Dict mapping with target only

```yaml
my-project:
  target: /absolute/path/to/target
```

#### `<dict-mapping>` - Dict mapping with target and subpath

```yaml
my-project:
  target: /absolute/path/to/target
  subpath:
    - .kiro/hooks
    - .vscode
```

#### `<target>` as `<path-list>` - Multiple targets in dict

```yaml
my-project:
  target:
    - /absolute/path/to/target1
    - /absolute/path/to/target2
  subpath:
    - .kiro/hooks
```

#### `<subpath-item>` as `<copy-item>` - Copy strategy

```yaml
my-project:
  target: /absolute/path/to/target
  subpath:
    - .kiro/hooks
    - path: .kiro/steering/rules.md
      copy: true
```

#### `<mapping-list>` with `<string-mapping>` - List of simple strings

```yaml
my-project:
  - /absolute/path/to/target1
  - /absolute/path/to/target2
```

#### `<mapping-list>` with `<dict-mapping>` - List of dicts

```yaml
my-project:
  - target: /absolute/path/to/target1
    subpath:
      - .kiro/hooks
  - target: /absolute/path/to/target2
    subpath:
      - .vscode
```

#### `<mapping-list>` mixed - List with both string and dict mappings

```yaml
my-project:
  - /absolute/path/to/target1
  - target: /absolute/path/to/target2
    subpath:
      - local-file/tasks/releases
```

#### Complete example - Multiple projects with various mappings

```yaml
# <string-mapping>
project-a: /absolute/path/to/target

# <dict-mapping> with subpath
project-b:
  target: /absolute/path/to/target
  subpath:
    - .kiro/hooks

# <mapping-list> with <string-mapping>
project-c:
  - /absolute/path/to/target1
  - /absolute/path/to/target2

# <mapping-list> mixed
project-d:
  - /absolute/path/to/target1
  - target: /absolute/path/to/target2
    subpath:
      - .kiro/hooks
      - path: .kiro/steering/rules.md
        copy: true
```

---

## Complete Syntax

### Single Mapping

```yaml
# Simple string - sync everything
project-a: /absolute/path/to/target

# Dict with subpath - sync only specific items
project-b:
  target: /absolute/path/to/target
  subpath:
    - .kiro/hooks
    - .vscode

# Dict with copy strategy
project-c:
  target: /absolute/path/to/target
  subpath:
    - .kiro/hooks                    # symlink
    - path: .kiro/steering/rules.md  # physical copy
      copy: true
```

### List of Mappings

```yaml
# List of simple strings - sync everything to multiple targets
project-d:
  - /absolute/path/to/target1
  - /absolute/path/to/target2

# List of dicts - selective sync to multiple targets
project-e:
  - target: /absolute/path/to/target1
    subpath:
      - .kiro/hooks
  - target: /absolute/path/to/target2
    subpath:
      - .vscode

# Mixed list - combine simple strings and dicts
project-f:
  - /absolute/path/to/target1           # sync everything
  - target: /absolute/path/to/target2   # sync only specific items
    subpath:
      - local-file/tasks/releases
```

### Dict with Multiple Targets

The `target` key in a dict mapping can also be a list:

```yaml
# Sync same subpaths to multiple targets
project-g:
  target:
    - /absolute/path/to/target1
    - /absolute/path/to/target2
  subpath:
    - .kiro/hooks
    - .vscode
```

---

## Features

### Subpath Mapping

By default, all top-level items in a managed project are synced. Use `subpath` to sync only specific items:

```yaml
my-project:
  target: /path/to/target
  subpath:
    - .kiro/hooks
    - .vscode/settings.json
    - docker-compose.dev.yml
```

**Behavior:**
- Only listed subpaths are synced
- Intermediate directories created automatically
- All items are symlinked by default

### Copy Strategy

By default, items are symlinked. Use `copy: true` for physical copies when tools don't recognize symlinks:

```yaml
my-project:
  target: /path/to/target
  subpath:
    - .kiro/hooks                    # symlink (default)
    - path: .kiro/steering/rules.md  # physical copy
      copy: true
```

**Behavior:**
- Items without `copy: true` are symlinked
- Items with `copy: true` are physically copied
- Bidirectional sync: detects changes in both locations
- Conflict resolution: prompts when both sides changed

**Limitations:**
- Copy mode only supports single files, not directories
- This is intentional to keep symlinks as the primary workflow

### Multiple Targets

Sync the same managed project to multiple targets:

```yaml
# Simple: sync everything to multiple targets
api-service:
  - /path/to/target1
  - /path/to/target2

# Dict: sync same subpaths to multiple targets
frontend:
  target:
    - /path/to/target1
    - /path/to/target2
  subpath:
    - .kiro/hooks

# Mixed: different sync strategies for different targets
my-project:
  - /path/to/target1              # sync everything
  - target: /path/to/target2      # sync only specific items
    subpath:
      - .kiro/hooks
```

---

## Configuration Rules

| Rule | Description |
|------|-------------|
| **Project names** | Directory names in your managed files location |
| **Target paths** | Must be absolute paths |
| **Subpaths** | Relative to the project directory |
| **Mapping types** | Simple string (sync all) or dict (selective sync + copy) |
| **Target key** | Accepts string or list in dict mappings |
| **Copy flag** | Creates physical files instead of symlinks (files only) |

---

## Examples

### Basic Usage

```yaml
# Single target, sync everything
personal-tool: /Users/username/projects/personal-tool

# Multiple targets, sync everything
api-service:
  - /Users/username/work/api-v1
  - /Users/username/work/api-v2
```

### Selective Sync

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

### Copy Strategy

```yaml
# IDE requires physical steering files
my-app:
  target: /Users/username/work/my-app
  subpath:
    - .kiro/hooks                    # symlink
    - .vscode                        # symlink
    - path: .kiro/steering/rules.md  # physical copy
      copy: true

# Multiple targets with copy
multi-env:
  target:
    - /Users/username/work/dev
    - /Users/username/work/staging
  subpath:
    - .kiro/hooks                    # shared (symlink)
    - path: .qoder/config.yml        # per-target (physical copy)
      copy: true
```

### Mixed Strategies

```yaml
# Different sync strategies for different targets
beyond-local-file:
  - /Users/username/projects/beyond-local-file  # full sync
  - target: /Users/username/blog                # partial sync
    subpath:
      - local-file/tasks/releases

# Complex mixed configuration
my-project:
  - /Users/username/work/project-full           # full sync
  - /Users/username/work/project-full-2         # full sync
  - target: /Users/username/work/project-partial # partial sync
    subpath:
      - .kiro/hooks
      - .vscode
  - target:                                      # partial sync with copy
      - /Users/username/work/env-dev
      - /Users/username/work/env-prod
    subpath:
      - .kiro/hooks
      - path: .kiro/steering/rules.md
        copy: true
```

---

## Best Practices

### Use Absolute Paths

```yaml
# ✅ Recommended
project: /Users/username/workspace/project

# ❌ Avoid
project: ../workspace/project
```

### Prefer Symlinks

Use copy strategy only when necessary (tool compatibility):

```yaml
my-project:
  target: /Users/username/workspace/my-project
  subpath:
    - .kiro/hooks                    # symlink (preferred)
    - path: .kiro/steering/rules.md  # copy (only if tool requires)
      copy: true
```

### Use Selective Sync

Sync only what you need:

```yaml
my-project:
  target: /Users/username/workspace/my-project
  subpath:
    - .vscode
    - .kiro
    - .editorconfig
```

### Document Your Config

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

## Advanced Topics

### Copy Strategy Conflict Resolution

When both managed and target files have changed, the tool prompts for resolution:

```
Conflict detected: both managed and target files have changed
  managed: /path/to/managed/.kiro/steering/rules.md
  target:  /path/to/target/.kiro/steering/rules.md

Choose resolution: [m]anaged / [t]arget / [s]kip
```

**Options:**
- `m` — Use managed version (overwrite target)
- `t` — Use target version (overwrite managed, reverse sync)
- `s` — Skip this file (keep both versions as-is)

### Copy Strategy Sync Behavior

**Initial sync:**
- Copies from managed to target
- Records file state for change detection

**Subsequent syncs:**
- Detects changes in both locations
- Three-way comparison: managed, target, last-sync-state

**Change scenarios:**
1. No changes → Skip
2. Managed changed only → Sync managed → target
3. Target changed only → Sync target → managed (reverse sync)
4. Both changed → Conflict (prompt user)

---

## See Also

- **[CLI Reference](cli-reference.md)** - Complete command-line interface documentation
- **[Config Format Clarification](config-format-clarification.md)** - Format vs architecture concepts
- **[Main README](../README.md)** - Getting started guide
