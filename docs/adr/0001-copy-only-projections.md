# Copy-only projections

Kiro-class tools deny workspace paths that resolve outside the project via symlink, and a mixed symlink/copy mode kept the broken default in place. 0.5.0 is a breaking release: every projection is a physical copy, `copy: true` is rejected as an unsupported option, and `link` stays as the abstraction over that mechanism.

Existing mappings whose target path is a symlink to the correct managed item are converted to copies when the daemon starts. `revlink create` copies into the managed project and leaves the target file in place; restore unregisters and also leaves it. `link sync` is removed: a live daemon replaces manual sync.

## Status

accepted

## Considered Options

- Keep symlink as the default, copy as opt-in (0.4.0). Rejected: the default path is exactly what Kiro refuses, and file-only copy cannot cover directory items.
- Copy as the new default, symlink retained as an explicit opt-in. Rejected: mixing two mechanisms in one release still leaves a symlink footgun (`revlink` would recreate workspace-escape).
- Copy only. Accepted.

## Consequences

- Live sharing is gone: each target project holds its own tree; edits propagate through the daemon.
- Directory copy is required; file-only copy cannot be the only projection.
- Windows Developer Mode is no longer required for the projection itself.
- `blf upgrade` remains a package updater, not a workspace migrator.
