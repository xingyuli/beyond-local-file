# Idle observe reuses the last hash when a file's stat signature is unchanged

Idle observe reads a file's contents only when its stat signature (size, mtime, ctime, inode) differs from the last scan, or when the entry is racy: its mtime is less than 2 seconds older than the moment it was last hashed. Otherwise it reuses the last SHA-256. SHA-256 stays the one grain of sameness (ADR 0029); the signature only decides whether to re-read. The cache lives in memory per worker unit, so the first scan after a daemon start hashes everything. Apply-time scans (`scan_path_state`) always hash.

## Status

accepted

## Considered Options

- Trust size and mtime only. Rejected: mtime can be set back (`touch -d`, `cp -p`, `rsync -t`); ctime cannot be set from user space.
- Back off or pause the idle interval instead. Rejected as the primary fix: a machine in use still re-hashed the whole tree every tick (about 600 MB for one unit). Pausing while the display sleeps is a separate ticket.
- FSEvents or inotify watching. Rejected: another dependency and platform-specific code; polling stays.
- Periodic full re-hash as a safety net. Rejected: with ctime a missed change is implausible, and a safety net would hide a bug in the signature rule.
