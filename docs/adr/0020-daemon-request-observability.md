# Daemon log records shell requests, op steps, and set-wide work

A slow `revlink create` of a tiny path left no trail: request stdout is captured for the CLI, and `daemon.log` only showed catch-up copies and live applies. The worker now logs each shell request, mutating-op steps with durations, and the set-wide scans/writes that can dominate wall time — on the timestamped daemon log, not as CLI output.

## Status

accepted

## Context

The serve loop is single-threaded. `on_idle` and `before_request` both call `LiveSync.tick()`, which SHA-256-hashes every watched file on every hub and replica in the configuration set. After a successful create/restore/remove the worker records a full-set baseline and dumps `baseline.yml`, then `live.reload` scans again. None of that work had a name or a duration in `daemon.log`.

`CreateFormatter` step lines exist, but `handle_request` captures stdout for the shell. ADR 0015 stamps worker prints; captured request stdout is not the daemon log.

## Decision

Bind a worker stream at process start (the 0015 timestamp wrapper). Log through that stream so `redirect_stdout` cannot steal the lines.

- `request: start` then `request: done` for each served shell op (`op`, `path`, `cwd`, `exit`, `duration_ms`). Start is written *before* the pre-request live tick so a hang still leaves a line.
- Create, restore, and remove steps log `duration_ms` (`create: copy`, `create: checksum`, …).
- Live ticks log `reason` (`idle` or `before-request`), `roots`, `paths`, `files`, `hashed_bytes`, `duration_ms`, `applied`. Idle ticks faster than 100ms with no apply are omitted.
- `live: scan` (init and reload), `baseline: record`, `snapshot: write`, `baseline: write`, and `persist: done` log duration and size context.

Timestamps stay on every line (0015). Formatter output returned to the CLI is unchanged.

## Consequences

A future slow run can be explained from `daemon logs` without a debugger: which request, which step, and whether set-wide hashing or yaml dump dominated. CLI progress streaming is a separate change. This does not make create faster.
