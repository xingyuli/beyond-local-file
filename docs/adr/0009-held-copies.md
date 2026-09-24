# Held copies for out-of-window deletes; no 0.5.0 restore command

Held copies live under ``~/.blf/held/<sha256 of the managed project path>/`` (0018) and always carry a hold reason. A leftover ``.blf-held/`` in the managed project is still skipped by discovery, observers, and catch-up (including sync-all); new holds are not written there. Delete past generation gap 3 uses `delete-gap` (hub bytes held, then live path delete-wins). `revlink create` fan-out uses `create-overwrite` when a replica had different bytes (replica bytes held, then hub overwrites).

`daemon status` lists held copies. `daemon start` and `daemon reload` print a warning and require ack; they do not require the user to restore or discard before the daemon runs. There is no held restore/discard shell: the status path is enough to copy by hand. Held copies appear in the resolve UI nav (0024); inspect and restore of held bytes stay later.

Update stale-base does not use held copies. The losing replica is marked out-of-sync (0010).

## Status

accepted
