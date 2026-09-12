# Runtime contribution source

When several managed projects contribute disjoint items to one target, a path change on that target belongs to exactly one item and therefore one hub. Live observe derives that owner from committed mappings (item name equals the path or is a prefix of it). It is not stored in the baseline or the mapping snapshot.

Fan-out copies only to other in-sync replicas of that same managed project. Another hub's replica that happens to use the same item name is not written and is not marked out-of-sync.

## Status

accepted

## Considered Options

- One hub per replica watch (first processing unit). Rejected: a change to another contributor's item is applied to the wrong hub; fan-out matches item names globally.
- Persist owner on each baseline path. Rejected: no scenario depends on a persisted index; reload already rebuilds from mappings.
- Derive owner at observe/reload from committed mappings; scope fan-out to that hub. Accepted.
