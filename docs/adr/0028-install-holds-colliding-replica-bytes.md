# Install holds colliding replica bytes

Whenever hub bytes are installed onto a replica that already has different bytes — `revlink create` fan-out, fresh catch-up, target-add, ingest item-add — those replica bytes are stored as a held copy with reason `create-overwrite`, then overwritten. Equal bytes are left in place. The hold is the item tree, not each nested file. Silent overwrite is rejected: the replica's file would be lost. The resolve UI lists the held copy. 0038 is the read-only diff and Discard. Restore stays later (0009).

## Status

accepted

## Considered Options

- Hub-truth overwrite with no hold (0003 as implemented). Rejected: first start or target-add of a replica that already had files would lose those bytes.
- A second hold reason for catch-up. Rejected: the user-visible situation is the same as create fan-out — install replaced different replica bytes.
