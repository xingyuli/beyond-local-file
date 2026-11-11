# Resolve UI discards a held copy and shows a read-only diff

A held copy is one of the two live-sync edge outcomes (the other is out-of-sync). The resolve UI listed the hold-reason clause and could not show the bytes or remove the slot. 0009, 0024, and 0028 left inspect and restore for later, and left no discard. That is rejected for inspect and for deletion. The resolve UI discards one held copy and shows a read-only diff of a file that differs from the projection. Restore stays later. There is still no discard shell.

**Discard** deletes that one slot. The projection stays. An out-of-sync mark on the same path stays, and Submit on that path is still **resolve**. Every hold reason uses the same control (`create-overwrite`, `delete-overwrite`, `delete-gap`, `kind-change`). An empty held directory stays listed until Discard. The nav stays one row per managed project and item. Each slot on that row has its own Discard. Discard asks with the existing dialog first: title "Discard this held copy?", body the hold-reason clause, Cancel leaves the slot, Discard deletes it. The page then stays when that row still has a held copy or an out-of-sync mark. Otherwise it opens the next row, or shows none.

The held row lists that slot's files, path and size. A file that matches the projection does not open. One differing file opens at a time. The panes are titled `target-now` and `held-copy`, with the relative path above them. Both panes are read-only. A binary file shows hash and size. A symlink shows the two link texts. A missing projection leaves `target-now` empty. Files that exist only on the live tree are not listed. This diff does not produce a confirmed fact. It is not sequential replica merge (0025): no chunk accept, no mark as merged, no middle result.

The request log names both resolve-UI writes with `live: resolve`. Submit's line becomes `live: resolve out-of-sync {path} gen {n}`, and `baseline: write` still follows it, because the baseline changes. Discard writes `live: resolve held-copy {path} reason={hold reason} slot={slot}` and no baseline line, because the projection and the baseline stay. The button stays Discard. One Submit can clear more than one out-of-sync reason on a path, so that line names the outcome `out-of-sync`, not `stale-base` or `fan-out-mismatch`. A held copy has one hold reason, so the reason id is on that line.

This amends 0009, 0024, and 0028. Those ADRs defer inspect and restore, and 0009 forbids a discard shell. The shell ban and the restore deferral stand. The deferral of inspect does not. 0024's "held rows show the hold reason only" does not.

## Status

accepted

## Considered Options

- Put the held bytes back onto the projection. Rejected: the live path is already the installed result. An empty `create-overwrite` of `.grok` would replace `config.toml` with an empty directory. The `.kiro` hold would replace the live `steering/` tree with the older files.
- A `blf` discard command. Rejected: 0009's ban on a discard shell stands. The resolve UI is already where the row is. `daemon status` still prints the slot path.
- Drop an empty held directory without a click. Rejected: that empty directory is the held copy. It stays in `status` until Discard.
- Reuse sequential replica merge for the diff, including chunk accept and mark as merged. Rejected: the page is for reading the held bytes against the projection, not for writing a new hub generation.
- Discard on one click, with no dialog. Rejected: the resolve UI already has a confirm dialog, and a slot can hold bytes that differ from the projection.
- A log verb `live: discard`, or no log line. Rejected: Submit already writes `live: resolve` to the request log. Both outcomes use that verb. The second word is the edge outcome, `out-of-sync` or `held-copy`.

## Consequences

- Glossary **Discard**, **Resolve**, **Resolve UI**, and **Request log** name the log lines. **Discard** still avoids calling the action resolve.
- The old request-log line `live: resolve {path} gen {n}` gains `out-of-sync` after `resolve`.
- Restore of a held copy is still later.
