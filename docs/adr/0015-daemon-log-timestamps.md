# Daemon log timestamps at write time

Worker stdout is redirected to ``daemon.log`` in the set run directory (0018) with no clock. `daemon logs` tails the file as stored. Stamping belongs in the worker at write time so every `print` gets a local-offset prefix without changing callers or rewriting old unstamped lines.

## Status

accepted

The single ``daemon.log``, the one-second stamp, and ``daemon logs`` are superseded by 0022. Stamping at write time, in the host's local offset, stands.

## Context

The daemon worker's stdin is DEVNULL. Catch-up, live, and runtime progress is `print(..., flush=True)`. `spawn_and_wait` opens the set's `daemon.log` as the child's stdout (stderr merged). `daemon logs` follows that file and must not add a display-only clock. Lines already in the file stay as written. TTY status lines for catch-up and `link check` are streamed to the shell (0019); they are not a second clock on the log.

## Decision

Inside `run_worker`, wrap `sys.stdout` and `sys.stderr` before the first print. Each new line is prefixed at write time with `datetime.now().astimezone().isoformat(timespec="seconds")`, then a space, then the original line:

```
2026-09-12T17:42:03+08:00 live: update alpha.txt gen 1
```

The stamp is the daemon host's local timezone with offset. `daemon logs` prints the file unchanged.

## Consequences

New worker lines in the set's `daemon.log` are timestamped; old unstamped lines are not rewritten. Shell request stdout captured via `redirect_stdout` is not stamped. Direct writes to the file descriptor bypass the wrapper.

Stamp in `daemon logs` when displaying was rejected: the file would still have no clock, and two viewers would disagree. Changing every `print` was rejected: easy to miss; the stream wrapper covers all worker prints. Host-side stamping in `spawn_and_wait` was rejected: line writes happen in the child.
