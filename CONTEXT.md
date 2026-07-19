# beyond-local-file

A tool for projecting shared files from a single authoritative directory into many target project directories, using symlinks or physical copies.

## Language

**Managed project**:
The authoritative directory whose contents are projected into target projects. Its contents are never modified by the tool.
_Avoid_: Source project, host project, origin

**Target project**:
A directory that receives projected items from a managed project. The user works inside target projects day-to-day.
_Avoid_: Destination project, consumer project

**Item**:
A single file or directory inside a managed project that is projected into one or more target projects.
_Avoid_: File, resource, artifact

**Mapping**:
A declared relationship between a managed project and one or more target projects, with optional rules governing which items are projected and how.
_Avoid_: Configuration entry, rule, link definition

**Projection**:
The act of making an item from a managed project visible inside a target project, either as a symlink or a physical copy.
_Avoid_: Sync, deploy, copy, link

**Link strategy**:
The mechanism used for a projection: symlink (the target sees a pointer to the managed item) or copy (the target receives an independent physical file).
_Avoid_: Mode, type, method

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
The reverse adoption workflow: moving a file that already exists in a target project into the managed project and replacing the original with a symlink. The inverse dissolves the symlink and restores the file to the target.
_Avoid_: Adopt, import, reverse sync

**Git exclude**:
An entry in a target project's `.git/info/exclude` that prevents Git from tracking a projected item. The tool maintains these entries automatically alongside projections.
_Avoid_: Gitignore entry, ignore rule
