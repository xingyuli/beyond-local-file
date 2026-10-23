# Forced remove clears an unmatched declared item

`remove --force` clears the same set as a successful remove: the managed copy, every projection, git exclude on each projecting target, and the subpath. A copy that is already absent still counts as cleared. A remaining copy is deleted even when it does not match the managed copy, including different bytes or a symlink. A directory item is the whole tree. Without the flag, remove still requires the managed copy to exist and the copies to match. A path delete still leaves the item declared, so putting the file back syncs until remove.

## Status

accepted

## Considered Options

- Ordinary remove succeeds on an empty declaration, with no flag. Rejected: the leftovers are cleaned only when the user passes force, and the unforced command stays strict.
- Force only accepts already-absent copies. Rejected: a remaining unmatched copy is one of the leftovers, and the command would still stop with nothing cleared.
- Leave an unmatched copy on disk and only drop the subpath and git exclude. Rejected: stripping git exclude would show that file to git, and the leftover would remain.
- A path delete of the item root unregisters it. Rejected: an accidental delete can be undone by putting the file back while the item stays declared.
- Ask on a terminal before deleting an unmatched copy. Rejected: the flag is the confirmation, and remove already asks nothing.

## Consequences

- The path must still be the declared selective item. Force still refuses a path that is not that item, a participating target that is inaccessible, a path reached through a directory symlink, and a git exclude file that cannot be read.
- Held copies stay in the attic. A sync-all name that item discovery has already dropped is not a forced remove.
- The item's baseline row is forgotten, including the out-of-sync marks remove already drops.
- Dry-run lists this cleanup and writes nothing. Forced remove does not ask. The shell screen stays the one remove already opens.
- The transcript reports a present path as deleted and an already-absent path as absent. A failed configuration splice keeps remove's existing repair report.
