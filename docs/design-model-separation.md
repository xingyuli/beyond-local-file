# Design: Model Separation

> **📖 Note**: This document describes the two-model architecture. For an overview, see [design-overview.md](design-overview.md). For strategy management, see [design-divide-and-conquer.md](design-divide-and-conquer.md).

## Table of Contents

1. [Overview](#overview)
2. [The Problem](#the-problem)
3. [The Solution](#the-solution)
4. [Configuration Models](#configuration-models)
5. [Processing Models](#processing-models)
6. [Translation Layer](#translation-layer)
7. [Display Name Logic](#display-name-logic)
8. [Benefits](#benefits)
9. [Examples](#examples)
10. [Implementation Details](#implementation-details)

---

## Overview

The system separates configuration models (reflecting YAML structure) from processing models (reflecting execution structure). This separation ensures the config layer purely handles YAML parsing while the processing layer focuses on execution.

### Key Concept

```
YAML Config → ConfigProject (with Mappings)
           → Translation Layer
           → ProcessingUnit (M×N expansion)
           → Execution
```

---

## The Problem

### Configuration vs Execution Mismatch

When a project maps to multiple targets, the configuration structure doesn't match the execution structure:

**Configuration (User Intent)**:
```yaml
my-project:
  - /target1
  - target: [/target2, /target3]
    subpath: [.kiro/hooks]
```

**Execution (What Actually Runs)**:
- Process my-project → /target1 (sync everything)
- Process my-project → /target2 (sync .kiro/hooks only)
- Process my-project → /target3 (sync .kiro/hooks only)

The configuration defines 2 mappings with 3 total targets, but execution requires 3 separate processing units.

---

## The Solution

### Two Distinct Model Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    Configuration Layer                       │
│  (Reflects YAML grammar - user intent)                      │
│                                                              │
│  ConfigProject                                              │
│  ├── managed_project_name: "my-project"                    │
│  ├── managed_project_path: /path/to/my-project             │
│  └── mappings: [                                            │
│      Mapping(targets=[/target1], subpaths=None),           │
│      Mapping(targets=[/target2, /target3],                 │
│              subpaths=[".kiro/hooks"])                      │
│  ]                                                           │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ translate_config_to_processing()
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Processing Layer                          │
│  (Reflects execution structure - M×N expansion)             │
│                                                              │
│  ProcessingUnit #1                                          │
│  ├── display_name: "my-project#1"                          │
│  ├── managed_project_path: /path/to/my-project             │
│  ├── target_project_path: /target1                         │
│  └── items: None (sync everything)                          │
│                                                              │
│  ProcessingUnit #2                                          │
│  ├── display_name: "my-project#2-1"                        │
│  ├── managed_project_path: /path/to/my-project             │
│  ├── target_project_path: /target2                         │
│  └── items: [ProjectItem(".kiro/hooks", ...)]              │
│                                                              │
│  ProcessingUnit #3                                          │
│  ├── display_name: "my-project#2-2"                        │
│  ├── managed_project_path: /path/to/my-project             │
│  ├── target_project_path: /target3                         │
│  └── items: [ProjectItem(".kiro/hooks", ...)]              │
└─────────────────────────────────────────────────────────────┘
```

---

## Configuration Models

Located in `src/beyond_local_file/model/config.py`

### ConfigProject

Represents a project with its mappings.

```python
@dataclass
class ConfigProject:
    """Project configuration with list of mappings.
    
    Attributes:
        managed_project_name: Project name from configuration.
        managed_project_path: Absolute path to managed project directory.
        mappings: List of mappings defining targets and sync rules.
    """
    managed_project_name: str
    managed_project_path: Path
    mappings: list[Mapping]
```

**Key Points**:
- Uses `managed_project_name` and `managed_project_path` for clarity
- Contains a list of `Mapping` objects (not split by targets)
- Directly reflects YAML grammar structure

### Mapping

Represents a single mapping entry (string-mapping or dict-mapping).

```python
@dataclass
class Mapping:
    """Single mapping with targets and optional rules.
    
    Attributes:
        targets: List of target paths (can have multiple).
        subpaths: Optional list of relative subpaths for selective sync.
        copy_paths: Optional set of subpath names using copy strategy.
    """
    targets: list[Path]
    subpaths: list[str] | None = None
    copy_paths: set[str] | None = None
```

**Key Points**:
- Each mapping has its own targets, subpaths, and copy_paths
- Targets can be a list (from `target: [t1, t2]`)
- Preserves all mapping-specific rules

### Config

Top-level configuration container.

```python
@dataclass
class Config:
    """Top-level configuration.
    
    Attributes:
        projects: Dictionary mapping project names to ConfigProject.
    """
    projects: dict[str, ConfigProject]
```

---

## Processing Models

Located in `src/beyond_local_file/model/processing.py`

### ProcessingUnit

Represents one (project, mapping, target) combination for execution.

```python
@dataclass
class ProcessingUnit:
    """One project-to-target mapping for execution.
    
    A ConfigProject with M mappings and N total targets becomes M*N ProcessingUnits.
    
    Attributes:
        managed_project_name: Original project name from configuration.
        managed_project_path: Absolute path to managed project directory.
        target_project_path: Single target path for this unit.
        items: None = sync everything, list = sync specified items only.
        display_name: Computed display name with suffix for output.
        mapping_index: Which mapping this unit comes from (0-based).
        target_index: Which target within the mapping (0-based).
    """
    managed_project_name: str
    managed_project_path: Path
    target_project_path: Path
    items: list[ProjectItem] | None
    display_name: str
    mapping_index: int
    target_index: int
```

**Key Points**:
- One unit per (project, mapping, target) combination
- `items=None` means sync everything (no subpath filter)
- `items=[...]` means sync only specified items (subpath filter)
- `display_name` includes suffix for disambiguation

### ProjectItem

Represents a single file or directory to sync.

```python
@dataclass
class ProjectItem:
    """Single file or directory in the managed project.
    
    Attributes:
        name: Item name (file or directory name).
        path: Absolute path to the item.
        strategy: How to link this item (SYMLINK or COPY).
    """
    name: str
    path: Path
    strategy: LinkStrategy
```

---

## Translation Layer

Located in `src/beyond_local_file/model/translator.py`

### translate_config_to_processing()

Converts ConfigProject instances to ProcessingUnit instances.

```python
def translate_config_to_processing(
    config_projects: dict[str, ConfigProject],
) -> list[ProcessingUnit]:
    """Translate config model to processing units.
    
    For each ConfigProject:
      - Iterate through mappings (mapping_index = 0, 1, 2, ...)
      - For each mapping, iterate through targets (target_index = 0, 1, 2, ...)
      - Create one ProcessingUnit per (mapping, target) combination
      - Compute display_name based on total mappings and targets
      - Load items based on mapping's subpaths
    
    Returns:
        List of ProcessingUnit instances ready for execution.
    """
```

### Translation Process

**Step 1: Count Total Units**
```python
total_units = sum(len(mapping.targets) for mapping in config_project.mappings)
```

**Step 2: Determine Padding**
```python
needs_mapping_padding = num_mappings >= 10
needs_target_padding = any(len(mapping.targets) >= 10 for mapping in mappings)
```

**Step 3: Create Processing Units**
```python
for mapping_idx, mapping in enumerate(config_project.mappings):
    for target_idx, target_path in enumerate(mapping.targets):
        # Compute display name
        display_name = _compute_display_name(...)
        
        # Load items
        items = _load_items(
            managed_project_path=config_project.managed_project_path,
            subpaths=mapping.subpaths,
            copy_paths=mapping.copy_paths,
        )
        
        # Create unit
        unit = ProcessingUnit(
            managed_project_name=config_project.managed_project_name,
            managed_project_path=config_project.managed_project_path,
            target_project_path=target_path,
            items=items,
            display_name=display_name,
            mapping_index=mapping_idx,
            target_index=target_idx,
        )
```

---

## Display Name Logic

Display names use suffixes to distinguish processing units.

### Rules

1. **Single unit**: No suffix
   - `"project"`

2. **Multiple mappings, single target each**: Mapping index only
   - `"project#1"`, `"project#2"`, `"project#3"`

3. **Single mapping, multiple targets**: Mapping and target indices
   - `"project#1-1"`, `"project#1-2"`, `"project#1-3"`

4. **Multiple mappings with multiple targets**: Both indices
   - `"project#1"`, `"project#2-1"`, `"project#2-2"`

5. **Zero-padding**: When any index ≥ 10
   - `"project#01"`, `"project#01-01"`

### Examples

**Example 1: Single mapping, single target**
```yaml
project-a: /target1
```
Result: `"project-a"` (no suffix)

**Example 2: Multiple mappings, single target each**
```yaml
project-b:
  - /target1
  - /target2
```
Result: `"project-b#1"`, `"project-b#2"`

**Example 3: Single mapping, multiple targets**
```yaml
project-c:
  target: [/target1, /target2]
  subpath: [.kiro/hooks]
```
Result: `"project-c#1-1"`, `"project-c#1-2"`

**Example 4: Multiple mappings, some with multiple targets**
```yaml
project-d:
  - /target1
  - target: [/target2, /target3]
    subpath: [.kiro/hooks]
  - /target4
```
Result: `"project-d#1"`, `"project-d#2-1"`, `"project-d#2-2"`, `"project-d#3"`

**Example 5: Padding (10+ mappings)**
```yaml
project-e:
  - /target1
  - /target2
  # ... 8 more mappings
  - /target10
  - /target11
```
Result: `"project-e#01"`, `"project-e#02"`, ..., `"project-e#10"`, `"project-e#11"`

---

## Benefits

### 1. Separation of Concerns

**Config Layer**:
- Only handles YAML parsing
- No processing logic
- No synthetic names

**Processing Layer**:
- Only handles execution
- No YAML knowledge
- Display names for output

### 2. Grammar Compliance

Config model directly reflects the formal grammar:

```
project-name: string-mapping | dict-mapping | list-of-mappings
string-mapping: target-path
dict-mapping: {target: target-path(s), subpath?: [...]}
list-of-mappings: [string-mapping | dict-mapping, ...]
```

### 3. Clear Semantics

- **Config model** = User intent (what they configured)
- **Processing model** = Execution plan (what will run)

### 4. Better Maintainability

- Changes to display logic don't affect config loading
- Changes to config parsing don't affect execution
- Easy to understand each layer independently

### 5. Easier Testing

- Test config parsing separately from execution
- Test translation logic in isolation
- Test display name generation independently

### 6. Future Flexibility

- Easy to add new processing strategies
- Easy to change display name format
- Easy to add new config features

---

## Examples

### Example 1: Simple Configuration

**YAML**:
```yaml
my-project: /target
```

**ConfigProject**:
```python
ConfigProject(
    managed_project_name="my-project",
    managed_project_path=Path("/path/to/my-project"),
    mappings=[
        Mapping(targets=[Path("/target")], subpaths=None, copy_paths=None)
    ]
)
```

**ProcessingUnit**:
```python
ProcessingUnit(
    managed_project_name="my-project",
    managed_project_path=Path("/path/to/my-project"),
    target_project_path=Path("/target"),
    items=None,  # Sync everything
    display_name="my-project",  # No suffix
    mapping_index=0,
    target_index=0,
)
```

### Example 2: Multiple Mappings

**YAML**:
```yaml
my-project:
  - /target1
  - target: /target2
    subpath: [.kiro/hooks]
```

**ConfigProject**:
```python
ConfigProject(
    managed_project_name="my-project",
    managed_project_path=Path("/path/to/my-project"),
    mappings=[
        Mapping(targets=[Path("/target1")], subpaths=None, copy_paths=None),
        Mapping(targets=[Path("/target2")], subpaths=[".kiro/hooks"], copy_paths=None),
    ]
)
```

**ProcessingUnits**:
```python
[
    ProcessingUnit(
        managed_project_name="my-project",
        managed_project_path=Path("/path/to/my-project"),
        target_project_path=Path("/target1"),
        items=None,  # Sync everything
        display_name="my-project#1",
        mapping_index=0,
        target_index=0,
    ),
    ProcessingUnit(
        managed_project_name="my-project",
        managed_project_path=Path("/path/to/my-project"),
        target_project_path=Path("/target2"),
        items=[ProjectItem(name=".kiro/hooks", ...)],  # Sync only .kiro/hooks
        display_name="my-project#2",
        mapping_index=1,
        target_index=0,
    ),
]
```

### Example 3: Multiple Targets in Mapping

**YAML**:
```yaml
my-project:
  target: [/target1, /target2]
  subpath: [.kiro/hooks]
```

**ConfigProject**:
```python
ConfigProject(
    managed_project_name="my-project",
    managed_project_path=Path("/path/to/my-project"),
    mappings=[
        Mapping(
            targets=[Path("/target1"), Path("/target2")],
            subpaths=[".kiro/hooks"],
            copy_paths=None
        ),
    ]
)
```

**ProcessingUnits**:
```python
[
    ProcessingUnit(
        managed_project_name="my-project",
        managed_project_path=Path("/path/to/my-project"),
        target_project_path=Path("/target1"),
        items=[ProjectItem(name=".kiro/hooks", ...)],
        display_name="my-project#1-1",
        mapping_index=0,
        target_index=0,
    ),
    ProcessingUnit(
        managed_project_name="my-project",
        managed_project_path=Path("/path/to/my-project"),
        target_project_path=Path("/target2"),
        items=[ProjectItem(name=".kiro/hooks", ...)],
        display_name="my-project#1-2",
        mapping_index=0,
        target_index=1,
    ),
]
```

---

## Implementation Details

### Config Parsing

**Old Method (Deprecated)**:
```python
def get_projects(self, project_name: str | None = None) -> dict[str, ProjectConfiguration]:
    """Returns split configurations with synthetic names."""
```

**New Method**:
```python
def get_config_projects(self, project_name: str | None = None) -> dict[str, ConfigProject]:
    """Returns ConfigProject with list of mappings (no splitting)."""
```

### Processing

**Old Method (Deprecated)**:
```python
def process_all(self, operation: CmdOperation, skip_invalid: bool = True) -> bool:
    """Uses ProjectConfiguration (split at config load time)."""
```

**New Method**:
```python
@staticmethod
def process_all_units(
    config_projects: dict[str, ConfigProject],
    operation: CmdOperation,
    skip_invalid: bool = True,
) -> bool:
    """Uses ProcessingUnit (split at translation time)."""
```

### CLI Integration

**Old Flow**:
```python
config → get_projects() → dict[str, ProjectConfiguration] → process_all()
```

**New Flow**:
```python
config → get_config_projects() → dict[str, ConfigProject]
       → translate_config_to_processing() → list[ProcessingUnit]
       → process_all_units()
```

---

## Summary

The two-model architecture provides:

1. **Clear Separation**: Config layer handles YAML, processing layer handles execution
2. **Grammar Compliance**: Config model directly reflects formal grammar
3. **Clean Semantics**: Config = intent, Processing = execution plan
4. **Better Maintainability**: Changes to one layer don't affect the other
5. **Easier Testing**: Test each layer independently
6. **Future Flexibility**: Easy to extend without breaking existing code

The translation layer properly converts user intent (configuration) into execution plan (processing units), with smart display name generation for clear output.

---

## See Also

- **[design-overview.md](design-overview.md)** - Architecture overview
- **[design-divide-and-conquer.md](design-divide-and-conquer.md)** - Strategy management details
- **[configuration-reference.md](configuration-reference.md)** - Configuration format guide
- **[development.md](development.md)** - Development workflow
