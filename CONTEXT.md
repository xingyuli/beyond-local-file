# beyond-local-file

A tool for projecting shared files from a single managed directory into many target project directories as physical copies.

## Language

**Managed project**:
The directory that holds items projected into target projects. The tool may write it when adopting an item or when applying a change observed in a target project.
_Avoid_: Source project, host project, origin

**Target project**:
A directory that receives projected items from a managed project. The user works inside target projects day-to-day.
_Avoid_: Destination project, consumer project

**Item**:
A single file or directory inside a managed project that is projected into one or more target projects.
_Avoid_: File, resource, artifact

**Mapping**:
A declared relationship between a managed project and one or more target projects, with optional subpaths governing which items are projected. Several managed projects may contribute to one target when their items do not overlap.
_Avoid_: Configuration entry, rule, link definition

**Link**:
The abstraction that makes a managed item visible in a target project. A link is always realized as a physical copy at the projection path; that path is not a symlink to the hub. Nested symlink nodes inside a directory item are copied as symlinks (venv interpreters, relative ``python`` → ``python3.14``).
_Avoid_: Shortcut, alias, strategy

**Projection**:
The physical copy of a managed item that lives inside a target project.
_Avoid_: Sync, deploy, copy

**Configuration set**:
The mapping yaml files one daemon process loads. The **global set** is the list in ``~/.blf/config``. ``-c PATH`` is a **singleton set** identified by that file's resolved path. With neither, ``config.yml`` in the current directory is a singleton set.
_Avoid_: .blfrc, profile, config file (that name is the mapping yaml)

**Global config**:
``~/.blf/config`` — a pointer list of mapping yaml paths (the former ``~/.blfrc`` ``config_file`` list). It is not itself a mapping document.
_Avoid_: .blfrc

**Mapping file**:
A yaml document of managed-project mappings (typically ``config.yml``). Several mapping files may belong to one configuration set.
_Avoid_: global config, .blfrc

**Runtime home**:
``~/.blf/`` — daemon process state and held copies. Mapping files stay where the user keeps them. Resolution order for which set to load: ``-c`` / ``--config``, else the global config, else ``config.yml`` in CWD.
_Avoid_: hub-local .blf, state beside config.yml

**Set run directory**:
``~/.blf/run/global/`` for the global set; ``~/.blf/run/file-<sha256 of the resolved mapping yaml>/`` for a singleton set. Pid, port, log, mapping snapshot, and item-document baseline live here.
_Avoid_: .blf next to config.yml

**Daemon**:
One OS process per configuration set. It catch-up's, then observes each managed project and target in that set, queues typed changes, writes the hub, fans out (excluding the source replica), and is the only writer of mappings that originate from blf commands. Two sets never watch the same mapping file at once.
_Avoid_: Coordinator, watcher, syncer, service, one process per mapping file

**Worker unit**:
The threading grain: one queue for **one managed project** (hub and every target). Idle observe, mailbox apply, catch-up, and mutating shells for that hub run as jobs on that queue. At most one job per worker unit. Distinct worker units run in parallel.
_Avoid_: Processing unit, thread per target, set-wide lock

**Mapping unit**:
The expanded **managed project × one target** with that mapping's items. Check rows, git exclude, and fan-out destinations. Not its own thread. A ConfigProject with M mappings and N total targets becomes M×N mapping units.
_Avoid_: Processing unit, worker unit, execution thread

**Daemon phase**:
``catch-up`` or ``ready``. The process accepts IPC in both phases. Live observation starts only in ``ready``. ``daemon start`` stays in the foreground until ``ready``. ``status`` always includes the pid. Other shells wait through ``catch-up``.
_Avoid_: starting, booting, warming

**Shell**:
A blf command that sends a request to the daemon. It does not copy, delete, or write mappings itself.
_Avoid_: Client, wrapper, frontend

**Mapping snapshot**:
The daemon's last committed mappings for its configuration set, persisted in the set run directory so a crash still has a before-state. Start and reload diff the set's mapping files against it to see external mapping edits.
_Avoid_: Cache, checkpoint, in-memory config

**Baseline**:
The last recorded hashes and presence for each path on a managed project and its target projects, written after a successful apply or a completed catch-up. Persisted as item documents under ``baseline/<managed-project>/`` in the set run directory: ``files`` holds FILE items (hub and each target in the same document); a DIRECTORY item is nested ``files`` plus one document per child subtree (as a file; ``<child>/files`` when a nested declared item needs that path as a directory). A mutating shell rewrites only documents covering paths it changed. No baseline means that managed project has never completed a catch-up. A leftover ``baseline.yml`` is read until a successful document write unlinks it (a partial ``baseline/`` tree does not shadow yaml). After a write, the worker reuses the in-memory trees and does not re-parse documents on the next persist.
_Avoid_: Checkpoint, watermark, sync-state

**Fresh catch-up**:
Daemon start with no baseline in the set run directory: every projection is made to match the managed project. IPC is already up (phase ``catch-up``); live observation begins at phase ``ready``.
_Avoid_: Reset, initial sync, first sync

**Update catch-up**:
Daemon start (or reload) with a baseline: only paths that differ from the baseline are queued. IPC is already up; live observation begins at phase ``ready``. Not a reset.
_Avoid_: Resync, full sync, recover

**Reload**:
Classify external mapping edits by diffing the configuration set's mapping files against the mapping snapshot, then commit. Removals are confirmed as one plan, coarsest first (project-remove, then target-remove, then item-remove, with inner diffs subsumed); adds apply automatically after. `daemon start` classifies in the foreground when the files differ from the snapshot, then catch-up's (IPC is already up) until phase ``ready``; `daemon reload` runs it when the daemon is already ``ready``. Decline (or no TTY when removals exist) commits nothing. The daemon does not watch mapping files. Internal mapping edits do not go through reload.
_Avoid_: Hot reload, config watch, live config

**Path change**:
A typed unit of work on a path under an item: create, update, or delete.
_Avoid_: Event, delta, mutation

**Mailbox**:
At most one not-yet-applied path change per (path, replica). A later event from the same replica replaces the pending change. Two replicas dirty on the same path are not merged.
_Avoid_: Debounce, batch, buffer, timeout

**Fan-out**:
After a successful hub apply, copy or delete that generation onto every in-sync replica of the owning managed project except the source replica — the tree the change was observed on. The source already has the bytes. Replicas of other managed projects are not written, even when they use the same item name.
_Avoid_: Broadcast, replicate, push, echo

**Generation**:
A per-path counter on the hub, incremented once per successful hub apply. A delete wins on the live path if the hub generation is at most 3 ahead of the replica's base.
_Avoid_: Version, clock, timestamp

**Held copy**:
Bytes kept under ``~/.blf/held/<sha256 of the managed project path>/`` so a live path can change without losing the previous file. That tree is not an item and is never projected. Each held copy has a **hold reason**. `status` lists held copies; `start` and `reload` warn and ack. There is no restore/discard command in 0.5.0. A leftover ``.blf-held/`` inside a managed project is still skipped by discovery; new holds are not written there.
_Avoid_: Quarantine, trash, stash, lost+found, stale removal, hub-local .blf-held

**Hold reason**:
A stable clause naming why a held copy exists. WARNINGs and the later resolve UI show it. 0.5.0 reasons: `create-overwrite` (item-add fan-out replaced different bytes on a replica), `delete-gap` (delete won past the generation window).
_Avoid_: Conflict type, error code, note

**Out-of-sync**:
A replica is excluded from a path after its update lost compare-and-swap (hub generation/hash no longer matches its base). Fan-out of that path skips it. Further path changes from it are discarded. The live path on the hub and on in-sync replicas keeps moving. Cleared when that replica's bytes match the hub again. `status` lists these; `start` and `reload` warn and ack.
_Avoid_: Freeze, conflict, diverge, partition

**Mapping change**:
A typed unit of work on mappings: item-add, item-remove, target-add, target-remove, project-add, or project-remove.
_Avoid_: Config diff, reload delta

**Subpath**:
An item declared explicitly in a mapping for selective projection. When no subpaths are declared, all top-level items in the managed project are projected.
_Avoid_: Filter, include, path entry

**Sync status**:
Whether a managed item and its projection match **right now** (live hashes). Match is in-sync. Mismatch is labeled from the baseline when one exists (managed-changed, target-changed, both-changed). There is no ``sync-state.yml`` and no manually-synced book from ``link sync``.
_Avoid_: Diff, state, status, sync-state

**Item discovery**:
The process of determining which items a managed project contributes to a given mapping — either by enumerating the managed project directory (sync-all) or by resolving each declared subpath against the filesystem. A distinct concern from mapping expansion.
_Avoid_: File scanning, directory walk, item loading

**Mapping expansion**:
The pure structural transformation that converts a config with M mappings and N total targets into a flat list of mapping units. Independent of the filesystem — concerns only the shape of the config.
_Avoid_: Translation, flattening, config parsing

**Revlink**:
The reverse adoption workflow: copy an item that already exists in a target project into the managed project, leave the target path as a real file, and register it as a projection. The inverse unregisters the item and leaves the target file in place. Restore and remove resolve the hub from PATH's contribution source when several managed projects target the working directory. Create of a new item there interviews in the shell for a hub; an already-covered path uses that owner without a prompt.
_Avoid_: Adopt, import, reverse sync

**Git exclude**:
An entry in a target project's `.git/info/exclude` that prevents Git from tracking a projected item. The tool maintains these entries automatically alongside projections.
_Avoid_: Gitignore entry, ignore rule

**Contribution source**:
The managed project that owns an item on a target. Derived at runtime from committed mappings after item discovery. Not persisted. A target path belongs to the unique item whose name equals that path or is a prefix of it; that item belongs to one managed project. Restore and remove use that owner. Create uses it to skip the hub interview when PATH is already an item.
_Avoid_: Overlay owner, source index, persisted owner

**Item overlap**:
Two items on the same target whose names are equal or one is a path prefix of the other (``local-file`` and ``local-file/devops/k8s.md``). Illegal across managed projects and within one project's subpaths. Start and reload fail and name both projects and both paths. Distinct siblings on one target (``.vscode`` and ``.kiro/hooks``) are allowed.
_Avoid_: Collision, conflict, duplicate mapping

## Runtime

One daemon process loads one configuration set. Process state lives in the runtime home, not next to mapping files or inside managed projects.

A yaml file already loaded by a running set is served by that process (``-c`` is not a second watcher). Starting a set that shares a mapping file with another running set is an error.

``link check`` hashes managed vs target now. A check with no project name is a job on every worker unit; the table is the merge. With a project name, that one unit. Progress is one rewritten TTY status line (mapping unit ``i/n``, current item name, no per-file paths), filled as worker units finish mapping units. The table is printed once at the end. Non-TTY: no status line, final table only.

The set's ``daemon.log`` records each served shell request (op, PATH, cwd, start, end, exit), mutating-op steps with durations, and observe/persist work (live tick / item scan, baseline record, snapshot and item-document write) with duration and size context. Request stdout captured for the CLI is not a substitute. See 0015, 0020, and 0021.

The accept thread binds the port and answers ``status``. It does not hash. Each worker unit has its own thread: idle observe of **that** unit's trees (15 s from the end of that unit's last idle observe, units staggered) and mutating shells routed by mapping snapshot / contribution source. A mutating shell applies the mailbox (no scan) then the op; it does not start an observe. Mutating TTY: ``Waiting …`` if that worker unit is busy, then the op, then ``Writing baseline …``. Non-TTY: no status line, result at the end. After persist, live observation continues from the new baseline without a reload scan. ``daemon reload`` catch-up jobs run only for worker units whose mappings changed. Two worker units splicing the same mapping yaml or ``.git/info/exclude`` take a lock per file so both writes survive.
