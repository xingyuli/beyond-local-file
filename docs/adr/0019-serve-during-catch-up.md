# IPC is up during catch-up; progress is one TTY status line

The worker binds the localhost port and accepts requests as soon as it is running. Catch-up runs **after** that bind. ``daemon status`` reports phase ``catch-up`` or ``ready`` and always includes the pid. Live observation starts only in ``ready``.

``daemon start`` stays in the foreground until ``ready``, rewriting one status line (unit ``i/n``, current item name, no per-file paths). Shells other than ``status`` wait through ``catch-up`` with the same kind of line, then run. The check **table** is printed once at the end; it does not show progress. Non-TTY: no status line, final table only. ``--format verbose`` stays line-oriented.

``link check`` compares live hashes of managed vs target (0006). The pre-request live tick is not a substitute for that comparison.

The worker's stdout remains the set's ``daemon.log`` (0015). Status lines are a **stream on the shell's IPC connection**, rendered by the shell that owns the TTY. The daemon does not drive Rich Live.

## Status

accepted

## Considered Options

- Wait to bind until catch-up finishes (0.5.0). Rejected: start and check look hung; progress cannot use IPC.
- Follow ``daemon.log`` until ready. Rejected in favor of status-phase + streamed status line once IPC exists from the first moment.
- Catch-up in the shell, then spawn a serving worker. Rejected: two hosts for catch-up (0005).
- Return from ``daemon start`` as soon as sockets accept. Rejected: the next ``link check`` in the same TTY would race; start is finished when projections exist.
- Live Rich table with ``k/n`` in cells. Rejected: one status line, then a static table.
- Check from baseline without rehashing. Rejected: check means do the bytes match **now**.

## Consequences

- ``daemon.ready`` as "catch-up finished" is replaced by phase ``ready`` on the status RPC. The port file exists in ``catch-up``.
- Mutating ops during ``catch-up`` wait; they do not apply in parallel with catch-up.
- A stuck catch-up can be targeted with ``status``'s pid.
