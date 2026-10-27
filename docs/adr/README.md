# ADRs

One line per decision. Read the file when the title matches the work.

- [0001](0001-copy-only-projections.md) — Copy-only projections
- [0002](0002-live-daemon.md) — Live daemon, hub-and-fan-out, stale-base conflict
- [0003](0003-catch-up-and-reload.md) — Fresh catch-up, update catch-up, explicit reload
- [0004](0004-per-path-change-grain.md) — Per-path change grain under a directory item
- [0005](0005-daemon-is-the-runtime.md) — Daemon is the sole runtime and sole internal mapping writer
- [0006](0006-shells-and-operations.md) — Shells require the daemon; three stop-syncing operations
- [0007](0007-start-ingests-yaml.md) — Start ingests YAML in the foreground when the snapshot differs
- [0008](0008-mailbox-and-delete-window.md) — Mailbox coalesce; delete wins inside a generation window
- [0009](0009-held-copies.md) — Held copies for out-of-window deletes; no 0.5.0 restore command
- [0010](0010-out-of-sync-replica.md) — Out-of-sync replica on a lost update CAS
- [0011](0011-create-fan-out-and-hold-reason.md) — revlink create fans out; collisions hold with a reason
- [0012](0012-no-overlapping-item-paths.md) — No overlapping item paths on one target
- [0013](0013-preserve-nested-symlinks-on-copy.md) — Preserve nested symlink nodes on copy
- [0014](0014-runtime-contribution-source.md) — Runtime contribution source
- [0015](0015-daemon-log-timestamps.md) — Daemon log timestamps at write time
- [0016](0016-revlink-contribution-choice.md) — Revlink chooses a hub by path owner or a shell interview
- [0017](0017-configuration-set.md) — One daemon process per configuration set
- [0018](0018-runtime-home.md) — Runtime home is `~/.blf`; mapping hubs stay clean
- [0019](0019-serve-during-catch-up.md) — IPC is up during catch-up; progress is one TTY status line
- [0020](0020-daemon-request-observability.md) — Daemon log records shell requests, op steps, and set-wide work
- [0021](0021-worker-unit-pool.md) — Accept thread never hashes; one job per worker unit
- [0022](0022-three-daemon-logs.md) — Three logs, millisecond stamps, and `blf logs`
- [0023](0023-shell-screen.md) — Shell screen
- [0024](0024-resolve-ui.md) — Resolve UI is localhost HTML; resolve overwrites isolated replicas
- [0025](0025-sequential-two-way-replica-merge.md) — Sequential two-way replica merge, driven client-side
- [0026](0026-desktop-notice.md) — Desktop notice is display-only; status opens the resolve UI
- [0027](0027-restore-undoes-fan-out.md) — Restore undoes create's fan-out
- [0028](0028-install-holds-colliding-replica-bytes.md) — Install holds colliding replica bytes
- [0029](0029-one-apply-hash-grain.md) — One apply hash grain; no MD5 verify
- [0030](0030-one-apply-two-wrappers.md) — One apply; idle tick and shell request are wrappers
- [0031](0031-directory-path-does-not-carry-children.md) — A directory path change does not carry its children
- [0032](0032-symlink-path-change.md) — A symlink path change is its own kind
- [0033](0033-bounded-log-follow.md) — Log follow shows recent work, and each log stays bounded
- [0034](0034-stat-first-idle-observe.md) — Idle observe reuses the last hash when a file's stat signature is unchanged
- [0035](0035-forced-remove-clears-unmatched-copies.md) — Forced remove clears an unmatched declared item
- [0036](0036-target-add-catch-up-follows-idle-tick.md) — Target-add catch-up follows the idle tick
