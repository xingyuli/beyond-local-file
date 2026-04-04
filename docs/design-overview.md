# Design Overview

> **📖 Note**: This document provides a high-level overview of the system architecture. For detailed information, see [design-divide-and-conquer.md](design-divide-and-conquer.md) and [design-model-separation.md](design-model-separation.md).

## Table of Contents

1. [Introduction](#introduction)
2. [Core Design Principles](#core-design-principles)
3. [Architecture Layers](#architecture-layers)
4. [Key Design Patterns](#key-design-patterns)
5. [Quick Reference](#quick-reference)
6. [Further Reading](#further-reading)

---

## Introduction

The beyond-local-file system manages different link strategies (symlink, copy, etc.) for synchronizing files between managed projects and target locations. The architecture follows three core design patterns:

1. **Model Separation**: Configuration models (YAML structure) vs Processing models (execution structure)
2. **Divide-and-Conquer**: Partition items by strategy, delegate to specialized managers
3. **Protocol-Based Composition**: Uniform interface with strategy-specific details

### Design Goals

- **Separation of Concerns**: Clear boundaries between layers
- **Type Safety**: Compile-time guarantees through protocols
- **Extensibility**: Add new strategies without modifying existing code
- **Testability**: Easy to test each component in isolation
- **Maintainability**: Clean code that's easy to understand and modify

---

## Core Design Principles

### SOLID Principles

**Single Responsibility Principle (SRP)**
- Operations: partition and coordinate
- Managers: execute specific strategy
- Config: parse YAML
- Translator: convert config to processing units

**Open/Closed Principle (OCP)**
- Open for extension: add new strategies by creating new managers
- Closed for modification: existing code doesn't change

**Liskov Substitution Principle (LSP)**
- All managers implement `LinkStrategyManager` protocol
- Can be used interchangeably

**Interface Segregation Principle (ISP)**
- Unified result types have minimal interface
- Details types have strategy-specific interface

**Dependency Inversion Principle (DIP)**
- Depend on abstractions (protocols), not concrete implementations

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI Layer                            │
│  (User commands: sync, check)                               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Configuration Layer                       │
│  YAML → ConfigProject (with Mappings)                       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Translation Layer                         │
│  ConfigProject → ProcessingUnit (M×N expansion)             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Operations Layer                          │
│  Partition by strategy, coordinate managers                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                     Manager Layer                            │
│  SymlinkManager, CopyManager (protocol-based)               │
└─────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

**CLI Layer** (`cli.py`)
- Parse command-line arguments
- Load configuration
- Invoke operations

**Configuration Layer** (`config.py`, `model/config.py`)
- Parse YAML files
- Validate configuration
- Return ConfigProject instances

**Translation Layer** (`model/translator.py`)
- Convert ConfigProject to ProcessingUnit
- Expand M mappings × N targets
- Generate display names with suffixes

**Operations Layer** (`project_processor.py`)
- Partition items by strategy
- Create and coordinate managers
- Aggregate results

**Manager Layer** (`symlink_manager.py`, `copy_manager.py`)
- Execute strategy-specific operations
- Implement LinkStrategyManager protocol
- Return unified result types

---

## Key Design Patterns

### 1. Model Separation Pattern

**Problem**: Configuration structure doesn't match execution structure

**Solution**: Two separate model layers
- Config models reflect YAML grammar (user intent)
- Processing models reflect execution structure (M×N expansion)
- Translation layer converts between them

**Benefits**:
- Config layer purely handles YAML parsing
- Processing layer focuses on execution
- Easy to test separately

See [design-model-separation.md](design-model-separation.md) for details.

### 2. Divide-and-Conquer Pattern

**Problem**: Different strategies need different handling

**Solution**: Partition items by strategy, delegate to specialized managers
- Operations partition items
- Managers handle their partition independently
- Results are aggregated

**Benefits**:
- Managers don't know about other strategies
- Easy to add new strategies
- Clean separation of concerns

See [design-divide-and-conquer.md](design-divide-and-conquer.md) for details.

### 3. Protocol-Based Composition

**Problem**: Need uniform interface without inheritance

**Solution**: Protocol defines interface, composition for details
- All managers implement LinkStrategyManager protocol
- Unified result types for common fields
- Strategy-specific details via composition

**Benefits**:
- Duck typing with type safety
- No inheritance required
- Flexible and extensible

See [design-divide-and-conquer.md](design-divide-and-conquer.md) for details.

---

## Quick Reference

### Result Types (Consistent Naming)

| Type | Purpose | Common Fields | Details Field |
|------|---------|---------------|---------------|
| `LinkCreateResult` | Create operation | created, already_correct, skipped, failed | LinkCreateDetails? |
| `LinkCheckResult` | Check operation | exists, missing | LinkCheckDetails? |
| `GitExcludeAddResult` | Add git exclude | added, existing | N/A |
| `GitExcludeCheckResult` | Check git exclude | present, missing, extra | N/A |

### Protocol Methods

```python
class LinkStrategyManager(Protocol):
    def get_managed_items(self) -> list[ProjectItem]
    def create_links(self) -> LinkCreateResult
    def check_links(self) -> LinkCheckResult
    def add_git_excludes(self) -> GitExcludeAddResult
    def check_git_excludes(self, all_valid_entries: set[str]) -> GitExcludeCheckResult
```

### Manager Checklist

When creating a new manager:

- [ ] Accept `list[ProjectItem]` in constructor (pre-filtered)
- [ ] Implement all 5 protocol methods
- [ ] Return unified result types
- [ ] Create strategy-specific details if needed
- [ ] Set `details=None` if no strategy-specific details
- [ ] Don't filter items internally
- [ ] Don't know about other strategies

### Operation Checklist

When creating a new operation:

- [ ] Partition items by strategy
- [ ] Create managers with partitioned items
- [ ] Aggregate `all_valid_entries` from all managers
- [ ] Pass `all_valid_entries` to `check_git_excludes()`
- [ ] Process results uniformly
- [ ] Handle strategy-specific details if needed

---

## Further Reading

### Design Documentation
- **[design-model-separation.md](design-model-separation.md)** - Two-model architecture details
- **[design-divide-and-conquer.md](design-divide-and-conquer.md)** - Strategy management details

### User Documentation
- **[configuration-reference.md](configuration-reference.md)** - Configuration format and examples
- **[config-format-clarification.md](config-format-clarification.md)** - Config vs architecture clarification

### Development
- **[development.md](development.md)** - Development workflow and contributing
- **[cli-reference.md](cli-reference.md)** - CLI command reference

---

## File Locations

| Component | File |
|-----------|------|
| Config Models | `src/beyond_local_file/model/config.py` |
| Processing Models | `src/beyond_local_file/model/processing.py` |
| Translator | `src/beyond_local_file/model/translator.py` |
| Protocol & Result Types | `src/beyond_local_file/link_strategy_protocol.py` |
| SymlinkManager | `src/beyond_local_file/symlink_manager.py` |
| CopyManager | `src/beyond_local_file/copy_manager.py` |
| Operations | `src/beyond_local_file/project_processor.py` |
| CLI | `src/beyond_local_file/cli.py` |

---

## Summary

The beyond-local-file architecture provides:

1. **Model Separation** - Config vs Processing models with translation layer
2. **Divide-and-Conquer** - Operations partition, managers conquer
3. **Protocol-Based Design** - Uniform interface, flexible implementation
4. **Composition Over Inheritance** - Strategy-specific details via protocol
5. **Type Safety** - Compile-time guarantees through protocols
6. **Extensibility** - Add new strategies without modifying existing code
7. **SOLID Principles** - Follows all five principles
8. **Testability** - Easy to test each component in isolation

The design properly supports multiple link strategies while maintaining clean separation of concerns and enabling easy extension with new strategies in the future.
