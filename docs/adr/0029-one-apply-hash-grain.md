# One apply hash grain; no MD5 verify

Sameness on the write path is per-file SHA-256 (`scan_path_state` / `scan_items`), the grain live already uses. `ChecksumVerifier` (whole-tree MD5) is retired. Create and restore trust `copy_projection`; I/O failure is `OSError`. Remove still refuses when a projection does not match the hub, using that same SHA-256. Item-add collision (hold `create-overwrite`) compares the scanned tree, not a second digest. `link check` may still roll files up to an item digest for the table; that is a read, not a second write grain.

## Status

accepted

## Considered Options

- Keep MD5 verify on create/restore/remove as a post-copy integrity check. Rejected: local `copy_projection` already fails on I/O, and tests had to mock a digest the rest of the daemon does not use.
