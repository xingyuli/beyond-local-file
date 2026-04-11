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

### Current Strategy Types

The system currently supports two link strategies:

| Strategy | Manager | Purpose | Details Type |
|----------|---------|---------|--------------|
| Symlink | `SymlinkManager` | Creates symbolic links | None (no strategy-specific details) |
| Copy | `CopyManager` | Creates physical copies with bidirectional sync | `CopyCreateDetails`, `CopyCheckDetails` |

**Key Points:**
- All managers implement the `LinkStrategyManager` protocol
- Managers receive pre-filtered items from operations (divide-and-conquer)
- Managers return unified result types (`LinkCreateResult`, `LinkCheckResult`)
- Strategy-specific information is provided via optional `details` field

**For implementation details**, see the source code:
- `src/beyond_local_file/symlink_manager.py`
- `src/beyond_local_file/copy_manager.py`
- `src/beyond_local_file/link_strategy_protocol.py`

---

## Operations Layer

### Overview

Operations coordinate work across multiple strategy managers using the divide-and-conquer pattern:

1. **PARTITION**: Divide items by strategy
2. **CONQUER**: Create managers and delegate to them
3. **COMBINE**: Aggregate results (especially for git exclude checking)

### Key Responsibilities

**SyncOperation:**
- Partition items by strategy
- Create appropriate managers with partitioned items
- Call `create_links()` on each manager
- Format and display results
- Handle abort signals

**CheckOperation:**
- Partition items by strategy
- Create appropriate managers with partitioned items
- Aggregate all valid entries for git exclude checking
- Call `check_links()` and `check_git_excludes()` on each manager
- Format and display results

### Git Exclude Aggregation

Git exclude entries should include ALL managed items (symlink + copy), not just one strategy's items. Operations collect all item names from all managers and pass this aggregated set to each manager's `check_git_excludes()` method.

**Why?** This prevents items from one strategy being incorrectly reported as "extra" entries.

**For implementation details**, see `src/beyond_local_file/project_processor.py`

---

## Extending the System

### Adding a New Strategy

To add a new link strategy:

1. **Define the strategy enum value** in `options.py`
2. **Create strategy-specific details** (if needed) implementing `LinkCreateDetails` and/or `LinkCheckDetails` protocols
3. **Create the manager class** implementing `LinkStrategyManager` protocol
4. **Update operations** in `project_processor.py` to partition and delegate to your new manager

**That's it!** No changes to existing managers needed.

**For detailed implementation guidance**, see `docs/development.md` section "Implementing a New Link Strategy"

---

## Code Templates

### Conceptual Templates

These templates show the conceptual structure for extending the system. For complete, working examples, see the source code.

### New Manager Structure

```python
class NewStrategyManager:
    def __init__(self, items: list[ProjectItem], target_path: Path):
        self.items = items  # Pre-filtered by caller
        self.target_path = target_path
        self.git_manager = GitExcludeManager(target_path)
    
    # Implement all 5 protocol methods:
    def get_managed_items(self) -> list[ProjectItem]: ...
    def create_links(self) -> LinkCreateResult: ...
    def check_links(self) -> LinkCheckResult: ...
    def add_git_excludes(self) -> GitExcludeAddResult: ...
    def check_git_excludes(self, all_valid_entries: set[str]) -> GitExcludeCheckResult: ...
```

### New Details Structure

```python
@dataclass
class NewCreateDetails:
    """Strategy-specific details for create operations."""
    field1: type1
    
    def get_summary(self) -> str:
        return f"Summary: {self.field1}"

@dataclass
class NewCheckDetails:
    """Strategy-specific details for check operations."""
    field1: type1
    
    def get_summary(self) -> str:
        return f"Summary: {self.field1}"
```

### Operation Partition Pattern

```python
# PARTITION
strategy1_items = [i for i in project.items if i.strategy == Strategy.ONE]
strategy2_items = [i for i in project.items if i.strategy == Strategy.TWO]

# CONQUER
if strategy1_items:
    mgr = Strategy1Manager(strategy1_items, target_path)
    result = mgr.create_links()

if strategy2_items:
    mgr = Strategy2Manager(strategy2_items, target_path)
    result = mgr.create_links()
```

### Git Exclude Aggregation Pattern

```python
# AGGREGATE all valid entries from all managers
all_valid_entries: set[str] = set()
if manager1:
    all_valid_entries.update(i.name for i in manager1.get_managed_items())
if manager2:
    all_valid_entries.update(i.name for i in manager2.get_managed_items())

# PASS to each manager for checking
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
    # Verify all protocol methods exist
    assert callable(getattr(manager, "get_managed_items", None))
    assert callable(getattr(manager, "create_links", None))
    assert callable(getattr(manager, "check_links", None))
    assert callable(getattr(manager, "add_git_excludes", None))
    assert callable(getattr(manager, "check_git_excludes", None))
```

### Test Result Types

```python
def test_result_types():
    result = manager.create_links()
    assert isinstance(result, LinkCreateResult)
    assert hasattr(result, "created")
    assert hasattr(result, "details")
```

**For complete test examples**, see `tests/unit/test_link_strategy_protocol.py` and related test files.

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
