---
inclusion: auto
fileMatchPattern: "src/beyond_local_file/**"
---

# Architecture

## Package Layout

```
src/beyond_local_file/
├── __init__.py            # Package metadata (__version__)
├── cli.py                 # Click CLI entry point — command groups and options
├── config.py              # YAML config loading and path resolution (Config class)
├── models.py              # Data models: ProjectItem, ProjectConfiguration, Project
├── options.py             # StrEnum definitions for CLI option values
├── formatters.py          # Output formatters: SyncResultFormatter, CheckResultFormatter, CheckTableFormatter
├── git_manager.py         # GitExcludeManager — reads/writes .git/info/exclude
├── project_processor.py   # ProjectProcessor + CmdOperation subclasses (SyncOperation, CheckOperation)
└── symlink_manager.py     # SymlinkManager — sync/check symlinks; Action enum, SyncResult, CheckResult
```

## Data Flow

1. `cli.py` parses CLI args, calls `load_config()` from `project_processor.py`.
2. `load_config()` uses `Config` (from `config.py`) to parse YAML and return `dict[str, ProjectConfiguration]`.
3. `ProjectProcessor.process_all(operation)` iterates projects/targets, creates `Project.from_directory()`, and calls `operation.execute(project, target_path)`.
4. `SyncOperation` / `CheckOperation` delegate to `SymlinkManager` for the actual symlink and git-exclude work.
5. Formatters in `formatters.py` handle all output rendering (Rich tables for table mode, click.echo for verbose mode).

## Key Design Decisions

- Tool and data separation: the CLI is installed once; managed project directories live separately.
- Config paths resolve relative to the config file's directory; target paths resolve relative to CWD.
- `CmdOperation` is an abstract base with `execute()` and `verbose_progress` — new commands extend this.
- `SymlinkManager` owns both symlink logic and `GitExcludeManager` composition.
- Output formatting is decoupled from operations via dedicated formatter classes.

## Adding a New CLI Command

1. Create a new `CmdOperation` subclass in `project_processor.py`.
2. Add a new Click command in `cli.py` under the `symlink` group (or a new group).
3. If the command has fixed option values, define a `StrEnum` in `options.py`.
4. If custom output is needed, add a formatter in `formatters.py`.
