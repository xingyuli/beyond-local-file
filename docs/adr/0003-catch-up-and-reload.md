# Fresh catch-up, update catch-up, explicit reload

The daemon distinguishes two starts by whether a baseline exists for that managed project. No baseline: **fresh catch-up** — projections are made to match the managed project, then observation begins. Baseline present: **update catch-up** — only paths that differ from the baseline are queued (stale-base conflict still applies), then observation begins. A crash is always update catch-up; first 0.5.0 start is fresh.

A new target project on an existing managed project is fresh **for that replica only**. Other replicas are not reset.

Mapping files are not watched. External mapping edits take effect through the reload classifier (`daemon start` when the files differ from the snapshot, `daemon reload` when already running). One OS process loads one **configuration set** (0017); each managed project has its own queue.

## Status

accepted

## Considered Options

- Treat every start as hub-truth. Rejected: downtime would delete target-project work.
- Treat every start as a full Q9 snapshot with no hub-truth fresh. Rejected: first start has no baseline to detect against; a truth must be chosen, and that truth is the managed project.
- Watch `config.yml` and apply mapping changes live. Rejected: mapping changes are deliberate and must be an explicit reload.
