# One daemon process per configuration set

`~/.blfrc` is replaced by the **global config** ``~/.blf/config``: a pointer list of mapping yaml files. That list is one **configuration set** and is loaded by one OS process. A configuration set is identified by one path: the global set by ``~/.blf/config``, a **singleton set** by the resolved mapping yaml (``-c PATH``, or CWD ``config.yml`` when there is no global list). A dedicated demo ``config.yml`` does not share a worker with the user's global set.

The set run directory, mapping-file list, overlap scan, and load of mapping yaml are derived from that identity. The mapping snapshot stays the last committed mappings (0005).

Resolution order: ``-c`` / ``--config``, else ``~/.blf/config``, else CWD ``config.yml``.

A yaml file already loaded by a running set is served by that process — ``-c`` does not start a second watcher. Starting a set that shares a mapping file with another running set is an error (stop the owner first). Two sets never observe the same mapping file. Start does not attach: it refuses overlap after ``is_running`` for this identity, so this set's own pid is "already running," not overlap.

Ready-path work uses the mapping snapshot and the worker's in-memory projects. Mapping files on disk are read at start, on reload, and after an internal splice. Shells talking to a running daemon send the set identity; they do not re-read mapping yaml before IPC.

This is not kube's cluster/context model. ``~/.blf/config`` is only the pointer list (the former ``config_file`` field). Mapping documents stay where the user keeps them.

## Status

accepted

## Considered Options

- One OS process for the whole machine; ``-c`` only filters shells. Rejected: the VHS demo uses ``--config config.yml`` in ``demo-workspace`` and must not attach to the user's global set.
- One OS process per mapping yaml listed in the global config. Rejected: the global list is one set; two yamls are not two runtimes. ADR 0003 is one process with a queue per managed project.
- ``-c PATH`` always spawns a singleton even when that path is already in a running set. Rejected: two observers on the same trees.

## Consequences

- ``revlink`` / ``remove`` / ``link check`` without ``-c`` talk to the global set's process when ``~/.blf/config`` exists.
- ``daemon start|stop|status|logs`` use the same resolution order as shells.
- Process identity for a singleton set is the resolved mapping-file path; for the global set it is ``~/.blf/config`` (run directory ``~/.blf/run/global/``, 0018). ``upgrade`` with no ``-c`` talks to that global identity, not the first listed mapping yaml.
- Two public loaders that looked interchangeable are one module: identity, mapping files, overlap, load.
