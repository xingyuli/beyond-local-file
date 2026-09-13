# Runtime home is ``~/.blf``; mapping hubs stay clean

Pid, port, log, mapping snapshot, baseline, and held copies live under ``~/.blf/``, not next to a mapping file and not inside a managed project. Hub-local ``.blf/`` was natural before a global pointer list existed; ``~/.blfrc`` (now ``~/.blf/config``, 0017) made that the wrong default.

Layout:

```
~/.blf/
  config
  run/global/{pid,port,ready,log,mapping-snapshot.yml,baseline.yml}
  run/file-<sha256 of resolved mapping yaml>/{...}
  held/<sha256 of managed project path>/
```

``sync-state.yml`` is gone. It was the ``link sync`` book. Baseline in the set run directory is the daemon's per-path truth. ``link check`` hashes managed vs target live (0006); baseline only labels which side moved.

Held copies move out of ``.blf-held/`` in the managed project (location only; hold reasons stay 0009). Discovery still skips a leftover ``.blf-held/`` name. New holds are written under ``~/.blf/held/<hash>/``.

Existing hub-local ``.blf/`` is not imported (fresh catch-up). First start that uses the runtime home **deletes** those ``.blf/`` directories and prints each path. There is no ``.blf-held/`` to migrate on the current hubs.

## Status

accepted

## Considered Options

- Keep ``.blf/`` next to each mapping yaml. Rejected: the yaml's parent is a user hub; pid/snapshot/log are runtime noise.
- Keep held copies in the managed project. Rejected: users can operate on them by accident; the directory is reserved only because it lived in the tree.
- Import old snapshot/baseline into ``~/.blf``. Rejected: current check is in-sync; first start after the move is a fresh catch-up.
- Delete leftover ``.blf-held/`` on first start. Not required: no such dirs on the current hubs. Relocate if a non-empty attic appears later rather than ``rm`` user bytes silently.

## Consequences

- ``BLF_HOME`` continues to relocate the home used for ``~/.blf`` in tests.
- Two configuration sets cannot share a pid file; that is why run directories are per set.
- User-facing docs that say ``~/.blfrc`` or ``<config-dir>/.blf/`` are stale until updated.
