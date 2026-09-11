# Held copies for out-of-window deletes; no 0.5.0 restore command

Held copies live in `.blf-held/` in the managed project and always carry a hold reason. Delete past generation gap 3 uses `delete-gap` (hub bytes held, then live path delete-wins). `revlink create` fan-out uses `create-overwrite` when a replica had different bytes (replica bytes held, then hub overwrites). `.blf-held/` is reserved: skipped by item discovery, observers, and catch-up, including sync-all mappings.

`daemon status` lists held copies. `daemon start` and `daemon reload` print a warning and require ack; they do not require the user to restore or discard before the daemon runs. 0.5.0 has no held restore/discard shell: the status path is enough to copy by hand. Interactive resolve is deferred to a desktop UI.

Update stale-base does not use `.blf-held/`. The losing replica is marked out-of-sync (0010).

## Status

accepted
