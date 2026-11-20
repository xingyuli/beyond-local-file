# Managed reports target state as JSON, not exit status

`blf managed [PATH]` tells a caller what blf projects into a directory. It is a Shell that asks the daemon (0006), runs from any directory, and never opens a shell screen (0023). Its stdout is one JSON document. `managed: false` is a normal answer and exits 0. Exit 1 means the command could not answer (daemon down, configuration set failed, daemon error). Exit 2 is a usage error. Callers get a structured answer, and a failure never reads as "not managed".

The first JSON-only command sets a precedent, so the output describes itself. `blf managed --schema` prints the JSON Schema, with the command's purpose and a description for every field. The output carries `schema_version`, bumped on a breaking change. One Python definition builds both the output and the schema, and tests validate real output against it.

PATH is the directory to look at, defaulting to the current directory. The target is the nearest ancestor-or-self that is a target project, and `is_target_root` says whether PATH itself is that target. The daemon answers from the mappings its worker units hold in memory, never from a mapping file (0014), so it reports what is actually projected, and an unreloaded mapping edit is not reported. Like the other shells, a request during catch-up waits until the daemon is ready (0019).

## Status

accepted

## Considered Options

- Exit status as the answer (0 managed, non-zero not). Rejected: it cannot separate "answered no" from "daemon down" or an old release without the command.
- Three exit codes for managed, not a target, and path uncovered. Rejected: the answer carries more than a code can, and a bad exit would read as a failure.
- A PATH to a file, with a `covered_by` field naming the item and hub file. Rejected: it invites file-by-file calls. `items` answers in batch, and the caller derives a hub path from `hub_path` plus the rest of the path.
- Read mapping yaml directly, without the daemon. Rejected: it would report mappings the daemon has not loaded, and changes made in a target are only observed by a running daemon.
- A `--json` or `--format` option, or a `managed schema` subcommand. Rejected: JSON is the only format, and a subcommand is ambiguous with a directory argument.
- Record the program name (`blf`, `blf_dev`) in the runtime home. Rejected: the tool cannot know a wrapper's name. Callers use `BLF_CMD`, then `blf`, then ask.
