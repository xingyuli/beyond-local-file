# A directory path change does not carry its children

A live path change for a directory creates, updates, or removes that directory only. Each file and each nested directory is its own path change and carries its own base. A replica that keeps writing a new tree stays in sync: later bytes are ordinary updates while the base still matches the hub. Out-of-sync stays a different writer: another replica that lost compare-and-swap, a replica whose disk was not the expected base at fan-out, or a replica that saved over a direct edit on the managed project.

Copying the whole directory when the directory path applied published children before their own creates ran. Those creates then lost compare-and-swap against a snapshot of the same replica, and files still open stayed excluded. Fan-out of that directory also replaced the destination tree whenever the directory merely existed, which drops a child only another replica had. Per-path grain is 0004. The lost-update rule is 0010.

Item install, fresh catch-up, and seed still copy the whole item (0028). Deletes stay deeper-first, then the directory. Fan-out of the directory path creates or removes that directory on in-sync replicas; children follow their own path changes.

## Status

accepted

## Considered Options

- Copy the whole directory, then if that same replica's child loses compare-and-swap, write the child's current bytes. Rejected: the first fan-out still publishes a mid-write snapshot, and a directory that merely exists still compares equal, so fan-out can drop another replica's child.
- Wait until the tree stops changing, then copy it. Rejected: 0008 already rejected a clock as the coalesce mechanism.
- A permanent rule that a longer replica file, or a file that starts with the hub bytes, clears out-of-sync. Rejected: that is also how a real lost update looks.

## Consequences

Marks already caused by the directory copy are not a path list in the product. A one-time adoption of the marks identified when this decision was made is the existing resolve operation, fired once locally after the new daemon is running: the excluded replica's current bytes are the confirmed fact. No recovery code is committed. A path already resolved, or whose excluded copy is gone, is skipped. Any other out-of-sync path, and any later mark on an adopted path, stays for resolve.
