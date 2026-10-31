# Live sync edge cases

This page is the reference for every edge case the live daemon reports, and the reason it gives. For the overview, see [Live updates, out-of-sync, and held copies](../README.md#live-updates-out-of-sync-and-held-copies) in the README. Terms follow the [glossary](../GLOSSARY.md).

An edge case ends in one of two ways, and each way has a fixed set of reasons:

| Outcome | Meaning | Reasons |
|---------|---------|---------|
| **Held copy** | The live path moved on. The bytes it replaced are kept under `~/.blf/held/`. | `create-overwrite`, `delete-overwrite`, `delete-gap`, `kind-change` |
| **Out-of-sync** | One replica is excluded from one path. The hub and the other replicas keep moving. | `stale-base`, `fan-out-mismatch` |

`blf daemon status` lists both. `reload` warns about both.

Examples use `lab-app` as the managed project (the hub), and `alpha` and `beta` as two replicas of it.

## Hold reasons

### `create-overwrite`

The daemon installed the hub's file on a replica that already had different bytes there. The replica's old bytes are held.

Example: `alpha` adopts `config.toml` as a new item. `beta` already has a different `config.toml`. The daemon copies `alpha`'s file to the hub and to `beta`, and holds `beta`'s old file. The same happens when you map a new target that has different bytes for a path the hub has.

### `delete-overwrite`

You mapped a new target that has bytes for an item the hub does not have. If those bytes differ from what the hub last recorded for that item, they are held and the projection is removed. If they still match, they are removed with no hold.

Example: the hub has no `old.txt`, but the new target for `beta` does, and its content was never what the hub recorded. `old.txt` is held and removed from `beta`.

### `delete-gap`

A replica deleted a file or symlink, but the hub had since changed it and the hub is more than 3 generations ahead of the replica's base. The delete still applies. The hub's current bytes (or the link text) are held first.

A file or symlink has a generation that counts live applies of that path. A delete with no hub change since the replica's base never needs the window. A directory has no generation, counts as 0, and never uses the window.

Example: the hub has `a.md` at generation 9, and `alpha` last saw it at generation 5. `alpha` deletes `a.md`. The gap is 4, so the hub's `a.md` is held and then removed everywhere.

### `kind-change`

A file became a directory, or a directory became a file. The previous file bytes are held, the new node is written, and no replica is marked out of sync.

Example: `alpha` replaces the directory `docs/` with a file `docs`. Every file under the old `docs/` (such as `docs/a.md`) is held. `beta` still has the directory, so fan-out holds `beta`'s files too and writes the file. Neither replica is marked out of sync.

## Out-of-sync reasons

Each mark names the replica and the path. For a file or symlink it also names the hub generation.

### `stale-base`

An update from a replica lost to a different writer: another replica, or a direct edit on the managed project that changed the hub after the replica's base.

Example: `alpha` and `beta` both change `a.md` before the daemon applies either. `alpha` wins. `beta` is out of sync for `a.md`.

### `fan-out-mismatch`

Fan-out skipped a replica because its disk was not the expected base. Two cases:

- The replica's path changed after the tick's snapshot, so it no longer matches what the hub had.
- A directory delete reached a replica whose directory still holds children, so it could not be removed.

Example: `alpha` deletes the directory `docs/`. `beta` still has `docs/extra.md` that only it has. Fan-out cannot remove `docs/` on `beta`, so `beta` is marked.

### What an out-of-sync mark does

- Fan-out of that path skips the replica, and its further changes to that path are discarded.
- The mark clears when the replica's bytes match the hub again, when **resolve** overwrites the path, or when that target's baseline rows are dropped.
- The mark records the node the replica still has, so a mark can sit on a directory, a file, or a symlink.
