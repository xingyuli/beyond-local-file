# Design: Divide-and-Conquer Strategy Management

> **📖 Note**: This document describes the divide-and-conquer pattern for managing link strategies. For an overview, see [design-overview.md](design-overview.md). For model architecture, see [design-model-separation.md](design-model-separation.md).

## Table of Contents

1. [Overview](#overview)
2. [The Problem Space](#the-problem-space)
3. [The Solution Space](#the-solution-space)
4. [Divide-and-Conquer Strategy](#divide-and-conquer-strategy)
5. [Protocol-Based Architecture](#protocol-based-architecture)
6. [Result Type Design](#result-type-design)
7. [Manager Implementations](#manager-implementations)
8. [Operations Layer](#operations-layer)
9. [Extending the System](#extending-the-system)
10. [Code Templates](#code-templates)
11. [Common Mistakes](#common-mistakes)
12. [Testing Patterns](#testing-patterns)

---

## Overview

This document describes the architecture for managing different link strategies (symlink, copy, etc.). The design follows a **divide-and-conquer** approach with **protocol-based composition** to enable clean separation of concerns and easy extensibility.

### Key Concepts

```
Project Items → PARTITION by strategy → Managers → CONQUER independently
```

---

## The Problem Space

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

---

## The Solution Space

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

See the full example in the original architecture-design.md document. The key steps are:

1. Define the strategy enum
2. Create strategy-specific details (if needed)
3. Create the manager implementing LinkStrategyManager protocol
4. Update operations to partition and delegate

**That's it!** No changes to existing managers needed.

---

## Code Templates

### New Manager Template

```python
class NewStrategyManager:
    def __init__(self, items: list[ProjectItem], target_path: Path):
        self.items = items  # Pre-filtered by caller
        self.target_path = target_path
        self.git_manager = GitExcludeManager(target_path)
    
    def get_managed_items(self) -> list[ProjectItem]:
        return self.items
    
    def create_links(self) -> LinkCreateResult:
        result = LinkCreateResult()
        # ... implementation
        result.details = NewCreateDetails(...) if needed else None
        return result
    
    def check_links(self) -> LinkCheckResult:
        result = LinkCheckResult()
        # ... implementation
        result.details = NewCheckDetails(...) if needed else None
        return result
    
    def add_git_excludes(self) -> GitExcludeAddResult:
        result = GitExcludeAddResult()
        if not self.git_manager.is_git_repo():
            return result
        item_names = {i.name for i in self.items}
        if item_names:
            added, existing = self.git_manager.write_entries(item_names)
            result.added = added
            result.existing = existing
        return result
    
    def check_git_excludes(self, all_valid_entries: set[str]) -> GitExcludeCheckResult:
        result = GitExcludeCheckResult()
        if not self.git_manager.is_git_repo():
            result.missing = {i.name for i in self.items}
            return result
        exclude_entries = self.git_manager.read_entries()
        item_names = {i.name for i in self.items}
        result.present = item_names & exclude_entries
        result.missing = item_names - exclude_entries
        result.extra = exclude_entries - all_valid_entries
        return result
```

### New Details Template

```python
@dataclass
class NewCreateDetails:
    """Strategy-specific details for create operations."""
    field1: type1
    field2: type2
    
    def get_summary(self) -> str:
        return f"Summary: {self.field1}, {self.field2}"

@dataclass
class NewCheckDetails:
    """Strategy-specific details for check operations."""
    field1: type1
    field2: type2
    
    def get_summary(self) -> str:
        return f"Summary: {self.field1}, {self.field2}"
```

### Operation Partition Template

```python
def execute(self, project: Project, target_path: Path) -> bool:
    # PARTITION
    strategy1_items = [i for i in project.items if i.strategy == Strategy.ONE]
    strategy2_items = [i for i in project.items if i.strategy == Strategy.TWO]
    
    # CONQUER
    if strategy1_items:
        mgr = Strategy1Manager(strategy1_items, target_path)
        result = mgr.create_links()
        # ... process result
    
    if strategy2_items:
        mgr = Strategy2Manager(strategy2_items, target_path)
        result = mgr.create_links()
        # ... process result
    
    return True
```

### Git Exclude Aggregation Template

```python
# AGGREGATE
all_valid_entries: set[str] = set()
if manager1:
    all_valid_entries.update(i.name for i in manager1.get_managed_items())
if manager2:
    all_valid_entries.update(i.name for i in manager2.get_managed_items())

# PASS
if manager1:
    git_result = manager1.check_git_excludes(all_valid_entries)
if manager2:
    git_result = manager2.check_git_excludes(all_valid_entries)
```

---

## Common Mistakes

### ❌ Manager Filters Internally
```python
class Manager:
    def __init__(self, project: Project, target_path: Path):
        self.items = [i for i in project.items if i.strategy == MY_STRATEGY]
```

### ✅ Manager Receives Partition
```python
class Manager:
    def __init__(self, items: list[ProjectItem], target_path: Path):
        self.items = items  # Pre-filtered by caller
```

---

### ❌ Strategy-Specific Fields in Unified Type
```python
@dataclass
class LinkCreateResult:
    created: set[str]
    reverse_copied: set[str]  # Copy-specific!
```

### ✅ Strategy-Specific Fields in Details
```python
@dataclass
class LinkCreateResult:
    created: set[str]
    details: LinkCreateDetails | None = None

@dataclass
class CopyCreateDetails:
    reverse_copied: set[str]
```

---

### ❌ Inconsistent Naming
```python
LinkOperationResult  # Has "Operation"
LinkCheckResult      # No suffix
```

### ✅ Consistent Naming
```python
LinkCreateResult  # Verb + Result
LinkCheckResult   # Verb + Result
```

---

## Testing Patterns

### Test Manager in Isolation
```python
def test_manager():
    items = [ProjectItem(name="file.txt", strategy=MY_STRATEGY, ...)]
    manager = MyManager(items, target_path)
    result = manager.create_links()
    assert "file.txt" in result.created
```

### Test Protocol Compliance
```python
def test_protocol_compliance():
    manager = MyManager(items, target_path)
    assert hasattr(manager, "get_managed_items")
    assert hasattr(manager, "create_links")
    assert hasattr(manager, "check_links")
    assert hasattr(manager, "add_git_excludes")
    assert hasattr(manager, "check_git_excludes")
```

### Test Result Types
```python
def test_result_types():
    result = manager.create_links()
    assert isinstance(result, LinkCreateResult)
    assert hasattr(result, "created")
    assert hasattr(result, "details")
```

---

## Summary

The divide-and-conquer architecture provides:

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

- **[design-overview.md](design-overview.md)** - Architecture overview
- **[design-model-separation.md](design-model-separation.md)** - Two-model architecture details
- **[configuration-reference.md](configuration-reference.md)** - Configuration format guide
- **[development.md](development.md)** - Development workflow
