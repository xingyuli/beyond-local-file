# Sequential two-way replica merge, driven client-side

0024's merge model was a single 3-way merge (hub-now, result, replica-now) with server-computed, ancestor-stash-aware hunks (`accept-ancestor`, `next`/`prev` conflict). In practice a path can have several out-of-sync replicas, and they are resolved one at a time: the merged result of replica N must become the starting point for diffing against replica N+1. There is no single ancestor that stays valid across that whole chain — a stashed ancestor only ever describes one hub-vs-one-replica divergence, not the sequence. The 3-way ancestor model also produced a page nobody could operate: raw text panes with no visual diff, and a "same middle across every replica switch" bug once ancestor-relative hunks were involved.

We replaced it with a sequential two-way flow, IntelliJ-merge style: the left pane starts as hub-now; the right pane is the first replica whose live bytes differ from hub. Both are diffed directly (no base) in a `CodeMirror.MergeView`, with the middle pane pre-seeded from the left and editable via CodeMirror's own per-chunk revert arrows or manual edits. Clicking "mark as merged" freezes the middle as the new left and advances to the next differing replica; replicas already `same as hub` are listed (so the full picture stays visible) but are not opened. Once every differing replica is merged, "submit" becomes enabled. The daemon serves every replica's live content once per page load; the browser does all diffing, chunk-accepting, and round-to-round accumulation itself, and only calls back to the daemon on submit — there is no more server-computed hunk/conflict state or per-hunk POST actions.

## Status

accepted

## Consequences

`merge.py`'s ancestor-aware hunk engine (`Hunk`, `MergeResult`, `merge_text`, `apply_action`, `Choice`) is gone; only `is_binary` remains. The daemon no longer tracks a current hunk, choices, or conflict state for a path — GET renders everything needed for the whole sequence up front, and POST only carries the final `submit`. 0024's "hunks use the selected right replica's stash" and "3-way merge... with a replica switcher" language is superseded by this decision. 0024's other decisions stand: the second localhost port and token auth, nav grouping by managed project, `same as hub` labeling, and overwrite of every replica of a path. The hub-byte ancestor stash is dropped from the out-of-sync row; sequential merge diffs live hub-now against replica-now and does not need it. The out-of-sync reason clause remains and is shown per replica in the list.
