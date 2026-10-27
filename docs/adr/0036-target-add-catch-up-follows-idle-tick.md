# Target-add catch-up follows the idle tick

Renaming a target directory and editing the mapping is a target-remove of the old path plus a target-add of the new path. The path is the identity; baseline rows do not follow the directory. Reload and start were letting update catch-up treat the new directory's existing tree as creates, so the hub and the ``files`` baseline took a new generation from the replica. That is rejected. Catch-up observes the hub the way an idle tick does, and the hub file is the truth. Hub writes stay in ``apply``, through the idle wrapper (0030). A new target does not become the source of a create. When the hub file differs from its baseline row, the generation increments once and the result fans out to in-sync targets; the new target's different bytes are held with ``create-overwrite``, then that target is installed from the hub result. When the hub has no item, the new target's different bytes are held with ``delete-overwrite`` and the projection is removed. ``delete-gap`` stays the generation-window delete, and it keeps hub bytes. Each path on the new target is recorded at that path's hub generation. A directory child takes the child's generation, not the directory node's. The hold stays one tree.

This amends 0030 and 0009. 0030 made every target-add a named ``seed_item`` job, including update catch-up. That job records generation 0 and cannot express "the hub has no item." Update catch-up of a new target is the idle tick, then one named install of the hub result (``install_fresh_item``). 0009's hold reasons gain ``delete-overwrite``. ``create-overwrite`` is unchanged.

## Status

accepted

## Considered Options

- Adopt the new directory's bytes onto the hub. Rejected: the hub is the source. A path change must not rewrite the baseline from the replica.
- Install the current hub disk onto the new target first, and leave the hub row unchanged until a later apply. Rejected: fan-out then sees the new target already holding the new bytes and marks it out of sync (0010). One idle-tick apply is easier to follow and to maintain.
- A special rule that hub disk wins on any generation conflict, including already-mapped replicas. Rejected: idle fan-out already uses the hub file for in-sync targets and still skips out-of-sync ones (0010).
- Hold reason ``hub-absent``, or reuse ``create-overwrite``, when the hub has no file. Rejected: ``create-overwrite`` means a hub file replaced replica bytes (0028). ``delete-gap`` keeps hub bytes. The new situation is a new target's different bytes removed because the hub has no file. The same reason covers a row that was already absent (the generation stays) and a hub delete this catch-up just applied (the generation increments).
- Stamp every path in the new target's scan with the directory node's generation. Rejected: a directory path does not carry its children (0031). The child's next edit would carry the directory node's base while the hub is at the child's generation.

## Consequences

- ``daemon reload`` and ``daemon start`` share this catch-up. Decline commits nothing.
- A removed target's baseline rows are dropped before catch-up, so a renamed-away directory is not observed as deletes of the hub. Item-remove drops that replica's rows for the item and leaves the hub file.
- A selective target's section of ``files`` lists only the file items it declares. A directory item is one held tree. A new target's baseline rows match the hub generation of each path.
- Glossary **Hold reason** names `delete-overwrite`. Glossary **Generation** says when a directory node's generation increments. This ADR is the catch-up rule.
