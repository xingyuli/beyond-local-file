# Resolve UI is localhost HTML; resolve force-overwrites isolated replicas

`daemon status` listing replica and relative path is not enough to learn an out-of-sync fact, and a bare CLI is still a poor place to pick winners (0010). The deferred UI is a **resolve UI**: localhost HTML the daemon serves while it is ready, opened from the status shell screen, where a 3-way merge produces a confirmed fact and **resolve** writes it to the hub and every replica of that path.

## Status

accepted

## Decision

- The daemon binds a second localhost port for HTTP, for as long as it is ready. A token in the set run directory authenticates the URLs. Stdlib HTTP only. JSON IPC stays on the existing port.
- On a TTY, `daemon status` keeps the listing and the shell screen (0023). A key opens the resolve UI. Non-TTY prints the URL when isolation exists. A later desktop notification may open the same URLs; this decision does not send notifications.
- Left nav is one row per managed project + relative path, grouped by managed project name, covering out-of-sync and held copies. Out-of-sync detail is a 3-way merge: hub-now, result, replica-now with a replica switcher. A replica whose live bytes match hub-now is labeled `same as hub`. The program does not badge a source replica. Held-only rows show hold-reason clauses; held inspect and restore stay later (0009).
- At mark time the daemon stashes the hub bytes from just before the isolating apply with the out-of-sync row (not a held copy) and an **out-of-sync reason** (`stale-base` or `fan-out-mismatch`). That stash is the ancestor for hunks. It is not a pane. Hunks use the selected right replica’s stash.
- **Resolve** applies the confirmed fact: a new hub generation, then force-overwrite every replica that has the item, including out-of-sync ones, and clear out-of-sync for that path. Isolated bytes that did not enter the result are not held. Live fan-out still skips out-of-sync replicas.

## Considered Options

- Native desktop app. Rejected: too heavy; a local browser is enough.
- Merge or pick-winner on the CLI or the shell screen. Rejected: 0010 still holds for a bare CLI.
- Short-lived HTTP helper spawned by status. Rejected: status and a later notification click both need a URL that already works while the daemon is up.
- Apply then fan-out as live observe does (skip out-of-sync replicas). Rejected: the confirmed fact would not land on the isolated trees.
- Hold isolated replica bytes on resolve. Rejected: the merge already chose the fact; leftover isolated bytes are discarded.

## Consequences

0010’s isolation rules (CAS, skip out-of-sync on fan-out, loser’s bytes stay until resolve) still hold. Its “no resolve shell / later desktop UI” does not. 0009’s held restore/discard is still later; held copies only appear in the resolve UI’s nav. 0023 gains a status-screen key. Baseline grows reason, clause, and ancestor bytes. `docs/cli-reference.md` moves with the code that makes this true.
