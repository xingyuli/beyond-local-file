# A directory node has no generation

A baseline row exists only while that node exists. A missing row means the path is absent. One idle tick sees one snapshot, so edits that land before the scan are one change.

A directory row has no generation. Removing the directory deletes the row. A directory delete does not use the generation window and holds nothing. A file and a symlink share one generation. It starts at 0 for install, fresh catch-up, and rescan, and a later live apply increments it. An idle tick that sees the file or symlink gone ends that generation. The next tick that sees it starts at 1. A change between a file and a symlink applies when the base matches and increments that same counter. A base that does not match is out of sync, recorded as the node that replica still has.

A delete of a file or a symlink wins when the hub generation is at most 3 ahead of the replica's base. A directory base counts as 0. Past that window the file bytes or the link text are held as ``delete-gap``, and the row is dropped.

A file becoming a directory, or a directory becoming a file, holds the previous file bytes as ``kind-change``, writes the new node, and does not mark out of sync. Every file that snapshot removes under the directory is held. The new file starts at generation 1. The directory row has no generation. 0031 stands: those held files are not carried as the directory's own change.

A directory becoming a symlink, or a symlink becoming a directory, does not use ``kind-change``. That switch is intentional. A matching base applies. Children of the directory are dropped and not held (0032). The symlink starts at generation 1, or the symlink's generation ends. A mismatched base is out of sync.

This amends 0008, 0032, and 0036. 0008's generation is not stored on a directory. 0032's ``present`` flag is not stored. 0036's catch-up records a directory with no generation and records each file and symlink at that path's hub generation.

## Status

accepted

## Considered Options

- Keep a directory generation and an absent row so a later create continues the counter. Rejected: a directory has no bytes, and a missing row already means absent. Ending the counter on an observed delete is accepted for a file and a symlink too.
- Treat a file and a symlink like a file and a directory, and always hold one direction. Rejected: a symlink has a generation, so both directions compare the same way. An asymmetric hold was harder to follow.
- Hold the children when a directory becomes a symlink. Rejected: switching a directory and a symlink is intentional, and 0032 already leaves those children unheld.

## Consequences

- Catch-up copies each file and symlink at its hub generation and copies a directory with no generation. A path with no row is absent. ``delete-overwrite`` still holds a new target's bytes when the hub has no item.
- An out-of-sync directory is the directory row that replica still has. The clause names the replica and the path and has no generation.
- A same-kind file conflict stays out of sync (0010). ``kind-change`` is not used for it.
