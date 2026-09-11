# Held copies for out-of-window deletes; no 0.5.0 restore command

When a delete's generation gap is greater than 3, the daemon does not freeze the live path and does not drop the hub bytes. It moves them to `.blf-held/` in the managed project, then delete-wins on the live tree (hub path gone, fan-out absence). `.blf-held/` is reserved: skipped by item discovery, observers, and catch-up, including sync-all mappings.

`daemon status` lists held copies. `daemon start` and `daemon reload` print a warning and require ack; they do not require the user to restore or discard before the daemon runs. 0.5.0 has no held restore/discard shell: the status path is enough to copy by hand. Interactive resolve is deferred to a desktop UI.

Update stale-base does not use `.blf-held/`. The losing replica is marked out-of-sync (0010).

## Status

accepted
