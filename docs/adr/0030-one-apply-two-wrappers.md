# One apply; idle tick and shell request are wrappers

The module is LiveSync. Hub write, fan-out, hold, out-of-sync, git exclude, and baseline record sit in one `apply`. `tick` (idle / update catch-up) and `request` (shell / fresh catch-up / resolve) wrap it. There is no sibling Apply type. How work arrives differs: idle observe discovers path changes from disk (passive); a shell request names the job (proactive). Those are two wrappers over the same implementation. A mutating shell still applies the mailbox then the named job and does not start an observe (0021). Mapping yaml splice stays in the wrapper (`ConfigUpdater`); apply does not write yaml. Create splices then names the install job. Ingest only names the job. Restore and remove name the disk job, then splice the drop. After a splice, watch roots change without forgetting last-seen (`replace_projects`, not `reload`). Create, restore, remove, and resolve are no longer a second write engine. Update catch-up is the idle wrapper (detect vs baseline). Fresh catch-up and target-add are named install jobs on the shell-style wrapper.

## Status

accepted

## Considered Options

- Separate write engines for live, catch-up, and create. Rejected: create copied then asked live to forget; catch-up built a throwaway LiveSync. The write policy drifted.
- One `apply(jobs)` overload that idle tick must pass empty jobs. Rejected as the public shape: detection and submission are two wrappers, not a flag on the hot method.
