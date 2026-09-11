# Live daemon, hub-and-fan-out, stale-base conflict

Copy-only projections cannot share inodes, so a long-running daemon observes each managed project and its target projects, queues changes, writes the managed project as hub, then fans that generation out to in-sync replicas except the source replica. `link sync` is dropped; `link check` stays. The process is named **daemon** in the CLI and the glossary; "coordinator" is not used.

A change carries the content hash and generation it observed. A target **update** is legal only if that base still matches the hub. The first successful apply wins; the losing replica is marked **out-of-sync** for that path (see 0010). Deletes use the generation window and held copies, not this isolation.

Two-tier processing (hub worker, then fan-out) is a durability/latency split, not a correctness mechanism. The race exists with one worker too.

## Status

accepted

## Considered Options

- Scan snapshot inside `link sync`, no daemon. Rejected: once observation is live, a manual sync command has no job.
- Live daemon with last-write-wins at the hub. Rejected: stale-base writes drop the other version from the hub.
- Live daemon with stale-base freeze of the whole path. Superseded by 0010 (isolate the losing replica, keep the hub moving).
