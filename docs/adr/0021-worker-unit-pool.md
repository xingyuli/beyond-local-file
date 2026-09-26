# Accept thread never hashes; one job per worker unit

The daemon process is two programs. The accept thread binds the port and answers `status`. Work that hashes or mutates a hub runs as a job on the **worker unit** for that managed project — at most one job at a time. Distinct worker units run in parallel.

## Status

accepted

The TTY status-line sentences in the decision below are superseded by 0023. Worker-unit scheduling stands.

## Context

A single serve loop used to accept, idle-observe, pre-request tick, and handle shells. A ~3s hash of every root in the configuration set held `accept`, so `status` and unrelated shells stalled. See 0020 and the redesign ticket.

A ConfigProject with several mappings/targets is not several threads. The thread is the managed project (hub + every target). The expanded managed×target row is a **mapping unit**, used for check rows and fan-out, not for scheduling.

## Decision

- One worker unit per managed project: a queue and a `LiveSync` over that hub and its targets only.
- Idle observe is a job on that unit, 15s from the end of that unit's last idle observe, with units staggered.
- Create, restore, and remove enqueue on the unit that owns the PATH (mapping snapshot / contribution source / `project_name`).
- `link check` with no project name enqueues on every worker unit and merges the table; with a project name, that one unit. Progress is `Checking i/n … item`, filled as mapping units finish.
- `daemon reload` catch-up jobs run only for worker units whose mappings changed (start new units, stop removed ones).
- Mutating shells apply the mailbox (no scan), then the op. They do not start an observe. TTY: `Waiting …` if that unit is busy, then Creating/Restoring/Removing, then `Writing baseline …`. Non-TTY has no status line.
- Resolve apply from the resolve UI enqueues on the worker unit for that managed project. The HTTP accept thread does not write the hub.
- Splices of a mapping yaml or `.git/info/exclude` take a process-wide lock per file so two worker units cannot lose each other's writes.
- `status` never joins a worker-unit queue.

## Consequences

A hash or create on one managed project does not block `status` or a shell for a different managed project. A mutating shell for a busy unit waits on **that** queue only. The expanded managed×target row is a `MappingUnit` in code, not a thread.
