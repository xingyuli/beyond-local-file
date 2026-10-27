# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

This repo uses a **single-context** layout.

## Before exploring, read these

- **`GLOSSARY.md`** at the repo root.
- **`docs/adr/README.md`**: read each ADR whose title matches the area.
- **`docs/design-daemon.html`** when the work is the daemon as a whole (process shape, live path, start/reload, resolve UI).

Catch-up, reload, or start: read ADR 0010, 0028, 0030, 0031, and 0036. Reload catch-up runs in `daemon/runtime.py` `_catch_up_unit`. Start catch-up loads the baseline `daemon/ingest.py` `prune_removed_replicas` already saved, then `run_catch_up`.

If `GLOSSARY.md` or `docs/adr/` is absent, proceed silently. The `/domain-modeling` skill creates them lazily when a term or decision is actually resolved.

## File structure

```
/
├── GLOSSARY.md
├── docs/adr/
└── src/
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `GLOSSARY.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding.
