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
├── options.py                   # User-facing option enums: StrEnum for CLI flags, Enum for interactive prompts
├── link_strategy_protocol.py   # Protocol definitions and unified result types
├── git_manager.py               # GitExcludeManager — reads/writes .git/info/exclude
├── project_processor.py         # Config loading, ProjectProcessor orchestrator
├── symlink_manager.py           # SymlinkManager — implements LinkStrategyManager protocol
├── copy_manager.py              # CopyManager — implements LinkStrategyManager protocol
├── sync_state.py                # Copy strategy state tracking
├── operations/
│   ├── __init__.py              # Re-exports CmdOperation, SyncOperation, CheckOperation, run_upgrade
│   ├── base.py                  # CmdOperation ABC
│   ├── link_sync.py             # SyncOperation + LinkSyncFormatter
│   ├── link_check.py            # CheckOperation + LinkCheckFormatter + table formatters
│   └── upgrade.py               # run_upgrade — install method detection and self-upgrade logic
└── model/
    ├── config.py                # Config models (YAML structure)
    ├── processing.py            # Processing models (execution structure)
    └── translator.py            # Config → Processing translation
```

## Data Flow

1. `cli.py` parses CLI args, calls `load_config_projects()` from `project_processor.py`.
2. `load_config_projects()` uses `Config` (from `config.py`) to parse YAML and return `dict[str, ConfigProject]`.
3. `ProjectProcessor.process_all_units(operation)` iterates processing units and calls `operation.execute_unit(unit)`.
4. `SyncOperation` / `CheckOperation` (in `operations/`) partition items by strategy, delegate to `SymlinkManager` / `CopyManager`, and format output inline.
5. Each operation module owns its formatters — `link_sync.py` owns `LinkSyncFormatter`, `link_check.py` owns `LinkCheckFormatter` and the table formatters.

## Key Design Decisions

- Tool and data separation: the CLI is installed once; managed project directories live separately.
- Config paths resolve relative to the config file's directory; target paths resolve relative to CWD.
- `CmdOperation` is an abstract base with `execute_unit()` and `verbose_progress` — new subcommands extend this.
- Each subcommand is a self-contained module: operation logic + user-facing formatting live together.
- `SymlinkManager` owns both symlink logic and `GitExcludeManager` composition.

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
# In operations (e.g., operations/link_sync.py)
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

1. Create a new module in `src/beyond_local_file/operations/` (e.g., `link_repair.py`).
2. Define a `CmdOperation` subclass and its formatter(s) in that module.
3. Re-export the operation class from `operations/__init__.py`.
4. Add a new Click command in `cli.py` under the `link` group (or a new group).
5. If the command has fixed CLI option values (flags/args), define a `StrEnum` in `options.py`. If it presents a numbered interactive prompt, define a plain `Enum` with integer values in `options.py`.
6. Use protocol methods (`create_links()`, `check_links()`, `add_git_excludes()`, `check_git_excludes()`).
7. Operations must check git repo status before calling git exclude methods.
8. All result types come from `link_strategy_protocol.py`.
