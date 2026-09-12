# Preserve nested symlink nodes on copy

A projection path is a real file or directory, not a symlink to the hub. Nested symlink nodes inside a directory item are part of the tree (venv ``python`` → ``python3.14`` → the real interpreter) and must be copied as symlinks. Following them writes regular files, so the hub hash (``symlink:<target>``) never matches the replica, and interpreters stop being the binaries the tree named.

Catch-up, live fan-out, CopyManager, and revlink all replace a destination with ``copy_projection``: copy a symlink as a symlink; ``copytree(..., symlinks=True)`` for directories; ``copy2(..., follow_symlinks=False)`` for files.

Windows may need Developer Mode (or equivalent) when a directory item contains nested links. Dangling nested links copy as dangling.

## Status

accepted

## Considered Options

- Follow nested symlinks (``copytree`` default). Rejected: venv interpreters become Mach-O copies; check reports managed-changed forever.
- Preserve only links whose target stays inside the item. Rejected: ``python3.14`` points at Homebrew or uv; that is the real venv shape.
- Preserve every nested symlink node. Accepted.
