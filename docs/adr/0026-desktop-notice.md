# Desktop notice is display-only; status opens the resolve UI

Isolation during idle observe is silent unless you run `status`. A **desktop notice** is the daemon’s OS banner the first time this process persists a new out-of-sync mark or held copy. It names the kind, the **managed project**, and the path (or a count). It does not open a URL: there is no app bundle identity to attach a click, and `blf daemon status` is already the door to the resolve UI. Restart and reload of leftover rows stay silent. Coalesce inside one worker-unit persist (one out-of-sync toast and one held toast; a single fact uses `{rel} in {managed-project}`, several use `{n} paths in {managed-project}`). Skip a toast when the isolation was caused by the current TTY shell. Default on; `BLF_NOTIFY=0` opts out. Best-effort: a refused OS permission must not fail persist.

The daemon talks to the OS only through `desktop-notifier`. This repo does not call `osascript`, PowerShell, WinRT, or `notify-send`. Platform bridges (`rubicon-objc`, WinRT, `dbus-fast`) stay transitive extras of that library, selected by environment markers.

## Status

accepted

## Considered Options

- Click opens the resolve UI URL. Rejected: a Python daemon is not a signed `.app`; macOS click needs a bundle identity this project will not ship.
- Stdlib/subprocess backends (`osascript` / PowerShell / `notify-send`). Rejected: one dependency and no platform branches in this tree, unless `desktop-notifier` cannot send on a given OS.
- `desktop-notifier` click callbacks and a CFRunLoop. Rejected: display-only; send does not need an event loop.
- Toast leftover isolation at `ready`. Rejected: `status` and reload already list those rows.
- Single-fact body `{rel} on {replica-name}` (last path component). Rejected: a replica directory and a managed project often share a basename; the notice would not tell them apart. Status lists replicas. The banner always names the managed project, which is how `status` and the resolve UI group rows.

## Consequences

0024’s “later notification may open the same URLs” does not hold. The out-of-sync reason clause stays off the banner (too technical); it remains on `status` and, for held copies, as visible resolve-UI text. Out-of-sync clauses in the resolve UI are tooltip-only until a later ticket. `docs/cli-reference.md` and the dependency list move with the code that makes this true.
