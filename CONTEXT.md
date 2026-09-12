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

**Daemon**:
The sole runtime for projecting, catching up, and applying mapping changes. It observes each managed project and its target projects, queues typed changes, writes the hub, fans out (excluding the source replica), and is the only writer of mappings that originate from blf commands.
_Avoid_: Coordinator, watcher, syncer, service

**Shell**:
A blf command that sends a request to the daemon. It does not copy, delete, or write mappings itself.
_Avoid_: Client, wrapper, frontend

**Mapping snapshot**:
The daemon's last committed mappings, persisted on disk so a crash still has a before-state. Start and reload diff the config file against it to see external mapping edits.
_Avoid_: Cache, checkpoint, in-memory config

**Baseline**:
The last recorded hashes and presence for each path on a managed project and its target projects, written after a successful apply or a completed catch-up. No baseline means that managed project has never completed a catch-up.
_Avoid_: Checkpoint, watermark, sync-state

**Fresh catch-up**:
Daemon start with no baseline: every projection is made to match the managed project, then observation begins.
_Avoid_: Reset, initial sync, first sync

**Update catch-up**:
Daemon start (or reload) with a baseline: only paths that differ from the baseline are queued, then observation begins. This is the downtime window, not a reset.
_Avoid_: Resync, full sync, recover

**Reload**:
Classify external mapping edits by diffing the config file against the mapping snapshot, then commit. Removals are confirmed as one plan, coarsest first (project-remove, then target-remove, then item-remove, with inner diffs subsumed); adds apply automatically after. `daemon start` runs this in the foreground when the file differs from the snapshot, then backgrounds; `daemon reload` runs it when the daemon is already up. Decline (or no TTY when removals exist) commits nothing. The daemon does not watch config files. Internal mapping edits do not go through reload.
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
Bytes kept under `.blf-held/` in the managed project so a live path can change without losing the previous file. That directory is reserved: it is not an item and is never projected. Each held copy has a **hold reason**. `status` lists held copies; `start` and `reload` warn and ack. There is no restore/discard command in 0.5.0.
_Avoid_: Quarantine, trash, stash, lost+found, stale removal

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
The relationship between a managed item and its physical copy in a target project, as determined by comparing current file hashes against a stored baseline: in-sync, managed-changed, target-changed, both-changed, or manually-synced.
_Avoid_: Diff, state, status

**Item discovery**:
The process of determining which items a managed project contributes to a given mapping — either by enumerating the managed project directory (sync-all) or by resolving each declared subpath against the filesystem. A distinct concern from mapping expansion.
_Avoid_: File scanning, directory walk, item loading

**Mapping expansion**:
The pure structural transformation that converts a config with M mappings and N total targets into a flat list of execution units. Independent of the filesystem — concerns only the shape of the config.
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
