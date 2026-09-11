# revlink create fans out; collisions hold with a reason

`revlink create` is item-add: copy into the hub, then fan out to every other target of that managed project (source replica excluded). Selective mappings all receive the subpath. That is the expand-phase form of “tell the daemon this path is a managed item.”

If a non-source replica already has different bytes at that path, those bytes are stored as a held copy with hold reason `create-overwrite`, then the hub copy overwrites the replica. Equal bytes are left in place and recorded in-sync. WARNINGs print the hold-reason clause so a later resolve UI can show the same text.

## Status

accepted

## Considered Options

- Fan out only on a later `link sync`. Rejected: create's intent is “this path is now a managed item,” which includes every replica of the hub.
- Skip replicas with different bytes. Rejected: the new managed item would not appear there; the user asked to overwrite after holding.
- Overwrite without holding. Rejected: the file would be lost.
