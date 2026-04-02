# Architecture Quick Reference

Quick reference for the link strategy management architecture.

## Core Concepts

### Divide-and-Conquer
```
Project Items → PARTITION by strategy → Managers → CONQUER independently
```

### Protocol-Based
```
LinkStrategyManager Protocol → Implemented by all managers → Uniform interface
```

### Composition
```
Unified Result Types + Strategy-Specific Details → Clean separation
```

---

## Key Types

### Result Types (Consistent Naming)

| Type | Purpose | Common Fields | Details Field |
|------|---------|---------------|---------------|
| `LinkCreateResult` | Create operation | created, already_correct, skipped, failed | LinkCreateDetails? |
| `LinkCheckResult` | Check operation | exists, missing | LinkCheckDetails? |
| `GitExcludeAddResult` | Add git exclude | added, existing | N/A |
| `GitExcludeCheckResult` | Check git exclude | present, missing, extra | N/A |

### Details Types (Strategy-Specific)

| Strategy | Create Details | Check Details |
|----------|----------------|---------------|
| Symlink | None | None |
| Copy | `CopyCreateDetails` | `CopyCheckDetails` |
| Future | `FutureCreateDetails` | `FutureCheckDetails` |

---

## Protocol Methods

```python
class LinkStrategyManager(Protocol):
    def get_managed_items(self) -> list[ProjectItem]
    def create_links(self) -> LinkCreateResult
    def check_links(self) -> LinkCheckResult
    def add_git_excludes(self) -> GitExcludeAddResult
    def check_git_excludes(self, all_valid_entries: set[str]) -> GitExcludeCheckResult
```

---

## Manager Checklist

When creating a new manager:

- [ ] Accept `list[ProjectItem]` in constructor (pre-filtered)
- [ ] Implement all 5 protocol methods
- [ ] Return unified result types
- [ ] Create strategy-specific details if needed
- [ ] Set `details=None` if no strategy-specific details
- [ ] Don't filter items internally
- [ ] Don't know about other strategies

---

## Operation Checklist

When creating a new operation:

- [ ] Partition items by strategy
- [ ] Create managers with partitioned items
- [ ] Aggregate `all_valid_entries` from all managers
- [ ] Pass `all_valid_entries` to `check_git_excludes()`
- [ ] Process results uniformly
- [ ] Handle strategy-specific details if needed

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

## File Locations

| Component | File |
|-----------|------|
| Protocol & Result Types | `src/beyond_local_file/link_strategy_protocol.py` |
| SymlinkManager | `src/beyond_local_file/symlink_manager.py` |
| CopyManager | `src/beyond_local_file/copy_manager.py` |
| Operations | `src/beyond_local_file/project_processor.py` |
| Protocol Tests | `tests/unit/test_link_strategy_protocol.py` |
| Manager Tests | `tests/unit/test_symlink_manager.py`, etc. |

---

## Further Reading

- [Full Architecture Design](./architecture-design.md) - Complete design documentation
- [Configuration Reference](./configuration-reference.md) - Configuration examples
- [Development Guide](./development.md) - Development workflow
