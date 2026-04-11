---
inclusion: fileMatch
fileMatchPattern: "src/beyond_local_file/**"
---

# Architecture

## Package Layout

```
src/beyond_local_file/
├── __init__.py                  # Package metadata (__version__)
├── cli.py                       # Click CLI entry point — command groups and options
├── config.py                    # YAML config loading and path resolution (Config class)
├── options.py                   # StrEnum definitions for CLI option values
├── link_strategy_protocol.py   # Protocol definitions and unified result types
├── formatters.py                # Output formatters: LinkSyncFormatter, LinkCheckFormatter
├── git_manager.py               # GitExcludeManager — reads/writes .git/info/exclude
├── project_processor.py         # ProjectProcessor + CmdOperation subclasses (SyncOperation, CheckOperation)
├── symlink_manager.py           # SymlinkManager — implements LinkStrategyManager protocol
├── copy_manager.py              # CopyManager — implements LinkStrategyManager protocol
├── sync_state.py                # Copy strategy state tracking
└── model/
    ├── config.py                # Config models (YAML structure)
    ├── processing.py            # Processing models (execution structure)
    └── translator.py            # Config → Processing translation
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

## Result Type Architecture

All result types are defined in `link_strategy_protocol.py` as the single source of truth:

**Base Result Types:**
- `LinkCreateResult` — Results from link creation operations
- `LinkCheckResult` — Results from link check operations
- `GitExcludeAddResult` — Results from git exclude add operations
- `GitExcludeCheckResult` — Results from git exclude check operations
- `OperationProgress` — Progress tracking embedded in operation results

**Strategy-Specific Details:**
- `CopyCreateDetails` — Additional information for copy strategy create operations (e.g., reverse_copied items)
- `CopyCheckDetails` — Additional information for copy strategy check operations (e.g., sync status details)

**Composition Pattern:**
Base results use composition for strategy-specific details:
```python
@dataclass
class LinkCreateResult:
    created: set[str]
    already_correct: set[str]
    skipped: set[str]
    failed: set[str]
    details: LinkCreateDetails | None = None  # Strategy-specific details
    progress: OperationProgress = field(default_factory=...)
```

Managers create unified result types directly.

## Git Exclude Responsibility Pattern

Operations are responsible for checking git repository status before calling manager git exclude methods:

```python
# In operations (project_processor.py)
if symlink_items:
    manager = SymlinkManager(symlink_items, unit.target_project_path)
    link_result = manager.create_links(self.ask_callback)
    
    # Operation checks git repo status
    git_result = None
    if manager.git_manager.is_git_repo():
        git_result = manager.add_git_excludes()
```

Managers document this as a PRECONDITION in their docstrings:

```python
def add_git_excludes(self) -> GitExcludeAddResult:
    """Add git exclude entries for all managed items (protocol method).
    
    PRECONDITION: This method is guaranteed to be called only when the target
    directory is inside a git repository. Callers must check git repo status
    before invoking this method.
    """
```

This design:
- Keeps managers focused on their core responsibility (managing links)
- Avoids redundant git repo checks across multiple managers
- Makes the precondition explicit in the contract

## Adding a New CLI Command

1. Create a new `CmdOperation` subclass in `project_processor.py`.
2. Add a new Click command in `cli.py` under the `link` group (or a new group).
3. If the command has fixed option values, define a `StrEnum` in `options.py`.
4. Use protocol methods (`create_links()`, `check_links()`, `add_git_excludes()`, `check_git_excludes()`).
5. Operations must check git repo status before calling git exclude methods.
6. Use `LinkSyncFormatter` and `LinkCheckFormatter` for output.
7. All result types come from `link_strategy_protocol.py`.
