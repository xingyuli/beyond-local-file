# Configuration Format Reference

## Purpose

This document defines the official `config.yml` format and clarifies the distinction from conceptual examples in architecture documentation.

## Important Note

The "Problem Space" section in `docs/design-divide-and-conquer.md` shows **conceptual examples** for explaining architecture, NOT the actual configuration format. Always refer to this document for the real format.

---

## Configuration Format

### 1. Simple string — single target

```yaml
project-a: /Users/username/projects/project-a
```

### 2. Simple list — multiple targets

```yaml
project-b:
  - /Users/username/workspace/project-b-v1
  - /Users/username/workspace/project-b-v2
```

### 3. Selective subpaths

```yaml
project-c:
  target: /Users/username/workspace/project-c
  subpath:
    - .kiro/hooks
    - .vscode/settings.json
```

The `target` key accepts a string or list. Only listed subpaths are projected. Every item is a physical copy (file or directory).

`copy: true` is not valid. A leftover flag is rejected at load:

```
Unsupported option 'copy: true' (project: my-project, mapping: 1, key: copy)
```

---

## Configuration Rules

1. **Project names** are directory names in your managed files location
2. **Target paths** must be absolute paths
3. **Subpaths** are relative to the project directory
4. **Projections** are always physical copies; there is no symlink strategy
5. **Items** are auto-discovered from filesystem (or specified in subpath)

---

## Internal vs User-Facing

### User Configuration (config.yml)

```yaml
my-project:
  target: /path/to/target
  subpath:
    - .kiro/hooks
    - .kiro/steering/rules.md
```

### Internal Model (Python)

```python
Project(
    name="my-project",
    path=Path("/current/dir/my-project"),
    targets=[Path("/path/to/target")],
    items=[
        ProjectItem(name=".kiro/hooks", strategy=LinkStrategy.COPY),
        ProjectItem(name=".kiro/steering/rules.md", strategy=LinkStrategy.COPY),
    ]
)
```

**Transformation:**
1. Config parsing extracts project names and targets
2. Filesystem discovery finds items (or uses subpath list)
3. Model construction creates `Project` and `ProjectItem` objects
4. Every item is a copy; leftover `copy: true` never reaches this step

---

## Conceptual Example (NOT Real Config)

The architecture docs use this format for explanation only:

```yaml
# ❌ NOT THE ACTUAL CONFIG FORMAT
projects:
  my-project:
    path: ~/managed/project
    targets: [~/target1, ~/target2]
    items:
      - name: config.yml
        strategy: copy
```

**Why different?**
- `projects:` wrapper doesn't exist
- `path:` field doesn't exist (auto-discovered)
- `items:` array doesn't exist (auto-discovered or in subpath)
- `strategy:` field doesn't exist (copy is the only projection)

These fields exist in the internal model, not the user config.

---

## Summary

| Aspect | User Config | Internal Model |
|--------|-------------|----------------|
| Location | `config.yml` | Python classes |
| Format | Simple YAML | Complex objects |
| Projection | Always a copy | `LinkStrategy.COPY` (leftover symlink conversion is catch-up, not a user option) |
| Items | Auto-discovered or subpath | Explicit list |
| Purpose | User-facing | Internal processing |

**Key takeaway:** Use `README.md` and `docs/configuration-reference.md` for configuration. The `docs/design-divide-and-conquer.md` examples illustrate internal architecture only.

---

## See Also

- **[Configuration Reference](configuration-reference.md)** - Complete configuration documentation
- **[CLI Reference](cli-reference.md)** - Complete command-line interface documentation
- **[Design Overview](design-overview.md)** - Architecture overview
- **[Main README](../README.md)** - Getting started guide
