# Three logs, millisecond stamps, and `blf logs`

Idle observe and shell requests are separate records. A merged follow tells them apart. The clock is fine enough to compare phases of a request.

## Status

accepted

## Context

0015 stamps every worker line into one `daemon.log` at a resolution of one second, and `daemon logs` follows that file. 0020 added request and step lines to that same file so a slow shell could be explained. After 0021 the set-wide corridor those lines were built to explain is gone. A reader opens the log to see why daemon work took the time it did. Idle ticks, mostly with no change, bury the request. The shell's own startup is a different process and is not part of this record.

## Decision

- Three records live in the set run directory: `logs/idle.log`, `logs/requests.log`, and `logs/daemon.log`.
- The idle log records idle ticks, and when a tick applies, the apply, held-copy, and persist lines that follow. A tick under 100ms that finds nothing is omitted. Every line names its worker unit.
- The request log records each shell request and every step of the work that request caused, including a reload's catch-up, however small the step. Every line names its worker unit. `request: start` and `request: done` carry `queue_ms`, `op_ms`, and `persist_ms` (`persist_ms` absent on a dry-run). A check or reload on several worker units lists each unit's duration. `done` is the wall.
- The daemon log records process start, the catch-up that belongs to start, ready, stop, and a failure that is neither an idle tick nor a shell request.
- The stamp stays 0015's write-time local offset, at millisecond resolution (`2026-09-21T18:55:09.184+08:00`).
- `blf logs` follows the three files merged by that stamp until Ctrl+C. Ctrl+C stops the follow, not the daemon. While merging it prints `[daemon]`, `[idle]`, or `[requests]` in front of the stored line. Each name has a stable color when stdout is a terminal. A pipe keeps the prefix and drops the color. `blf logs requests`, `blf logs idle`, and `blf logs daemon` follow that one file and print its stored lines with no prefix.
- `daemon logs` is retired. Running it prints a line that names `blf logs`.

## Consequences

A shell request can be read without idle ticks between its lines. An apply the daemon made on its own is in the idle log. Start's catch-up is in the daemon log. 0015's single file, one-second stamp, and `daemon logs` no longer hold. Stamping at write time, in the host's local offset, still holds.
