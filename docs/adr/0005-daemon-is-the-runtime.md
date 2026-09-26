# Daemon is the sole runtime and sole internal mapping writer

Copy, catch-up, fan-out, resolve, and every mapping edit that originates from blf run inside the daemon. `revlink create`, `revlink restore`, and `remove` are shells: they send a request and do not themselves copy, delete, or write `config.yml`. The resolve UI is not a second writer: Submit enqueues on the worker unit. That makes the daemon the single point that maintains blf-caused config changes.

The mapping snapshot is persisted on disk. After a crash or kill, start can still diff the config file against the last committed snapshot and see external mapping edits. A snapshot that lived only in memory could not.

Manual edits of the config file remain an external source and still take effect only through reload (or the equivalent classify-on-start against the persisted snapshot). The daemon does not watch mapping files.

## Status

accepted

## Considered Options

- Shells do the work and notify a running daemon. Rejected: two writers of mappings and of projections; a missed notify lets live observation undo `remove`.
- Shells work fully offline and only talk to the daemon when it happens to be up. Rejected: the daemon is the runtime, not an optional accelerator.
- In-memory snapshot only. Rejected: after a kill, the daemon cannot tell what changed in the config file since it last ran.
