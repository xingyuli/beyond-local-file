# Advanced Usage

## Configuration Format

The `config.yml` file maps project directory names to target paths. Three formats
are supported and can be mixed in the same file.

### Simplified (string)

```yaml
project-b: /Users/user/workspace/project-b
```

### Simplified (list)

```yaml
project-a:
  - /Users/user/workspace/project-a
  - /Users/user/workspace/project-a-fork
```

### Full format (selective subpaths)

Use a dict with `target` and optional `subpath` to sync only specific items:

```yaml
project-c:
  target: /Users/user/workspace/project-c
  subpath:
    - .kiro/hooks
    - .vscode/settings.json
```

`target` accepts a string or list. `subpath` accepts a string or list of relative
paths within the project directory. When `subpath` is set, only those paths are
linked instead of every top-level item.

Intermediate directories are created automatically in the target. For example,
syncing subpath `.kiro/hooks` creates the `.kiro/` directory in the target if it
doesn't exist.

### Multiple targets with subpaths

```yaml
project-c:
  target:
    - /Users/user/workspace/project-c
    - /Users/user/workspace/project-c-fork
  subpath:
    - .kiro/hooks
```

```bash
beyond-local-file symlink sync project-c    # syncs only .kiro/hooks to both targets
beyond-local-file symlink check project-c   # checks subpath symlink status
```
