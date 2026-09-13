# Configuration Reference

Complete reference for a **mapping file** (typically `config.yml`).

Every projection is a physical copy (file or directory). `copy: true` is not a valid option.

One daemon process loads one **configuration set** of mapping files: `-c PATH` is a singleton set; `~/.blf/config` is the global set (a pointer list, not a mapping document); with neither, `config.yml` in CWD is a singleton set. See [Configuration set](cli-reference.md#configuration-set).

---

## Configuration Structure

The mapping file maps managed project names to their target locations. Each project can have one or more mappings to target locations.

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

Projects everything from the managed project to the target.

```yaml
/absolute/path/to/target
```

#### 2. Dict Mapping

Supports selective subpath projection.

```yaml
target: /absolute/path/to/target  # can be string or list
subpath:                          # optional: project only these items
  - relative/path/to/item1
  - relative/path/to/item2
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

<subpath-item>    ::= <relative-path> | <path-item>

<path-item>       ::= path: <relative-path>

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

A leftover `copy:` key on a mapping or a path-item is rejected at load:

```
Unsupported option 'copy: true' (project: my-project, mapping: 1, key: copy)
```

The error names the project, 1-based mapping index, and key.

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

#### `<subpath-item>` as `<path-item>` - Path dict without copy flag

```yaml
my-project:
  target: /absolute/path/to/target
  subpath:
    - .kiro/hooks
    - path: .kiro/steering/rules.md
```

`path:` is an alternate spelling of a relative subpath. It does not change projection: the item is still a physical copy. `copy: true` on that dict is rejected.

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
      - .kiro/steering/rules.md
```

---

## Complete Syntax

### Single Mapping

```yaml
# Simple string - project everything
project-a: /absolute/path/to/target

# Dict with subpath - project only specific items
project-b:
  target: /absolute/path/to/target
  subpath:
    - .kiro/hooks
    - .vscode
```

### List of Mappings

```yaml
# List of simple strings - project everything to multiple targets
project-d:
  - /absolute/path/to/target1
  - /absolute/path/to/target2

# List of dicts - selective projection to multiple targets
project-e:
  - target: /absolute/path/to/target1
    subpath:
      - .kiro/hooks
  - target: /absolute/path/to/target2
    subpath:
      - .vscode

# Mixed list - combine simple strings and dicts
project-f:
  - /absolute/path/to/target1           # project everything
  - target: /absolute/path/to/target2   # project only specific items
    subpath:
      - local-file/tasks/releases
```

### Dict with Multiple Targets

The `target` key in a dict mapping can also be a list:

```yaml
# Project same subpaths to multiple targets
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

By default, all top-level items in a managed project are projected. Use `subpath` to project only specific items:

```yaml
my-project:
  target: /path/to/target
  subpath:
    - .kiro/hooks
    - .vscode/settings.json
    - docker-compose.dev.yml
```

**Behavior:**
- Only listed subpaths are projected
- Intermediate directories created automatically
- Files and directories are physical copies

### Copy-only projections

There is no symlink strategy and no `copy: true` flag. The daemon copies files and directories. The projection path is a real file or directory, not a symlink to the hub. Nested symlink nodes inside a directory item (venv `python` → `python3.14` → the real interpreter) are copied as symlinks; following them is a bug. Leftover blf symlinks from older versions become copies on first catch-up.

If a config still contains `copy: true`:

```yaml
# Invalid in 0.5.0 — will not load
my-project:
  target: /path/to/target
  subpath:
    - path: .kiro/steering/rules.md
      copy: true
```

```
Unsupported option 'copy: true' (project: my-project, mapping: 1, key: copy)
```

Remove the `copy:` key (and, if you like, write the subpath as a plain string).

### Multiple Targets

Project the same managed project to multiple targets:

```yaml
# Simple: project everything to multiple targets
api-service:
  - /path/to/target1
  - /path/to/target2

# Dict: project same subpaths to multiple targets
frontend:
  target:
    - /path/to/target1
    - /path/to/target2
  subpath:
    - .kiro/hooks

# Mixed: different subpaths for different targets
my-project:
  - /path/to/target1              # project everything
  - target: /path/to/target2      # project only specific items
    subpath:
      - .kiro/hooks
```

Each target holds its own tree. The daemon treats the managed project as the hub and fans successful applies out to in-sync replicas of that managed project.

### Item overlap

Several managed projects may contribute items to one target only if the item names are disjoint: not equal, and neither a path prefix of the other. The same rule applies to two subpaths of one managed project.

```yaml
# Illegal: local-file is a prefix of local-file/devops/k8s.md
proj-a:
  target: /path/to/target
  subpath:
    - local-file
proj-b:
  target: /path/to/target
  subpath:
    - local-file/devops/k8s.md
```

Start and reload fail after item discovery:

```
Error: overlapping items on /path/to/target: proj-a 'local-file' and proj-b 'local-file/devops/k8s.md'
```

Distinct siblings on one target are fine (`.vscode` and `.kiro/hooks`). Flatten owned files into the directory item, or use disjoint items.

---

## Configuration Rules

| Rule | Description |
|------|-------------|
| **Project names** | Directory names in your managed files location |
| **Target paths** | Must be absolute paths |
| **Subpaths** | Relative to the project directory |
| **Mapping types** | Simple string (project all) or dict (selective subpaths) |
| **Target key** | Accepts string or list in dict mappings |
| **Projections** | Always physical copies (files and directories); nested symlink nodes stay links |
| **Item overlap** | Item names on one target must be disjoint (not equal, not a path prefix) |
| **`copy:` key** | Rejected at load; not a valid option |

---

## Examples

### Basic Usage

```yaml
# Single target, project everything
personal-tool: /Users/username/projects/personal-tool

# Multiple targets, project everything
api-service:
  - /Users/username/work/api-v1
  - /Users/username/work/api-v2
```

### Selective Projection

```yaml
# Project only specific files and directories
frontend-app:
  target: /Users/username/work/frontend
  subpath:
    - .kiro/hooks
    - .vscode/settings.json
    - .editorconfig

# Multiple targets with selective projection
microservice:
  target:
    - /Users/username/work/service-a
    - /Users/username/work/service-b
  subpath:
    - .kiro/steering
    - docker-compose.dev.yml
```

### Mixed Mappings

```yaml
# Different subpaths for different targets
beyond-local-file:
  - /Users/username/projects/beyond-local-file  # full projection
  - target: /Users/username/blog                # partial projection
    subpath:
      - local-file/tasks/releases

# Complex mixed configuration
my-project:
  - /Users/username/work/project-full           # full projection
  - /Users/username/work/project-full-2         # full projection
  - target: /Users/username/work/project-partial # partial projection
    subpath:
      - .kiro/hooks
      - .vscode
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

### Use Selective Projection

Project only what you need:

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

# Legacy project - only project test files
legacy-app:
  target: /Users/username/workspace/legacy
  subpath:
    - test.http  # API testing
    - .env.test  # Test environment
```

### Apply mapping edits through the daemon

The daemon does not watch mapping files. After a manual edit, run `blf daemon start` (if it is down) or `blf daemon reload` (if it is already up). Removals print one plan and require confirmation; decline commits nothing.

---

## Advanced Topics

### Live hub and fan-out

The managed project is the hub. A mailbox holds at most one not-yet-applied path change per `(path, replica)`. The owner of a target path is the unique item whose name equals that path or is a prefix of it, and that item's managed project — the **contribution source**, derived at runtime from committed mappings, not persisted. After a successful hub apply, that generation is copied or deleted onto other in-sync replicas of that managed project except the source replica. Replicas of other managed projects are not written, even when they use the same item name.

### Out-of-sync replicas

If two replicas edit the same path, the first apply wins. The loser is out-of-sync for that path: fan-out skips it, and further path changes from it are discarded. The hub and in-sync replicas keep moving. `blf daemon status` lists these; `start` and `reload` warn and continue. 0.5.0 has no resolve shell — if the replica's bytes later match the hub, out-of-sync clears.

### Held copies

A delete that wins past generation gap 3 still removes the live path and keeps the previous hub bytes under `~/.blf/held/<sha256 of the managed project path>/` (`delete-gap`). `revlink create` fan-out uses `create-overwrite` when a replica had different bytes. That tree is not an item and is never projected. `status` lists held copies; there is no restore/discard command in 0.5.0.

---

## See Also

- **[CLI Reference](cli-reference.md)** - Complete command-line interface documentation
- **[Config Format Clarification](config-format-clarification.md)** - Format vs architecture concepts
- **[Main README](../README.md)** - Getting started guide
