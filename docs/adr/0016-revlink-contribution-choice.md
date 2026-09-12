# Revlink chooses a hub by path owner or a shell interview

Several managed projects may contribute disjoint items to one target. Restore and remove run inside that target: PATH under exactly one contributor's item selects that hub; a path that is not a managed item is an error, not CWD-level ambiguity. Only create can add a new item. When several hubs target CWD and PATH is new, the shell interviews for a 1-based project name in the same invocation. No `--project` flag. The daemon worker stdin is DEVNULL, so the prompt cannot run inside a handler.

Create already covered by one item sends that `project_name` and hits the existing already-covered rule. Fan-out stays on the chosen hub's replicas. No TTY (or an aborted prompt) lists the project names and exits 1.

## Status

accepted

## Considered Options

- Keep `Ambiguous: multiple projects target <cwd>` for create, restore, and remove. Rejected: restore/remove are not ambiguous once PATH is matched to a contribution source; create can interview instead of forcing a second command.
- Add `--project` on create/restore/remove. Rejected: restore/remove do not need it; create should continue the same invocation after a number is typed.
- Prompt inside the daemon handler. Rejected: worker stdin is DEVNULL.
- Interview in the shell, send `project_name` on create, resolve restore/remove by contribution source. Accepted.
