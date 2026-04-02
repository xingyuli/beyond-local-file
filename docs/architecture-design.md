# Architecture Design: Link Strategy Management

> **📖 Note**: This document describes the internal architecture. For user-facing configuration, see [configuration-reference.md](configuration-reference.md) and [config-format-clarification.md](config-format-clarification.md).

## Table of Contents

1. [Overview](#overview)
2. [Core Concepts](#core-concepts)
3. [Divide-and-Conquer Strategy](#divide-and-conquer-strategy)
4. [Protocol-Based Architecture](#protocol-based-architecture)
5. [Result Type Design](#result-type-design)
6. [Manager Implementations](#manager-implementations)
7. [Operations Layer](#operations-layer)
8. [Extending the System](#extending-the-system)
9. [Design Principles](#design-principles)
10. [Common Patterns](#common-patterns)

---

## Overview

This document describes the architecture for managing different link strategies (symlink, copy, etc.) in the beyond-local-file project. The design follows a **divide-and-conquer** approach with **protocol-based composition** to enable clean separation of concerns and easy extensibility.

### Key Design Goals

1. **Partition Strategy**: Divide items by strategy, delegate to specialized managers
2. **Unified Interface**: All managers implement the same protocol
3. **Clean Composition**: Strategy-specific details via protocol, not inheritance
4. **Type Safety**: Compile-time guarantees through protocols and type hints
5. **Extensibility**: Add new strategies without modifying existing code

---

## Core Concepts

### The Problem Space

> **⚠️ IMPORTANT**: The YAML example below is a **conceptual illustration** of the internal data model, NOT the actual `config.yml` format. For the real configuration format, see `README.md` and `docs/configuration-reference.md`.

Users configure mappings from managed paths to target paths. Each mapping can use different strategies:

```yaml
# ⚠️ CONCEPTUAL EXAMPLE ONLY - NOT ACTUAL CONFIG FORMAT
projects:
  my-project:
    path: ~/managed/project
    targets:
      - ~/target1
      - ~/target2
    items:
      - name: config.yml
        strategy: symlink  # Create symbolic link
      - name: data.db
        strategy: copy     # Physical copy with sync
```

### The Solution Space

```
┌─────────────────────────────────────────┐
│         Project (All Items)             │
│  [config.yml, data.db, script.sh]      │
└──────────────┬──────────────────────────┘
               │
               │ PARTITION by strategy
               │
       ┌───────┴────────┬────────────┐
       │                │            │
       ▼                ▼            ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Symlink Items│  │  Copy Items  │  │ Future Items │
│ [config.yml] │  │  [data.db]   │  │ [script.sh]  │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                  │
       │ CONQUER         │ CONQUER          │ CONQUER
       │                 │                  │
       ▼                 ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│SymlinkManager│  │ CopyManager  │  │FutureManager │
└──────────────┘  └──────────────┘  └──────────────┘
```

---

## Divide-and-Conquer Strategy

### Conceptual Model

The architecture follows a classic divide-and-conquer pattern:

1. **DIVIDE**: Operations partition items by strategy
2. **CONQUER**: Each manager handles its partition independently
3. **COMBINE**: Operations aggregate results from all managers

### Partition Responsibility

**Operations are responsible for partitioning:**

```python
def execute(self, project: Project, target_path: Path) -> bool:
    # PARTITION: Divide items by strategy
    symlink_items = [i for i in project.items if i.strategy == LinkStrategy.SYMLINK]
    copy_items = [i for i in project.items if i.strategy == LinkStrategy.COPY]
    
    # CONQUER: Delegate to appropriate managers
    if symlink_items:
        symlink_mgr = SymlinkManager(symlink_items, target_path)
        result = symlink_mgr.create_links()
    
    if copy_items:
        copy_mgr = CopyManager(copy_items, target_path, config_dir)
        result = copy_mgr.create_links()
```

**Managers receive only their partition:**

```python
class SymlinkManager:
    def __init__(self, symlink_items: list[ProjectItem], target_path: Path):
        self.symlink_items = symlink_items  # Pre-filtered by caller
        # Manager trusts caller to provide correct items
```

### Why This Matters

**❌ Wrong Approach (Manager filters internally):**
```python
class SymlinkManager:
    def __init__(self, project: Project, target_path: Path):
        self.project = project
        # Manager filters - violates single responsibility
        self._symlink_items = [i for i in project.items if i.strategy == LinkStrategy.SYMLINK]
```

**✅ Correct Approach (Manager receives partition):**
```python
class SymlinkManager:
    def __init__(self, symlink_items: list[ProjectItem], target_path: Path):
        self.symlink_items = symlink_items  # Pre-filtered by caller
        # Manager focuses on execution, not filtering
```

**Benefits:**
- Clear separation of concerns
- Managers don't know about other strategies
- Easy to test managers in isolation
- Consistent interface across all managers

---

## Protocol-Based Architecture

### The LinkStrategyManager Protocol

All managers implement this protocol:

```python
class LinkStrategyManager(Protocol):
    """Protocol for managing link operations (symlink or copy)."""
    
    def get_managed_items(self) -> list[ProjectItem]:
        """Return the list of items this manager handles."""
        ...
    
    def create_links(self) -> LinkCreateResult:
        """Create all links for managed items."""
        ...
    
    def check_links(self) -> LinkCheckResult:
        """Check status of all links for managed items."""
        ...
    
    def add_git_excludes(self) -> GitExcludeAddResult:
        """Add git exclude entries for all managed items."""
        ...
    
    def check_git_excludes(self, all_valid_entries: set[str]) -> GitExcludeCheckResult:
        """Check git exclude status for managed items."""
        ...
```

### Protocol Benefits

1. **Duck Typing**: No inheritance required, just implement the methods
2. **Type Safety**: Type checkers verify protocol compliance
3. **Flexibility**: Managers can have additional methods beyond protocol
4. **Testability**: Easy to create mock implementations

### Protocol Compliance

**SymlinkManager:**
```python
class SymlinkManager:
    # Implements LinkStrategyManager protocol
    def get_managed_items(self) -> list[ProjectItem]: ...
    def create_links(self) -> LinkCreateResult: ...
    def check_links(self) -> LinkCheckResult: ...
    def add_git_excludes(self) -> GitExcludeAddResult: ...
    def check_git_excludes(self, all_valid_entries: set[str]) -> GitExcludeCheckResult: ...
```

**CopyManager:**
```python
class CopyManager:
    # Implements LinkStrategyManager protocol
    def get_managed_items(self) -> list[ProjectItem]: ...
    def create_links(self) -> LinkCreateResult: ...
    def check_links(self) -> LinkCheckResult: ...
    def add_git_excludes(self) -> GitExcludeAddResult: ...
    def check_git_excludes(self, all_valid_entries: set[str]) -> GitExcludeCheckResult: ...
```

---

## Result Type Design

### Naming Convention

All result types follow the pattern: `<Noun><Verb>Result`

```python
LinkCreateResult       # Link + Create + Result
LinkCheckResult        # Link + Check + Result
GitExcludeAddResult    # GitExclude + Add + Result
GitExcludeCheckResult  # GitExclude + Check + Result
```

**Why this pattern?**
- Consistent and predictable
- Easy to remember
- Professional API design
- Scales well with new operations

### Composition Over Inheritance

Result types use **composition** for strategy-specific details:

```python
@dataclass
class LinkCreateResult:
    """Unified result - only common fields."""
    created: set[str]
    already_correct: set[str]
    skipped: set[str]
    failed: set[str]
    details: LinkCreateDetails | None = None  # Strategy-specific details
```

**Why composition?**
- Unified types stay clean (no strategy-specific fields)
- No wasted memory (details=None for strategies without details)
- Type-safe access via isinstance()
- Easy to extend with new strategies

### Details Protocol

Strategy-specific details implement a protocol:

```python
class LinkCreateDetails(Protocol):
    """Protocol for strategy-specific create details."""
    def get_summary(self) -> str:
        """Get a human-readable summary of strategy-specific details."""
        ...

class LinkCheckDetails(Protocol):
    """Protocol for strategy-specific check details."""
    def get_summary(self) -> str:
        """Get a human-readable summary of strategy-specific details."""
        ...
```

### Strategy-Specific Implementations

**Copy Strategy:**
```python
@dataclass
class CopyCreateDetails:
    """Copy-specific details for create operations."""
    reverse_copied: set[str]  # Items synced from target back to managed
    
    def get_summary(self) -> str:
        if self.reverse_copied:
            return f"Reverse copied: {len(self.reverse_copied)} items"
        return "No reverse copies"

@dataclass
class CopyCheckDetails:
    """Copy-specific details for check operations."""
    in_sync: list[str]
    manually_synced: list[str]
    managed_changed: list[str]
    target_changed: list[str]
    both_changed: list[str]
    
    def get_summary(self) -> str:
        parts = []
        if self.in_sync:
            parts.append(f"In sync: {len(self.in_sync)}")
        if self.both_changed:
            parts.append(f"Conflicts: {len(self.both_changed)}")
        return ", ".join(parts) if parts else "No details"
```

**Symlink Strategy:**
```python
# Symlinks don't need strategy-specific details
# result.details = None
```

### Result Type Usage

**Creating Results:**
```python
# Symlink manager - no details
result = LinkCreateResult(
    created={"file1.txt"},
    already_correct=set(),
    skipped=set(),
    failed=set(),
    details=None,  # No strategy-specific details
)

# Copy manager - with details
details = CopyCreateDetails(reverse_copied={"file2.txt"})
result = LinkCreateResult(
    created={"file1.txt"},
    already_correct=set(),
    skipped=set(),
    failed=set(),
    details=details,  # Strategy-specific details
)
```

**Accessing Results:**
```python
# Access common fields uniformly
total_created = len(result.created)
total_failed = len(result.failed)

# Type-safe access to strategy-specific details
if isinstance(result.details, CopyCreateDetails):
    if result.details.reverse_copied:
        print(f"Reverse copied: {result.details.reverse_copied}")

# Or use protocol method
if result.details:
    print(result.details.get_summary())
```

---

## Manager Implementations

### SymlinkManager

**Responsibility**: Create and manage symbolic links

**Constructor:**
```python
def __init__(self, symlink_items: list[ProjectItem], target_path: Path):
    """Initialize with pre-filtered symlink items."""
    self.symlink_items = symlink_items  # Trusts caller to filter
    self.target_path = Path(target_path)
    self.git_manager = GitExcludeManager(self.target_path)
```

**Protocol Implementation:**
```python
def create_links(self, ask_callback=None) -> LinkCreateResult:
    """Create symlinks for all managed items."""
    # Use existing sync() logic
    sync_result = self.sync(ask_callback)
    
    # Map to unified result type
    return LinkCreateResult(
        created=sync_result.created,
        already_correct=sync_result.already_correct,
        skipped=sync_result.skipped,
        failed=sync_result.failed,
        details=None,  # Symlinks don't have strategy-specific details
    )

def check_links(self) -> LinkCheckResult:
    """Check status of symlinks."""
    result = LinkCheckResult()
    
    for item in self.symlink_items:
        link_path = self.target_path / item.name
        if link_path.exists() or link_path.is_symlink():
            result.exists.append(item.name)
        else:
            result.missing.append(item.name)
    
    result.details = None  # No strategy-specific details
    return result
```

**Legacy Methods:**
```python
def sync(self, ask_callback=None) -> SyncResult:
    """Legacy method for backward compatibility."""
    # Existing implementation unchanged
    ...

def check(self, all_item_names=None) -> CheckResult:
    """Legacy method for backward compatibility."""
    # Existing implementation unchanged
    ...
```

### CopyManager

**Responsibility**: Create and manage physical file copies with bidirectional sync

**Constructor:**
```python
def __init__(self, copy_items: list[ProjectItem], target_path: Path, config_dir: Path):
    """Initialize with pre-filtered copy items."""
    self.copy_items = copy_items  # Trusts caller to filter
    self.target_path = target_path
    self.config_dir = config_dir
    self.sync_state = SyncState(config_dir)
    self.sync_state.load()
    self.git_manager = GitExcludeManager(target_path)
```

**Protocol Implementation:**
```python
def create_links(self, conflict_callback=None) -> LinkCreateResult:
    """Create copies for all managed items."""
    # Use existing sync() logic
    copy_result = self.sync(conflict_callback)
    
    # Create strategy-specific details
    details = CopyCreateDetails(reverse_copied=copy_result.reverse_copied)
    
    # Map to unified result type
    return LinkCreateResult(
        created=copy_result.copied,
        already_correct=copy_result.in_sync,
        skipped=copy_result.skipped,
        failed=copy_result.failed,
        details=details,  # Copy-specific details
    )

def check_links(self) -> LinkCheckResult:
    """Check status of copies."""
    # Use existing check() logic
    copy_check = self.check()
    
    # Create strategy-specific details
    details = CopyCheckDetails(
        in_sync=copy_check.in_sync,
        manually_synced=copy_check.manually_synced,
        managed_changed=copy_check.managed_changed,
        target_changed=copy_check.target_changed,
        both_changed=copy_check.both_changed,
    )
    
    # Map to unified result type
    result = LinkCheckResult()
    result.exists = copy_check.in_sync + copy_check.manually_synced
    result.missing = copy_check.missing
    result.details = details  # Copy-specific details
    
    return result
```

**Legacy Methods:**
```python
def sync(self, conflict_callback=None) -> CopyResult:
    """Legacy method for backward compatibility."""
    # Existing implementation unchanged
    ...

def check(self) -> CopyCheckResult:
    """Legacy method for backward compatibility."""
    # Existing implementation unchanged
    ...
```

---

## Operations Layer

### SyncOperation

**Responsibility**: Coordinate sync operations across all strategies

```python
class SyncOperation(CmdOperation):
    def execute(self, project: Project, target_path: Path) -> bool:
        """Execute sync using divide-and-conquer strategy."""
        
        # PARTITION: Divide items by strategy
        symlink_items = [i for i in project.items if i.strategy == LinkStrategy.SYMLINK]
        copy_items = [i for i in project.items if i.strategy == LinkStrategy.COPY]
        
        # CONQUER: Delegate to appropriate managers
        
        # Handle symlink items
        if symlink_items:
            manager = SymlinkManager(symlink_items, target_path)
            result = manager.sync(self.ask_callback)
            
            # Format and display results
            formatter = SyncResultFormatter(project, result)
            formatter.format(project.name, target_path)
            
            if result.aborted:
                return False
        
        # Handle copy items
        if copy_items:
            copy_mgr = CopyManager(copy_items, target_path, self.config_dir)
            copy_result = copy_mgr.sync(self.conflict_callback)
            
            # Format and display results
            CopyResultFormatter(copy_result).format(project.name, target_path)
        
        return True
```

### CheckOperation

**Responsibility**: Coordinate check operations across all strategies

```python
class CheckOperation(CmdOperation):
    def execute(self, project: Project, target_path: Path) -> bool:
        """Execute check using divide-and-conquer strategy."""
        
        # PARTITION: Divide items by strategy
        symlink_items = [i for i in project.items if i.strategy == LinkStrategy.SYMLINK]
        copy_items = [i for i in project.items if i.strategy == LinkStrategy.COPY]
        
        # CONQUER: Create managers with partitioned items
        symlink_mgr = SymlinkManager(symlink_items, target_path) if symlink_items else None
        copy_mgr = CopyManager(copy_items, target_path, self.config_dir) if copy_items else None
        
        # COMBINE: Collect all valid entries for git exclude checking
        all_valid_entries: set[str] = set()
        if symlink_mgr:
            all_valid_entries.update(i.name for i in symlink_mgr.get_managed_items())
        if copy_mgr:
            all_valid_entries.update(i.name for i in copy_mgr.get_managed_items())
        
        # Execute checks
        if symlink_mgr:
            symlink_result = symlink_mgr.check()
            
            # Check git excludes with aggregated entries
            if symlink_mgr.git_manager.is_git_repo():
                git_result = symlink_mgr.check_git_excludes(all_valid_entries)
                # Map to legacy result for backward compatibility
                symlink_result.exclude_present = git_result.present
                symlink_result.exclude_missing = git_result.missing
                symlink_result.exclude_extra = git_result.extra
        
        if copy_mgr:
            copy_result = copy_mgr.check()
        
        # Format and display results
        # ...
        
        return True
```

### Git Exclude Aggregation

**Why aggregate?**

Git exclude entries should include ALL managed items (symlink + copy), not just one strategy's items. This prevents items from one strategy being reported as "extra" entries.

**How it works:**

1. **Collect**: Get all item names from all managers
2. **Pass**: Pass aggregated set to each manager's `check_git_excludes()`
3. **Identify**: Each manager can correctly identify extra entries

```python
# Collect all valid entries from ALL managers
all_valid_entries: set[str] = set()
if symlink_mgr:
    all_valid_entries.update(i.name for i in symlink_mgr.get_managed_items())
if copy_mgr:
    all_valid_entries.update(i.name for i in copy_mgr.get_managed_items())

# Pass to each manager for checking
git_result = symlink_mgr.check_git_excludes(all_valid_entries)
# Now git_result.extra only contains truly extra entries
```

---

## Extending the System

### Adding a New Strategy

**Step 1: Define the strategy enum**

```python
# In options.py
class LinkStrategy(StrEnum):
    SYMLINK = "symlink"
    COPY = "copy"
    HARDLINK = "hardlink"  # New strategy
```

**Step 2: Create strategy-specific details (if needed)**

```python
# In link_strategy_protocol.py
@dataclass
class HardlinkCreateDetails:
    """Hardlink-specific details for create operations."""
    hardlink_count: int
    
    def get_summary(self) -> str:
        return f"Created {self.hardlink_count} hardlinks"

@dataclass
class HardlinkCheckDetails:
    """Hardlink-specific details for check operations."""
    broken_links: list[str]
    
    def get_summary(self) -> str:
        if self.broken_links:
            return f"Broken links: {len(self.broken_links)}"
        return "All links valid"
```

**Step 3: Create the manager**

```python
# In hardlink_manager.py
class HardlinkManager:
    """Manages hardlink creation and checking."""
    
    def __init__(self, hardlink_items: list[ProjectItem], target_path: Path):
        """Initialize with pre-filtered hardlink items."""
        self.hardlink_items = hardlink_items
        self.target_path = target_path
        self.git_manager = GitExcludeManager(target_path)
    
    # Implement LinkStrategyManager protocol
    
    def get_managed_items(self) -> list[ProjectItem]:
        return self.hardlink_items
    
    def create_links(self) -> LinkCreateResult:
        """Create hardlinks for all managed items."""
        result = LinkCreateResult()
        hardlink_count = 0
        
        for item in self.hardlink_items:
            target_file = self.target_path / item.name
            try:
                os.link(item.source_path, target_file)
                result.created.add(item.name)
                hardlink_count += 1
            except OSError:
                result.failed.add(item.name)
        
        # Add strategy-specific details
        details = HardlinkCreateDetails(hardlink_count=hardlink_count)
        result.details = details
        
        return result
    
    def check_links(self) -> LinkCheckResult:
        """Check status of hardlinks."""
        result = LinkCheckResult()
        broken_links = []
        
        for item in self.hardlink_items:
            target_file = self.target_path / item.name
            if target_file.exists():
                # Check if it's actually a hardlink (same inode)
                if target_file.stat().st_ino == item.source_path.stat().st_ino:
                    result.exists.append(item.name)
                else:
                    broken_links.append(item.name)
            else:
                result.missing.append(item.name)
        
        # Add strategy-specific details
        details = HardlinkCheckDetails(broken_links=broken_links)
        result.details = details
        
        return result
    
    def add_git_excludes(self) -> GitExcludeAddResult:
        """Add git exclude entries for hardlink items."""
        result = GitExcludeAddResult()
        
        if not self.git_manager.is_git_repo():
            return result
        
        item_names = {i.name for i in self.hardlink_items}
        if item_names:
            added, existing = self.git_manager.write_entries(item_names)
            result.added = added
            result.existing = existing
        
        return result
    
    def check_git_excludes(self, all_valid_entries: set[str]) -> GitExcludeCheckResult:
        """Check git exclude status for hardlink items."""
        result = GitExcludeCheckResult()
        
        if not self.git_manager.is_git_repo():
            item_names = {i.name for i in self.hardlink_items}
            result.missing = item_names
            return result
        
        exclude_entries = self.git_manager.read_entries()
        item_names = {i.name for i in self.hardlink_items}
        
        result.present = item_names & exclude_entries
        result.missing = item_names - exclude_entries
        result.extra = exclude_entries - all_valid_entries
        
        return result
```

**Step 4: Update operations**

```python
# In project_processor.py
class SyncOperation(CmdOperation):
    def execute(self, project: Project, target_path: Path) -> bool:
        # PARTITION
        symlink_items = [i for i in project.items if i.strategy == LinkStrategy.SYMLINK]
        copy_items = [i for i in project.items if i.strategy == LinkStrategy.COPY]
        hardlink_items = [i for i in project.items if i.strategy == LinkStrategy.HARDLINK]  # New
        
        # CONQUER
        if symlink_items:
            # ... existing code
        
        if copy_items:
            # ... existing code
        
        if hardlink_items:  # New
            hardlink_mgr = HardlinkManager(hardlink_items, target_path)
            result = hardlink_mgr.create_links()
            # Format and display results
        
        return True
```

**That's it!** No changes to existing managers needed.

---

## Design Principles

### 1. Single Responsibility Principle (SRP)

**Operations:**
- Responsible for partitioning items by strategy
- Responsible for coordinating between managers
- Responsible for aggregating results

**Managers:**
- Responsible for executing their specific strategy
- NOT responsible for filtering items
- NOT responsible for knowing about other strategies

**Result Types:**
- Responsible for common fields only
- NOT responsible for strategy-specific fields

**Details Types:**
- Responsible for strategy-specific fields only

### 2. Open/Closed Principle (OCP)

**Open for extension:**
- Add new strategies by creating new managers
- Add new details by creating new detail types

**Closed for modification:**
- Existing managers don't change when adding new strategies
- Unified result types don't change when adding new strategies
- Protocol doesn't change when adding new strategies

### 3. Liskov Substitution Principle (LSP)

All managers implement `LinkStrategyManager` protocol and can be used interchangeably:

```python
def process_manager(manager: LinkStrategyManager) -> None:
    """Works with any manager that implements the protocol."""
    items = manager.get_managed_items()
    result = manager.create_links()
    # ... process result
```

### 4. Interface Segregation Principle (ISP)

**Unified result types have minimal interface:**
- Only common fields that all strategies need
- No strategy-specific fields

**Details types have strategy-specific interface:**
- Only fields relevant to that strategy
- Implement minimal protocol (`get_summary()`)

### 5. Dependency Inversion Principle (DIP)

**Operations depend on abstractions:**
- Depend on `LinkStrategyManager` protocol, not concrete managers
- Depend on unified result types, not strategy-specific types

**Managers depend on abstractions:**
- Depend on `ProjectItem` interface
- Depend on `GitExcludeManager` interface

---

## Common Patterns

### Pattern 1: Partition and Delegate

```python
# PARTITION
symlink_items = [i for i in project.items if i.strategy == LinkStrategy.SYMLINK]
copy_items = [i for i in project.items if i.strategy == LinkStrategy.COPY]

# DELEGATE
if symlink_items:
    manager = SymlinkManager(symlink_items, target_path)
    result = manager.create_links()

if copy_items:
    manager = CopyManager(copy_items, target_path, config_dir)
    result = manager.create_links()
```

### Pattern 2: Aggregate and Pass

```python
# AGGREGATE
all_valid_entries: set[str] = set()
for manager in managers:
    all_valid_entries.update(i.name for i in manager.get_managed_items())

# PASS
for manager in managers:
    git_result = manager.check_git_excludes(all_valid_entries)
```

### Pattern 3: Type-Safe Details Access

```python
# Check if details exist
if result.details:
    # Use protocol method
    print(result.details.get_summary())

# Type-safe access to specific details
if isinstance(result.details, CopyCreateDetails):
    if result.details.reverse_copied:
        print(f"Reverse copied: {result.details.reverse_copied}")
```

### Pattern 4: Uniform Result Processing

```python
# Process results uniformly across all strategies
def process_result(result: LinkCreateResult) -> None:
    """Process result from any manager."""
    print(f"Created: {len(result.created)}")
    print(f"Failed: {len(result.failed)}")
    
    # Access strategy-specific details if available
    if result.details:
        print(f"Details: {result.details.get_summary()}")
```

---

## Summary

This architecture provides:

1. **Clean Partition Strategy** - Operations divide, managers conquer
2. **Protocol-Based Design** - Uniform interface, flexible implementation
3. **Composition Over Inheritance** - Strategy-specific details via protocol
4. **Type Safety** - Compile-time guarantees through protocols
5. **Extensibility** - Add new strategies without modifying existing code
6. **SOLID Principles** - Follows all five principles
7. **Testability** - Easy to test each component in isolation

The design properly supports multiple link strategies while maintaining clean separation of concerns and enabling easy extension with new strategies in the future.


---

## See Also

- **[Architecture Quick Reference](architecture-quick-reference.md)** - Quick overview of the architecture
- **[Config Format Clarification](config-format-clarification.md)** - Understanding config vs architecture
- **[Development Guide](development.md)** - Contributing and development setup
- **[Configuration Reference](configuration-reference.md)** - User-facing configuration guide
