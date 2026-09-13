# One daemon process per configuration set

`~/.blfrc` is replaced by the **global config** ``~/.blf/config``: a pointer list of mapping yaml files. That list is one **configuration set** and is loaded by one OS process. ``-c PATH`` is a **singleton set** identified by the resolved path of that mapping file (so a dedicated demo ``config.yml`` does not share a worker with the user's global set). With neither, ``config.yml`` in CWD is a singleton set.

Resolution order: ``-c`` / ``--config``, else ``~/.blf/config``, else CWD ``config.yml``.

A yaml file already loaded by a running set is served by that process — ``-c`` does not start a second watcher. Starting a set that shares a mapping file with another running set is an error (stop the owner first). Two sets never observe the same mapping file.

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
- Process identity for a singleton set is the resolved mapping-file path; for the global set it is the global run directory (0018).
