# Domain Docs

This repo uses a **single-context** layout.

## Files

| File | Purpose |
|------|---------|
| `CONTEXT.md` | Primary domain context — project overview, key concepts, ubiquitous language, architecture decisions |
| `docs/adr/` | Architecture Decision Records (ADRs) — significant technical decisions with context and rationale |
| `docs/design-daemon.html` | High-level daemon design as flowcharts (process, lifecycle, live path, mappings, resolve) |

## Reading rules for agents

1. **Always read `CONTEXT.md`** before making architectural or domain-level changes. It is the ground truth for domain terminology and design intent.
2. **Read `docs/design-daemon.html`** when the work is the daemon as a whole (process shape, live path, start/reload, resolve UI).
3. **Read relevant ADRs** in `docs/adr/` when a change touches an area covered by an existing decision.
4. **Write a new ADR** in `docs/adr/` when making a significant architectural decision that future contributors (human or agent) would benefit from understanding.

## ADR format

ADR files live in `docs/adr/` named `NNNN-short-title.md` (e.g., `0001-use-symlinks-for-sync.md`).

Each ADR contains: Title, Status, Context, Decision, Consequences.

## Notes

- `CONTEXT.md` does not exist yet — create it when the domain model is first formalized.
- `docs/adr/` does not exist yet — create it when the first architectural decision needs recording.
