---
inclusion: always
---

# local-file Directory Convention

This file defines the storage and organization conventions for the `local-file/` directory.

## Directory Structure

```
local-file/
├── agentic/              # Kiro-generated content
│   ├── analysis/        # Technical analysis reports (timestamped, flat)
│   ├── drafts/          # Informal plans, drafts, proposals (timestamped, flat)
│   ├── specs/           # Formal specification files (no timestamps, flat)
│   └── summaries/       # Task completion summaries (timestamped, flat)
├── initiatives/          # Strategic work items (not in changelog/release cycle)
│   ├── README.md        # Documentation
│   └── *.md             # Initiative files (e.g., share-and-impact.md)
└── tasks/               # Task tracking system
    ├── index.md         # Main hub linking to all task groups
    ├── manual/          # User-created tasks
    ├── auto-review/     # Auto-generated review findings
    └── releases/        # Archived completed tasks by release
        └── v0.x.x/      # Example release
            ├── CHANGELOG.md
            ├── tasks/   # Archived tasks
            │   ├── manual/
            │   └── auto-review/
            └── worklog/ # Archived agentic files
                ├── analysis/
                ├── drafts/
                └── summaries/
```

---

## Agentic Directory (`local-file/agentic/`)

Kiro-generated content organized by purpose. All files in `analysis/`, `drafts/`, and `summaries/` use `YYYYMMDD-HH-` prefix for chronological ordering (GMT+8 timezone).

### analysis/

**Purpose:** Technical analysis reports generated at the start of or during a chat conversation.

**When to write:** When analyzing codebase structure, investigating issues, or exploring technical approaches before implementation.

**Examples:**
- Codebase structure analysis
- Performance bottleneck investigation
- Dependency analysis
- Architecture exploration

**Naming:** `YYYYMMDD-HH-descriptive-title.md` using GMT+8 timezone (e.g., `20260326-18-codebase-structure-for-copy-feature.md`)

**Structure:** Flat directory - no subdirectories

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

**Naming:** `YYYYMMDD-HH-descriptive-title.md` using GMT+8 timezone (e.g., `20260326-18-single-file-copy-proposal.md`)

**Structure:** Flat directory - no subdirectories

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

**Naming:** Use `-spec.md` suffix for specification files (no timestamp prefix - specs are timeless)

**Structure:** Flat directory - no subdirectories

### summaries/

**Purpose:** Task completion summaries documenting changes made during a task or conversation.

**When to write:** When a task has been completed and you want to summarize the changes made.

**Examples:**
- `20260403-14-task-system-improvements.md`
- `20260327-09-copy-feature-implementation.md`
- `20260320-16-subpath-support-added.md`

**Naming:** `YYYYMMDD-HH-descriptive-title.md` using GMT+8 timezone

**Structure:** Flat directory - no subdirectories

---

## Initiatives Directory (`local-file/initiatives/`)

Strategic work items and coordinated efforts that don't directly belong in the changelog or release cycle.

**For complete initiative format specification, see:** `local-file/agentic/specs/initiative-definition-spec.md`

This section provides a quick reference. The formal spec contains detailed guidelines on initiative structure, action item tracking, naming conventions, workflow, and best practices.

**Purpose:** Track promotional activities, infrastructure setup, meta-project work, and multi-step initiatives.

**What goes here:**
- Promotional activities (PyPI publishing, community sharing)
- Infrastructure setup (CI/CD, GitHub Actions)
- Meta-project work (documentation overhauls, branding)
- Multi-step initiatives spanning multiple actions

**What doesn't go here:**
- Feature development → `local-file/tasks/manual/`
- Bug fixes → `local-file/tasks/manual/`
- Code quality improvements → `local-file/tasks/manual/`
- Auto-review findings → `local-file/tasks/auto-review/`

### Initiative File Format

Each initiative file follows this structure:

**Header (Required):**
```markdown
# Initiative Title

**Goal:** One-sentence description of what this initiative aims to achieve.
**Status:** Planning | In Progress | Completed | On Hold
**Created:** YYYY-MM-DD
**Completed:** YYYY-MM-DD (only if status is Completed)
```

**Overview Section (Required):**
Brief description of the initiative, its purpose, and expected impact.

**Action Items Table (Required):**
```markdown
| # | Action | Status | Related Task/Resource | Notes |
|---|--------|--------|----------------------|-------|
| 1 | [Action description] | Not Started | [Link to task](../tasks/manual/task.md) | Optional context |
| 2 | [Action description] | In Progress | [External link](https://...) | Optional context |
| 3 | [Action description] | Completed | — | Completed YYYY-MM-DD |
```

The Action Items table is the centerpiece - it provides at-a-glance status tracking with:
- Sequential numbering for easy reference
- Clear action descriptions
- Status tracking (Not Started, In Progress, Completed, Blocked, Skipped)
- Links to related tasks or external resources
- Optional notes for context, completion dates, or blockers

**Detailed Sections (Optional):**
For complex actions requiring more explanation, add detailed sections after the Action Items table with prerequisites, steps, resources, and notes.

**Success Criteria (Recommended):**
Define measurable outcomes and specific deliverables that indicate initiative completion.

### Linking Between Initiatives and Tasks

**From Initiative to Task:**
```markdown
| 2 | Add --version option | Not Started | [Task](../tasks/manual/add-version-option.md) | Required before PyPI |
```

**From Task to Initiative:**
```markdown
**Part of Initiative:** [Share & Prove Impact](../../initiatives/share-and-impact.md)
```

This creates bidirectional links showing how strategic goals connect to concrete work.

### Naming Conventions

- Use descriptive, goal-oriented names in kebab-case
- Avoid dates in filenames (initiatives are timeless)
- Examples: `share-and-impact.md`, `ci-cd-automation.md`, `documentation-overhaul.md`

**Structure:** Flat directory with markdown files describing goals, action items with status tracking, and context.

**Examples:**
- `share-and-impact.md` — Promoting the project through PyPI, README improvements, community engagement

---

## Task Tracking System (`local-file/tasks/`)

All project tasks are tracked under `local-file/tasks/` with task groups, indices, and individual task files.

**For complete task format specification, see:** `local-file/agentic/specs/task-definition-spec.md`

This section provides a quick reference. The formal spec contains detailed guidelines on task structure, naming conventions, workflow, and best practices.

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
        ├── tasks/       # Archived completed tasks
        │   ├── manual/  # Archived manual tasks
        │   └── auto-review/ # Archived auto-review tasks
        └── worklog/     # Archived agentic worklog files
            ├── analysis/   # Archived analysis files
            ├── drafts/     # Archived draft files
            └── summaries/  # Archived summary files
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
- Archive completed tasks to `local-file/tasks/releases/[version]/tasks/manual/` and `tasks/auto-review/`
- Archive agentic worklog files to `local-file/tasks/releases/[version]/worklog/analysis/`, `worklog/drafts/`, and `worklog/summaries/`
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
