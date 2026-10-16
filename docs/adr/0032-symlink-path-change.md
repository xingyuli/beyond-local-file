# A symlink path change is its own kind

`symlink` is the path change that makes one path a symlink node: a new symlink, a file or directory replaced by one, or a retarget. It is not an update. An update of a directory touches that directory only; replacing the directory with a symlink removes the directory, children included. Those children are not path changes, are not snapshotted, and are not held. A replica that already has the same symlink text is in sync. A different node, or a different symlink text, stays out of sync and is left untouched.

Deleting a symlink stays delete and unlinks that node, not its target. Replacing a symlink with a file or directory stays that file or directory's path change.

## Status

accepted

## Considered Options

- Classify the transition as update and special-case a symlink hash inside update. Rejected: the directory rule then lies, because this update removes children.
- Kinds for create, update, and delete under a symlink. Rejected: the walk stops at the symlink, so those changes are not observed.
- A stored through-symlink state for paths reached by following the link. Rejected: nothing asks, and `present` would no longer mean this snapshotted node is in the tree.
- Hold files that existed only in the replaced directory. Rejected: those paths leave with the directory, and holding them recreates a large held-copy list.

## Consequences

`present` stays a bool and means the snapshotted node is in the tree, not that a filesystem lookup succeeds. Fan-out copies the symlink text. The same text records the replica at the new generation. A different text does not write and does not drop that replica's child rows while they are still nodes.
