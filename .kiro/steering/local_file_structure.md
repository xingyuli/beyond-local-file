---
inclusion: always
---

# local-file Directory Convention

This file defines the storage and organization conventions for the `local-file/` directory.

## Directory Structure

```
local-file/
├── agentic/              # Kiro-generated content
│   ├── analysis/        # Technical analysis reports
│   ├── drafts/          # Informal plans, drafts, proposals
│   ├── specs/           # Formal specification files
│   └── summaries/       # Task completion summaries
└── tasks/               # Task tracking system
    ├── index.md         # Main hub linking to all task groups
    ├── manual/          # User-created tasks
    ├── auto-review/     # Auto-generated review findings
    └── releases/        # Archived completed tasks by release
```

---

## Agentic Directory (`local-file/agentic/`)

Kiro-generated content organized by purpose.

### analysis/

**Purpose:** Technical analysis reports generated at the start of or during a chat conversation.

**When to write:** When analyzing codebase structure, investigating issues, or exploring technical approaches before implementation.

**Examples:**
- Codebase structure analysis
- Performance bottleneck investigation
- Dependency analysis
- Architecture exploration

**Naming:** Descriptive names that clearly indicate the analysis topic (e.g., `codebase-structure-for-copy-feature.md`)

### drafts/

**Purpose:** Informal implementation plans, design proposals, or when explicitly asked to draft something.

**When to write:**
- Creating informal design proposals
- Drafting API specifications
- Sketching implementation approaches
- When user explicitly asks to "draft" something

**Examples:**
- Design proposals
- OpenAPI spec drafts
- Implementation approach sketches
- Architecture alternatives

**Naming:** Descriptive names indicating the draft content (e.g., `single-file-copy-proposal.md`)

### specs/

**Purpose:** Formal specification files that define formats, conventions, and standards.

**When to write:** When creating formal specifications for:
- File formats
- API specifications
- Configuration formats
- Task definitions
- Coding conventions

**Examples:**
- `task-definition-spec.md`
- `config-format-spec.md`
- `api-specification.md`

**Naming:** Use `-spec.md` suffix for specification files

### summaries/

**Purpose:** Task completion summaries documenting changes made during a task or conversation.

**When to write:** When a task has been completed and you want to summarize the changes made.

**Format:** Prefix with `YYYYMMDD-HH` (date and hour) so files can be read in chronological order.

**Examples:**
- `20260403-14-task-system-improvements.md`
- `20260327-09-copy-feature-implementation.md`
- `20260320-16-subpath-support-added.md`

**Naming:** `YYYYMMDD-HH-descriptive-title.md`

---

## Task Tracking System (`local-file/tasks/`)

All project tasks are tracked under `local-file/tasks/` with task groups, indices, and individual task files.

### Structure

```
local-file/tasks/
├── index.md              # Main hub linking to all task groups
├── manual/               # User-created tasks
│   ├── index.md         # Manual tasks index
│   ├── README.md        # Documentation
│   └── *.md             # Individual task files
├── auto-review/          # Auto-generated review findings
│   ├── index.md         # Auto-review tasks index
│   ├── simple_advices.md # One-sentence findings (running log)
│   ├── README.md        # Documentation
│   └── *.md             # Detailed auto-review task files
└── releases/             # Archived completed tasks by release
    ├── README.md        # Documentation
    └── v0.x.x/          # Example: tasks completed in v0.2.0
        ├── CHANGELOG.md # Formal changelog for this release
        └── *.md         # Archived completed task files
```

### Task Groups

#### Manual Tasks (`local-file/tasks/manual/`)
User-created tasks for features, bugs, usability improvements, and documentation.

#### Auto-Review Tasks (`local-file/tasks/auto-review/`)
Automatically generated code review findings:
- `simple_advices.md` — One-sentence findings (🟡 Should Fix / 🔵 Consider), grouped by date
- Detailed task files — Complex findings requiring more context, impact analysis, or multiple solutions

### Task Lifecycle

#### 1. Creating a Manual Task
- Create a markdown file in `local-file/tasks/manual/{verb}-{slug}.md`
- Start with header: Title, Category, Status, Description
- Add core sections: Motivation, Current Behavior, Expected Behavior, Proposed Solution
- Add optional sections as needed (keep implementation details minimal)
- Add a checkbox entry in `local-file/tasks/manual/index.md` under the appropriate category

#### 2. Creating an Auto-Review Finding
For simple one-sentence findings:
- Append to `local-file/tasks/auto-review/simple_advices.md`
- Group by date, use 🟡 or 🔵 prefix

For complex findings:
- Create a detailed task file in `local-file/tasks/auto-review/`
- Add to `auto-review/index.md`

#### 3. Working on a Task
- Update the Status field in the task file header as work progresses
- Commit changes with descriptive messages

#### 4. Completing a Task
- Update Status to "Completed" in the task file header
- Mark checkbox with `[x]` in the appropriate index
- Add completion date: `— Completed: YYYY-MM-DD` (infer from git commit date if possible)
- Commit the completion

#### 5. Preparing a Release (Use Hook)
When ready to release, trigger the "Prepare Release" hook which will:
- Gather all completed manual tasks since last git tag
- Generate formal CHANGELOG.md entries
- Archive completed tasks to `local-file/tasks/releases/[version]/`
- Update manual task index to remove completed tasks
- Create a clean slate for the next development cycle
- Note: Simple advices are NOT archived — they remain as a running log

### Categories

- Features — New functionality
- Bugs — Known issues to fix
- Usability — CLI UX and output improvements
- Documentation — Docs and README updates
- Code Quality — Refactoring and technical debt

### Conventions

#### Task File Format
- Header first: Title, Category, Status, Description at the top
- Core sections: Motivation, Current Behavior, Expected Behavior, Proposed Solution
- Keep implementation details minimal — they become stale quickly
- Focus on "why" and "what", not detailed "how"

#### Naming
- Use format: `{verb}-{slug}.md` (e.g., `add-dry-run-mode.md`, `fix-path-resolution.md`)
- Link tasks from the appropriate group index

#### Auto-Review
- Simple one-sentence findings go in `simple_advices.md`
- Complex findings requiring detailed analysis get their own task files
- Simple advices are NOT archived — they remain as a continuous running log

#### Completion
- Infer completion dates from git commit history when possible
- Completed manual tasks remain in their group until the next release preparation
- Completed auto-review detailed tasks CAN be archived

---

## Notes

- All Kiro-generated content must be placed in the appropriate subdirectories
- Do not scatter files in the `local-file/` root directory
- Use descriptive filenames that clearly indicate content
- Follow naming conventions for consistency
