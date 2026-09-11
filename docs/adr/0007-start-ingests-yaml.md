# Start ingests YAML in the foreground when the snapshot differs

`blf daemon start` compares `config.yml` to the persisted mapping snapshot. If they match (or there is no snapshot: first start / fresh catch-up), it catch-up's and backgrounds with no TTY. If they differ, start stays foreground and runs the same classifier as `reload`:

- Removals in order **project-remove → target-remove → item-remove**, dropping diffs already implied by a coarser removal.
- One printed plan, one yes/no.
- Adds (project / target / item) apply automatically after committed removals.
- Then filesystem catch-up against the **new** snapshot, then background.

No means abort: the daemon does not run, snapshot and files are unchanged. Non-interactive start with removals in the diff fails the same way. Silent start never deletes target copies.

This was chosen over always-background start (YAML-removed targets would keep being synced until a later reload) and over applying removals without a TTY.

## Status

accepted
