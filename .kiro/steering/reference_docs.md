---
inclusion: fileMatch
fileMatchPattern: 'docs/(cli-reference|configuration-reference).md'
---

# Reference Documentation Guidelines

This steering file defines the purpose, scope, and maintenance guidelines for the two definitive reference documents: `docs/cli-reference.md` and `docs/configuration-reference.md`.

## Purpose

These are **definitive reference documents** that serve as the single source of truth for:
- `cli-reference.md` — Command-line interface behavior and options
- `configuration-reference.md` — Configuration file format and features

They are NOT tutorials, guides, or conceptual explanations. They are exhaustive, precise, and authoritative references.

---

## CLI Reference (`docs/cli-reference.md`)

### What to Include

**Command Structure:**
- Global options (attached to the main CLI group)
- Commands and subcommands
- Command-specific options
- Arguments (required/optional)

**Command Behavior:**
- What the command does
- When it prompts for user input
- How it handles different scenarios
- Side effects (e.g., Git exclude file updates)

**Output:**
- Output format examples
- Status indicators and their meanings
- Exit codes

**Usage Examples:**
- Common command invocations
- Option combinations
- Workflow examples (initial setup, daily usage, troubleshooting)

**Environment:**
- Working directory requirements
- Config file location and override
- Integration with external tools (e.g., Git)

### What NOT to Include

**Configuration Details:**
- Configuration file format (belongs in `configuration-reference.md`)
- Configuration syntax and grammar
- Configuration features and rules
- Only reference the configuration reference doc

**Implementation Details:**
- Internal code structure
- How the tool is implemented
- Technical architecture

**Conceptual Explanations:**
- Why symlinks vs copies (brief mention is OK, but not deep explanation)
- Design philosophy
- Architectural concepts

**Installation and Setup:**
- How to install the tool
- System requirements
- These belong in README.md

### Maintenance Rules

1. **Verify Against Implementation:**
   - Always check `src/beyond_local_file/cli.py` for actual CLI structure
   - Verify option placement (global vs command-specific)
   - Confirm default values and option types

2. **Keep Examples Accurate:**
   - Test examples before documenting
   - Show correct option placement (global options before commands)
   - Use realistic paths and project names

3. **Document All Options:**
   - Every option must be documented
   - Include type, default value, and description
   - Show examples of each option in use

4. **Update When CLI Changes:**
   - New commands or options → add to reference
   - Changed behavior → update behavior section
   - Removed features → remove from reference

---

## Configuration Reference (`docs/configuration-reference.md`)

### What to Include

**Configuration Structure:**
- YAML structure and hierarchy
- Mapping types (string vs dict)
- Single vs list of mappings

**Formal Grammar:**
- BNF-style grammar specification
- Production rules with examples
- Complete syntax coverage

**Features:**
- Subpath mapping (selective sync)
- Copy strategy (physical copies)
- Multiple targets
- All configuration capabilities

**Configuration Rules:**
- Path requirements (absolute vs relative)
- Naming conventions
- Type constraints
- Validation rules

**Examples:**
- Basic usage examples
- Feature-specific examples
- Complex mixed configurations
- Real-world scenarios

**Advanced Topics:**
- Copy strategy conflict resolution
- Bidirectional sync behavior
- Edge cases and limitations

### What NOT to Include

**CLI Commands:**
- How to run commands (belongs in `cli-reference.md`)
- Command options and arguments
- Command output and behavior
- Only reference the CLI reference doc

**Implementation Details:**
- How configuration is parsed
- Internal data structures
- Code architecture

**Conceptual Explanations:**
- Why this configuration format was chosen
- Design philosophy
- Architectural decisions

**Installation and Setup:**
- Where to place config files (brief mention is OK)
- How to create initial config
- These belong in README.md

### Maintenance Rules

1. **Verify Against Implementation:**
   - Check `src/beyond_local_file/config.py` and `models.py` for actual config structure
   - Verify supported features and constraints
   - Confirm validation rules

2. **Keep Grammar Accurate:**
   - Grammar must match actual parser behavior
   - Every production rule needs an example
   - Test examples against actual tool

3. **Document All Features:**
   - Every configuration feature must be documented
   - Include syntax, behavior, and examples
   - Document limitations and constraints

4. **Update When Config Changes:**
   - New features → add to grammar and examples
   - Changed syntax → update grammar and all affected examples
   - Removed features → remove from reference

---

## Cross-Reference Guidelines

### When to Reference Each Other

**CLI Reference → Configuration Reference:**
- "See Configuration Reference for complete format documentation"
- Link to specific sections when mentioning config features
- Don't duplicate configuration syntax

**Configuration Reference → CLI Reference:**
- "See CLI Reference for command usage"
- Link when mentioning command behavior
- Don't duplicate command syntax

### When to Reference Other Docs

**README.md:**
- For getting started guides
- For installation instructions
- For high-level overview

**config-format-clarification.md:**
- For conceptual explanations
- For format vs architecture concepts
- For design philosophy

**platform-support.md / windows-support.md:**
- For platform-specific behavior
- For compatibility information

---

## Writing Style

### Be Precise and Exhaustive

- Document every option, feature, and behavior
- Use tables for structured information
- Include all possible values and their meanings

### Use Consistent Terminology

- "managed project" not "source project"
- "target location" not "destination"
- "subpath" not "sub-path" or "sub path"
- "copy strategy" not "copy mode" or "physical copy mode"

### Show, Don't Tell

- Provide concrete examples for every feature
- Use realistic paths and project names
- Show actual command output

### Keep It Factual

- State what the tool does, not why
- Avoid opinions and recommendations (except in "Best Practices" sections)
- Focus on behavior, not implementation

---

## Validation Checklist

Before committing changes to reference docs, verify:

- [ ] All options/features are documented
- [ ] Examples are tested and accurate
- [ ] Grammar matches implementation
- [ ] Cross-references are correct
- [ ] No duplicate content between the two docs
- [ ] Terminology is consistent
- [ ] Tables are properly formatted
- [ ] Code blocks have correct syntax highlighting

---

## When to Update

**Always update reference docs when:**
- Adding new CLI options or commands
- Adding new configuration features
- Changing existing behavior
- Fixing bugs that affect documented behavior
- Deprecating or removing features

**Update immediately, not later:**
- Reference docs must stay in sync with implementation
- Outdated docs are worse than no docs
- Include doc updates in the same commit as code changes
