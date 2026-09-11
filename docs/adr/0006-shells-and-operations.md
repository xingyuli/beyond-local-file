# Shells require the daemon; three stop-syncing operations

If the daemon is not running, shells fail and tell the user to start it. There is no offline copy engine and no auto-start. `link check` is a daemon query, same as the other shells.

Stop-syncing a path is three daemon operations, not one:

- `remove` deletes the hub copy and every projection, and drops the subpath.
- `restore` deletes the hub copy, leaves the file in the requesting target project, leaves other targets' copies as unmanaged files, and drops the subpath.
- External item-remove (reload commit) keeps the hub, confirms in the reload shell, and deletes target copies only.

Reload is plan → prompt on removals → commit. Path changes are create/update/delete. Mapping changes are item-add/item-remove/target-add/target-remove/project-add/project-remove. Trigger hooks attach to these types later.

## Status

accepted
