# Mailbox coalesce; delete wins inside a generation window

Live path changes are coalesced in a **mailbox** keyed by `(path, replica)`: at most one pending change besides an in-flight hub apply. Update+update keeps the latest bytes; update+delete becomes delete; delete+create becomes create. In-flight applies are not mutated. This is queue replacement, not a time debounce. Cross-replica pending updates are not coalesced: that would be last-write-wins and would break stale-base conflict for edits.

The hub carries a per-path **generation**, incremented once per successful apply. Matching-base delete propagates (hub, then other targets). If the hub has moved, delete still wins on the live path when `hub_gen - base_gen ≤ 3`. If the gap is larger, the current hub bytes are first stored as a **held copy** under `.blf-held/` (reserved, never projected), then the live path is deleted and absence is fanned out. The file is never unlinked without a copy. Create and update stay exact-hash CAS (frozen path on stale-base, not held). Generation does not increment while the daemon is down; catch-up sees current hash vs baseline, so downtime delete is typically gap 0–1 and still wins without holding.

## Status

accepted

## Considered Options

- Time-window debounce (e.g. 1s). Rejected as the coalesce mechanism: it adds a clock and does not cap generation if saves are spaced out.
- Coalesce by path only. Rejected: two replicas' updates would collapse to arrival order.
- Unlimited delete-wins with no generation cap. Rejected: a live replica many applies behind (failed fan-out) would still wipe a long hub history. The cap is that rail; catch-up does not need it.
