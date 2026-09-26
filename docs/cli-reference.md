# CLI Reference

Complete command-line interface reference for `beyond-local-file` (aliased as `blf`).

---

## Command Structure

```bash
blf [GLOBAL_OPTIONS] COMMAND [COMMAND_OPTIONS] [ARGUMENTS]
```

The daemon is the runtime. `link check`, `revlink create` / `restore`, and `remove` are shells: they send a request and fail if the daemon is down.

```
Error: daemon is not running. Start it with: blf daemon start
```

There is no `link sync`.

---

## Global Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `-c, --config PATH` | Path | — | Mapping yaml for a **singleton set**. See [Configuration set](#configuration-set). |
| `--version` | Flag | - | Show the installed version and exit |
| `--help` | Flag | - | Show help message and exit |

**Examples:**
```bash
blf --help
blf --version
blf -c custom.yml daemon start
blf --config /path/to/config.yml link check
```

---

## Commands

### `daemon` — Runtime

One OS process per **configuration set**. It catch-up's copy projections, observes the hub and replicas in that set, and is the only writer of mappings that originate from blf commands. Two sets never watch the same mapping file at once.

```bash
blf daemon SUBCOMMAND
```

**Subcommands:**
- `start` — Start the daemon; stays in the foreground until phase `ready`
- `stop` — Stop the running daemon
- `status` — Show pid and phase, plus out-of-sync paths and held copies
- `logs` — Retired. Use `blf logs`
- `reload` — Apply external mapping edits from the set's mapping files

---

## `daemon start` — Start the Runtime

Spawn the worker, ingest mapping edits if needed, catch-up in the foreground until phase `ready`, then return. The worker keeps running in the background.

### Syntax

```bash
blf daemon start
```

### Behavior

1. Resolves the configuration set (`--config` → `~/.blf/config` → CWD `config.yml`).
2. Fails if a daemon is already running for that set.
3. Fails if a mapping file in the set is already loaded by another running set, naming the owner.
4. First start deletes leftover hub-local `.blf/` next to each mapping file and prints each removed path (skips `~/.blf` itself).
5. If the set's mapping files differ from the mapping snapshot, classifies the diff in the foreground (same as `reload`): removals print one plan and require confirmation; adds apply after. On a terminal that confirm is asked on the shell screen before the daemon is spawned. Decline (or no TTY when removals exist) starts nothing.
6. Fails if two items on one target overlap (names equal, or one a path prefix of the other), naming both projects and both paths. Same rule inside one project's subpaths.
7. Warns about out-of-sync paths and held copies and asks you to continue. On a terminal that question is asked on the shell screen before the daemon is spawned, one at a time after a removal confirm if both apply.
8. Binds IPC, then catch-up. `daemon start` stays in the foreground until phase `ready`. On a terminal it opens a shell screen through catch-up and leaves it up when the daemon is ready. The header names `daemon start` and all projects. One row per managed project being caught up: state (`waiting`, `working`, `done`, or `failed`), the current item, and elapsed time. The header, the rows, and the hint stay put. When the daemon is ready, the output is `Daemon started (pid …)`. Closing the screen restores the terminal and prints that same line. Without a terminal there is no screen and no status line. Live observation starts only in `ready`.

   Before the daemon is spawned, a question uses `Enter: answer` and `Ctrl+C: cancel`. Ctrl+C closes the screen and starts nothing. While catch-up runs: `Ctrl+C: stop`. That prints `Stop this command?`. Stop question: `Enter: answer`, `Ctrl+C: confirm stop`, `Esc: continue`. After the daemon is ready: `q: close` and `Ctrl+C: close`. Closing does not ask for confirmation.
9. Catch-up: with no baseline, every projection is made to match the managed project (fresh catch-up). With a baseline, only paths that differ are queued (update catch-up). Leftover blf symlinks to the correct managed item become copies. Nested symlink nodes inside a directory item are copied as symlinks.

### Examples

```bash
# Start from the managed-files directory
blf daemon start

# Singleton set (global option)
blf -c custom.yml daemon start
```

### Output

On a terminal, the shell screen stays up until you close it, then:

```
Daemon started (pid 12345)
```

Without a terminal, that line is printed with no screen.

If a mapping file is already loaded by another running set:

```
Error: mapping file /Users/username/company/config.yml is already loaded by the running global set (pid 12345)
```

If mapping removals need confirmation, the plan and `Apply these mapping removals?` are lines on the shell screen. Answer `y` or `n`. Anything else prints one line and the question stays open. Decline prints `Mapping changes were not applied` and does not start the daemon. Without a terminal, removals are not applied.

Overlapping items:

```
Error: overlapping items on /Users/username/workspace/project: proj-a 'local-file' and proj-b 'local-file/devops/k8s.md'
```

---

## `daemon stop` — Stop the Runtime

Stop the running daemon for the resolved configuration set.

### Syntax

```bash
blf daemon stop
```

### Output

```
Daemon stopped
```

If nothing is running:

```
Daemon is not running
```

---

## `daemon status` — Runtime Status

Show whether the daemon is running (pid and phase), plus out-of-sync paths and held copies.

### Syntax

```bash
blf daemon status
```

### Terminal

On a terminal, a running daemon opens a shell screen and leaves it up until you close it. The header is pid and phase. There are no worker-unit rows. The output is the status text, then out-of-sync paths and held copies when those exist. After it finishes: `q: close` and `Ctrl+C: close`. When isolation exists and the daemon is ready, the hint is `o: open  q: close  Ctrl+C: close`. `o` opens the resolve UI in the default browser and leaves the screen up. Closing restores the terminal and prints that same text.

The ready daemon owns a second localhost HTTP port for the resolve UI (`127.0.0.1` only), authenticated by a token in the set run directory. JSON IPC stays on `daemon.port`. If the daemon is not running, status prints `Daemon is not running` and does not open a screen. Without a terminal, status prints the same text and does not wait for a key. When isolation exists, non-TTY status also prints the resolve UI URL and does not open a browser.

### Output

```
Daemon is running (pid 12345, phase ready)
```

During catch-up the phase is `catch-up`. The pid is always present while the process is up.

or

```
Daemon is not running
```

When isolation state exists:

```
Out-of-sync:
  /Users/username/workspace/project-b  notes.md
  update lost compare-and-swap at notes.md on /Users/username/workspace/project-b; hub generation 1 from /Users/username/workspace/project-a (reason: stale-base)
Held copies:
  delete applied past the generation window; kept hub bytes of notes.md (reason: delete-gap)
Held at /Users/username/.blf/held/<sha256>/...
http://127.0.0.1:12345/?token=...
```

The resolve UI is index plus detail at that URL. Query parameters `project` and `path` select a detail row; every link keeps the token. A GET with no `project`/`path` (or an unknown one) redirects to the first out-of-sync row, or the first held row when none is out-of-sync — landing is indistinguishable from clicking that row yourself. The left nav is grouped by managed project name, one row per managed project and relative path. A control at the top of the nav collapses it (Cmd+B on macOS, Ctrl+B otherwise) so the merge panes can use the width; the collapsed state is kept for the tab. Out-of-sync and held are top tab panes (a path in both categories appears in both panes), not a badge repeated on every row — the tab switcher itself is left out when only one category has anything in it. The open row is marked by a background highlight, not text, and that highlight is recomputed from the URL on every render, so it survives tab switches and page reloads. Leaving a path mid-merge (including re-selecting the same one, which reloads the page the same way) is confirmed first whenever there is at least one unsubmitted merged round.

Out-of-sync detail merges replicas one at a time, IntelliJ-merge style (ADR 0025). A single toolbar row above the stage holds the common leading path segments collapsed to one label, every target of that managed project that has the item as a small two-line chip (label, then status — not a wide "label STATUS" line, and not a left-hand column: a 4th or 5th vertical column alongside the nav and the diff panes left too little width for any of them, and a lone `submit` button previously wasted a whole row by itself), and `submit`, all sharing that one row. A hold-reason clause, if any, is in the chip's tooltip. Each chip is `same as hub` (green, not opened — the live bytes already match), `merged` (already folded into the result), `current` (the one being merged now), or `pending` (not reached yet). The stage starts on the first replica that differs from hub: a `CodeMirror` merge view with hub-now on the left, an editable result in the middle (seeded from hub-now), and that replica-now on the right — line numbers, colored diff regions, connecting curves, collapsed unchanged stretches, and click-to-take arrows between panes are how you pull a changed region into the result, alongside manual edits. Chunk arrows read "accept this chunk" (CodeMirror's default "revert chunk" wording is overridden — nothing is being undone). Clicking `mark as merged` freezes the result as the new left side and advances to the next differing replica, now labeled `current` instead of `hub-now` since it carries the accumulated result rather than hub bytes. A binary path skips the diff editor (bytes cannot be merged): each round is a `keep current` / `take this replica` choice between hash-and-size cards, and the winner becomes the new current pick. Once every differing replica is merged, the stage shows a read-only review of the final result (or the winning hash/size for a binary path) so there is something to check before `submit` sends the confirmed result to the daemon; before that, closing the page or leaving the path writes nothing. There is no project/path title in the toolbar — the highlighted nav row already says which path is open. `merge.py`'s ancestor-stash-aware hunks, `accept ancestor`, and `next`/`prev` conflict from the earlier design are gone — see ADR 0025. CodeMirror, its `merge` addon, and `diff_match_patch` are vendored static files served by the daemon at `/static/vendor/`; the resolve UI's own script and stylesheet are served at `/static/app.js` and `/static/app.css`. No CDN, no build step.

0.5.0 has no restore/discard shells for held copies. `start` and `reload` warn and continue.

---

## `blf logs` — Follow the Logs

Follow the set's logs until interrupted. Ctrl-C stops following, not the daemon.

The set run directory holds three files (`~/.blf/run/global/logs/` or `~/.blf/run/file-<sha256>/logs/`):

- `idle.log` — idle ticks, and when a tick applies, the apply, held-copy, and baseline persist lines that follow. A tick under 100ms that finds nothing is omitted. Every line names its worker unit.
- `requests.log` — each shell request and every step of the work that request caused, including a reload's catch-up. Every line names its worker unit.
- `daemon.log` — process start, the catch-up that belongs to start, ready, stop, and a failure that is neither an idle tick nor a shell request.

`blf logs` merges the three files by their write-time stamp. Each printed line is prefixed with `[daemon]`, `[idle]`, or `[requests]`. On a terminal each name has a stable color. A pipe keeps the prefix and drops the color.

`blf logs requests`, `blf logs idle`, and `blf logs daemon` follow that one file and print the stored lines with no prefix.

Each new line is stamped at write time with the daemon host's local timezone, offset, and milliseconds:

```
2026-09-21T18:55:09.184+08:00 daemon ready
```

A merged follow of a shell request:

```
[requests] 2026-09-21T18:55:09.184+08:00 request: start op=create path=notes.md cwd=/Users/me/project unit=notes queue_ms=2 op_ms=0 persist_ms=0
[requests] 2026-09-21T18:55:09.190+08:00 create: copy duration_ms=1 unit=notes
[requests] 2026-09-21T18:55:09.210+08:00 request: done op=create path=notes.md cwd=/Users/me/project unit=notes queue_ms=2 op_ms=11 persist_ms=14 exit=0
```

`request: start` and `request: done` carry `queue_ms`, `op_ms`, and `persist_ms` (`persist_ms` is absent on a dry-run). For one worker unit, those three times are the wall. A check or reload on several worker units lists each unit's duration. Request stdout captured for the CLI is not written here.

`blf daemon logs` is retired. It prints a line naming `blf logs` and does not follow a file.

### Syntax

```bash
blf logs
blf logs requests
blf logs idle
blf logs daemon
```

If the requested log is missing:

```
Daemon log not found
```

---

## `daemon reload` — Apply Mapping Edits

Classify external mapping edits by diffing the configuration set's mapping files against the mapping snapshot, then commit them in the running daemon.

### Syntax

```bash
blf daemon reload
```

### Behavior

1. Fails if the daemon is not running.
2. Fails if two items on one target overlap (names equal, or one a path prefix of the other), naming both projects and both paths.
3. If the file already matches the snapshot: `Mappings already match the snapshot`.
4. Removals print one plan (project-remove, then target-remove, then item-remove, inner diffs subsumed) and require confirmation. Adds apply automatically after. On a terminal that confirm is asked on the shell screen before the request is sent.
5. Decline commits nothing. No TTY when removals exist also commits nothing.
6. Warns about out-of-sync paths and held copies and asks you to continue. On a terminal that question is asked on the shell screen before the request is sent, one at a time after a removal confirm if both apply. A held-copy ack with no mapping change still opens the screen, then finishes with `Mappings already match the snapshot`.

The daemon does not watch mapping files. Internal mapping edits from `revlink` / `remove` do not go through reload.

#### Terminal

On a terminal, a reload that sends a request to the daemon opens a shell screen and leaves it up until you close it. The header names `daemon reload` and that managed project, or all projects when more than one worker unit's mappings changed. One row per worker unit whose mappings changed: state (`waiting`, `working`, `done`, or `failed`), the current item, and elapsed time. The header, the rows, and the hint stay put. Closing the screen restores the terminal and prints reload's result.

Before a request is sent, a question uses `Enter: answer` and `Ctrl+C: cancel`. Ctrl+C closes the screen and sends nothing. While the request runs: `Ctrl+C: stop`. That prints `Stop this command?`. Stop question: `Enter: answer`, `Ctrl+C: confirm stop`, `Esc: continue`. After the reload finishes: `q: close` and `Ctrl+C: close`. Closing does not ask for confirmation.

A reload that never reaches the daemon and has no question stays plain text and does not open a screen. That includes `Mappings already match the snapshot` with no isolation warning, and a daemon that is not running. A declined removal confirm is asked on the screen and then prints `Mapping changes were not applied`.

Without a terminal, reload prints its result only and does not wait for a key.

### Examples

```bash
# After editing a mapping file by hand
blf daemon reload
```

---

### `remove` — Permanently Remove a Managed Item

Permanently remove one managed item from the current target project and every validated projection.

#### Syntax

```bash
blf remove [OPTIONS] PATH
```

#### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `PATH` | Yes | Path to the managed file or directory to remove; it must be inside the current working directory. |

#### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--dry-run` | Flag | Off | Preview validation and cleanup without modifying files, Git excludes, or configuration. |

#### Behavior

Requires a running daemon. Run it inside the target.

1. Resolves the hub from PATH (contribution source): the unique item whose name equals PATH or is a prefix of it, and that item's managed project. Several managed projects targeting CWD is not CWD-level ambiguity.
2. Normalizes `PATH` and rejects paths outside the current working directory.
3. Preflights every configured projection that manages the exact item. A copy must match the managed item; a leftover blf symlink must still point at the managed copy.
4. Deletes every validated projection, removes its matching `.git/info/exclude` entry when applicable, then deletes the managed copy.
5. Removes the item from participating selective `subpath` lists in the configuration. See the [Configuration Reference](configuration-reference.md) for mapping syntax.

If any projection fails preflight validation, the command leaves all managed items and projections unchanged. If cleanup fails after preflight, it reports the recovery state and retains later destructive phases when possible.

#### Terminal

On a terminal, `remove` opens a shell screen and leaves it up until you close it, including a fast removal. The header names `remove` and PATH. One row shows this request's worker unit: managed project, state (`waiting`, `working`, `done`, or `failed`), the current step, and elapsed time. The header, the row, and the hint stay put. When the command finishes, the transcript fills the output (`Removed …`, `Deleted managed copy: …`, and the rest, or the error text).

The input line is hidden except while a question is open. It sits directly above the hint.

- While the request runs: `Ctrl+C: stop`. That prints `Stop this command?` and shows the input.
- Stop question: `Enter: answer`, `Ctrl+C: confirm stop`, `Esc: continue`. `y` stops the command. `n` continues. Anything else prints one line and the question stays open. A second Ctrl+C stops. Esc continues.
- After the command finishes: `q: close` and `Ctrl+C: close`. Closing does not ask for confirmation.

Closing the screen restores the terminal and prints that same transcript. Without a terminal, `remove` prints the transcript and exits with the command's exit code. It does not draw a screen or wait for a key.

#### Examples

```bash
# Permanently remove a managed file from the current target project
blf remove .vscode/settings.json

# Preview the validation and cleanup actions
blf remove --dry-run .vscode/settings.json

# Singleton set
blf --config ~/my-dev-files/config.yml remove .vscode/settings.json
```

#### Error Cases

| Condition | Message |
|-----------|---------|
| PATH is not a managed item | `'{path}' is not a managed item` |
| No managed project targets CWD | `No managed project found for current directory: <cwd>` |
| Daemon is down | `Error: daemon is not running. Start it with: blf daemon start` |

### `link` — Link Management

`link` is the metaphor for a managed item that is visible in a target project. A link is always a physical copy.

```bash
blf link SUBCOMMAND [OPTIONS] [ARGUMENTS]
```

**Subcommands:**
- `check` — Verify copy projections and Git excludes

---

## `link check` — Verify Status

Check the status of copy projections and Git exclude entries for each project and target location. This is a daemon query: it hashes managed vs target **now**. Match is in-sync. Mismatch is labeled from the baseline when one exists (managed-changed / target-changed / both-changed). There is no `sync-state.yml`.

If the process is in phase `catch-up`, check waits until `ready` rather than failing.

On a terminal, `link check` opens a shell screen and leaves it up until you close it. The header names `link check` and the project, or all projects when no project is given. One row per worker unit that request uses: managed project, state (`waiting`, `working`, `done`, or `failed`), the current item, and elapsed time. Rows fill in as units finish. The header, the rows, and the hint stay put. The output scrolls. When the check finishes, the plain table fills the output. `--format verbose` stays line-oriented in that output. Closing the screen restores the terminal and prints that same result.

While the check runs: `Ctrl+C: stop`. That prints `Stop this command?`. Stop question: `Enter: answer`, `Ctrl+C: confirm stop`, `Esc: continue`. After the check finishes: `q: close` and `Ctrl+C: close`. Closing does not ask for confirmation.

Without a terminal, `link check` prints the table only and does not wait for a key.

### Syntax

```bash
blf link check [PROJECT_NAME] [OPTIONS]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `PROJECT_NAME` | No | Check only this project; omit to check all projects |

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--extra-exclude` | Flag | Off | Show extra entries in `.git/info/exclude` |
| `--format FORMAT` | Choice | `table` | Output format: `table` or `verbose` |

### Output Formats

#### Table Format (Default)

Compact Rich table showing status for all projects and targets. The table is printed once at the end; it does not show `i/n` progress.

```bash
blf link check
```

**Output:**
```
┌─────────────┬─────────┬─────────┬──────────────────────────────────┐
│ Project     │ Exclude │ Copy    │ Target Path                      │
├─────────────┼─────────┼─────────┼──────────────────────────────────┤
│ project-a   │ ✓       │ ✓       │ /Users/user/workspace/project-a  │
│ project-b   │ ✓ (+1)  │ ✓       │ /Users/user/workspace/project-b  │
│ project-c   │ ✓       │ ✗ (1)   │ /Users/user/workspace/project-c  │
└─────────────┴─────────┴─────────┴──────────────────────────────────┘
```

A Symlink column appears only when leftover blf symlinks are still present (they become copies on daemon catch-up).

**Status indicators:**
- `✓` — All items correct
- `✓ (+N)` — All correct, N extra exclude entries
- `⚠ (N incorrect)` — N items exist but are not the expected copy (or leftover symlink points to the wrong source)
- `✗ (N missing)` — N items missing
- `✗ (N missing, M incorrect)` — N items missing and M items incorrect

#### Table Format with Extra Excludes

```bash
blf link check --extra-exclude
```

**Output:**
```
┌─────────────┬─────────┬─────────┬──────────────────────────────────┐
│ Project     │ Exclude │ Copy    │ Target Path                      │
├─────────────┼─────────┼─────────┼──────────────────────────────────┤
│ project-a   │ ✓       │ ✓       │ /Users/user/workspace/project-a  │
│ project-b   │ ✓ (+1)  │ ✓       │ /Users/user/workspace/project-b  │
└─────────────┴─────────┴─────────┴──────────────────────────────────┘

Extra exclude entries:
  project-b: old-file.txt
```

#### Verbose Format

Detailed per-project output printed as each result is processed.

```bash
blf link check --format verbose
```

**Output:**
```
Checking project-a -> /Users/user/workspace/project-a

Copy Status: ✓

Copy Sync Status:
  ✓ .kiro/hooks (in sync)
  ✓ .vscode/settings.json (in sync)
  ⚠ notes.md (target changed)

Git Exclude Status: ✓
```

### Copy Status Indicators

| Status | Description |
|--------|-------------|
| `in sync` | Live hashes of managed and target match |
| `mismatch` | Hashes differ and there is no baseline to label which side moved |
| `managed changed` | Live mismatch; only the hub differs from baseline |
| `target changed` | Live mismatch; only the replica differs from baseline |
| `conflict - both changed` | Live mismatch; both sides differ from baseline |
| `missing` | Target copy doesn't exist |
| `not a copy` | Target path exists but is not a regular copy |

While the daemon is running, hub/fan-out applies these changes live. `link check` hashes now; it does not copy.

### Examples

```bash
# Check all projects (table format)
blf link check

# Check specific project
blf link check my-project

# Show extra exclude entries
blf link check --extra-exclude

# Verbose output
blf link check --format verbose

# Check specific project with verbose output
blf link check my-project --format verbose

# Singleton set (global option)
blf -c custom.yml link check

# All options combined
blf --config custom.yml link check my-project --extra-exclude --format verbose
```

## `revlink` — Manage Files Adopted into the Managed Workflow

`revlink` is a subcommand group with two operations: `create` adopts an existing file or
directory into the managed project as a copy projection, and `restore` is the inverse —
it unregisters the item and leaves the target file in place.

```bash
blf revlink SUBCOMMAND [OPTIONS] PATH
```

**Subcommands:**
- `create` — Adopt a real file or directory as a copy projection
- `restore` — Stop managing PATH and leave the target file in place

Both require a running daemon.

---

## `revlink create` — Adopt a File into the Managed Workflow

Convert an existing file or directory in the current working directory into a managed copy
projection. The original stays a regular file or directory. The daemon copies it into the
managed project (the hub), verifies MD5, records Git exclude and config, then fans the hub
bytes out to other in-sync replicas of that managed project.

### Syntax

```bash
blf revlink create [OPTIONS] PATH
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `PATH` | Yes | File or directory in the current working directory to convert |

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--dry-run` | Flag | Off | Preview all actions without modifying the filesystem |
| `--force` | Flag | Off | Overwrite an existing destination in the managed project |

### Behavior

1. Resolves the configuration set (`--config` → `~/.blf/config` → CWD `config.yml`).
2. Chooses the hub. One managed project targeting CWD: no prompt. PATH already covered by an item: that contribution source, no prompt (then the existing already-covered error). Several hubs targeting CWD and PATH a new item: the same command asks for a 1-based managed project name on the shell screen before the request is sent. No TTY lists the names and exits 1. Ctrl+C on that question closes the screen and sends nothing.
3. Validates the source path (must exist, must not already be a symlink).
4. Copies the source to `<managed_project_path>/<relative-path>`. Nested symlink nodes inside a directory are copied as symlinks.
5. Verifies the copy via MD5 checksum; aborts and deletes the copy on mismatch.
6. Leaves the original as a regular file or directory.
7. Adds the item name to `.git/info/exclude` if the current directory is a Git repository.
8. If the matched mapping uses selective projection (`subpath` list), appends the item name to that list in the mapping file so that the daemon and `link check` will manage it going forward. Mappings that project everything (no `subpath`) are unaffected.
9. Fans the hub copy out to other in-sync replicas of that managed project. If a replica already had different bytes, those bytes are stored under `~/.blf/held/<sha256 of the managed project path>/` (`create-overwrite`) and the hub overwrites the live path.

#### Terminal

On a terminal, `revlink create` opens a shell screen and leaves it up until you close it, including a fast create. When several hubs target CWD and PATH is new, the numbered hub choice is asked on that screen before the request is sent. The header names `revlink create` and PATH. One row shows this request's worker unit: managed project, state (`waiting`, `working`, `done`, or `failed`), the current step, and elapsed time. The header, the row, and the hint stay put. When the command finishes, the transcript fills the output (`Computing checksum of …`, `Copying …`, and the rest, or the error text).

The input line is hidden except while a question is open. It sits directly above the hint.

- Before the request is sent: `Enter: answer` and `Ctrl+C: cancel`. A hub choice is answered with its number. Anything else prints one line and the question stays open. Ctrl+C closes the screen and sends nothing.
- While the request runs: `Ctrl+C: stop`. That prints `Stop this command?` and shows the input.
- Stop question: `Enter: answer`, `Ctrl+C: confirm stop`, `Esc: continue`. `y` stops the command. `n` continues. Anything else prints one line and the question stays open. A second Ctrl+C stops. Esc continues.
- After the command finishes: `q: close` and `Ctrl+C: close`. Closing does not ask for confirmation.

Closing the screen restores the terminal and prints that same transcript. Without a terminal, `revlink create` prints the transcript and exits with the command's exit code. It does not draw a screen or wait for a key.

### Examples

```bash
# Adopt a file into the managed project
blf revlink create myfile.txt

# Adopt a directory
blf revlink create .kiro/hooks

# Preview without making changes
blf revlink create --dry-run myfile.txt

# Overwrite an existing managed copy
blf revlink create --force myfile.txt

# Singleton set
blf -c ~/my-files/config.yml revlink create myfile.txt
```

When several managed projects contribute to CWD and PATH is new, those lines are output on the shell screen. Answer with the number. Create then continues on the chosen hub.

### Output

```
Copying /Users/user/project/myfile.txt -> /Users/user/my-files/project/myfile.txt
Computing checksum of /Users/user/project/myfile.txt
✓ MD5 checksum verified
✓ Target path left in place: /Users/user/project/myfile.txt
Added 'myfile.txt' to .git/info/exclude
```

With `--dry-run`:

```
[dry-run] Copying /Users/user/project/myfile.txt -> /Users/user/my-files/project/myfile.txt
[dry-run] Computing checksum of /Users/user/project/myfile.txt
[dry-run] ✓ MD5 checksum verified
[dry-run] ✓ Target path left in place: /Users/user/project/myfile.txt
[dry-run] Added 'myfile.txt' to .git/info/exclude
```

### Error Cases

| Condition | Message |
|-----------|---------|
| PATH does not exist | `Error: Path does not exist: <path>` |
| PATH is already a symlink | `Error: Path is already a symlink: <path>` |
| Destination exists and `--force` not set | `Error: Destination already exists: <path>` |
| No managed project targets CWD | `No managed project found for current directory: <cwd>` |
| Several hubs target CWD, PATH is new | Numbered prompt, then `Choose a managed project:` |
| Several hubs target CWD, PATH is new, no TTY | `Error: more than one managed project contributes to this directory: <names>` |
| PATH already covered by an item | Uses that contribution source (no prompt); then the existing already-covered error |
| MD5 checksum mismatch | `Error: Checksum mismatch — copy may be corrupt. Destination deleted.` |
| Daemon is down | `Error: daemon is not running. Start it with: blf daemon start` |

---

## `revlink restore` — Stop Managing a Path

The inverse of `revlink create`. Given a path in the current working directory that is a
managed projection, `revlink restore` deletes the managed (hub) copy, leaves PATH as a
regular file or directory, leaves other targets' copies as unmanaged files, and removes
the item from `.git/info/exclude` and the config subpath list.

Leftover blf symlinks from older versions are still restorable: the symlink is removed and
the managed content is copied back as a regular file.

### Syntax

```bash
blf revlink restore [OPTIONS] PATH
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `PATH` | Yes | Projection in the current working directory to stop managing |

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--dry-run` | Flag | Off | Preview all actions without modifying the filesystem |

### Behavior

1. Resolves the configuration set (`--config` → `~/.blf/config` → CWD `config.yml`).
2. Resolves the hub from PATH (contribution source). Run it inside the target. Several managed projects targeting CWD is not CWD-level ambiguity.
3. Validates the path (must exist as a regular file, directory, or leftover symlink; managed copy must exist).
4. Leaves the requesting target's file in place (or, for a leftover symlink, replaces it with a real copy).
5. Deletes the managed copy (non-fatal if this fails — a warning is printed and the restore is still considered successful).
6. Removes the item name from `.git/info/exclude` if the current directory is a Git repository.
7. If the matched mapping uses selective projection (`subpath` list), removes the item name from that list in the mapping file.

#### Terminal

On a terminal, `revlink restore` opens a shell screen and leaves it up until you close it, including a fast restore. The header names `revlink restore` and PATH. One row shows this request's worker unit: managed project, state (`waiting`, `working`, `done`, or `failed`), the current step, and elapsed time. The header, the row, and the hint stay put. When the command finishes, the transcript fills the output (`Leaving target file in place: …`, `Managed copy deleted: …`, and the rest, or the error text).

The input line is hidden except while a question is open. It sits directly above the hint.

- While the request runs: `Ctrl+C: stop`. That prints `Stop this command?` and shows the input.
- Stop question: `Enter: answer`, `Ctrl+C: confirm stop`, `Esc: continue`. `y` stops the command. `n` continues. Anything else prints one line and the question stays open. A second Ctrl+C stops. Esc continues.
- After the command finishes: `q: close` and `Ctrl+C: close`. Closing does not ask for confirmation.

Closing the screen restores the terminal and prints that same transcript. Without a terminal, `revlink restore` prints the transcript and exits with the command's exit code. It does not draw a screen or wait for a key.

### Examples

```bash
# Restore a file from the managed project
blf revlink restore myfile.txt

# Restore a directory
blf revlink restore .kiro/hooks

# Preview without making changes
blf revlink restore --dry-run myfile.txt

# Singleton set
blf -c ~/my-files/config.yml revlink restore myfile.txt
```

### Output

```
Leaving target file in place: /Users/user/project/myfile.txt
✓ Managed copy deleted: /Users/user/my-files/project/myfile.txt
Removed 'myfile.txt' from .git/info/exclude
Removed 'myfile.txt' from config subpath list
```

With `--dry-run`:

```
[dry-run] Leaving target file in place: /Users/user/project/myfile.txt
[dry-run] ✓ Managed copy deleted: /Users/user/my-files/project/myfile.txt
```

### Error Cases

| Condition | Message |
|-----------|---------|
| PATH does not exist | `Error: Path does not exist: <path>` |
| PATH is not a restorable projection | `Error: Path is not a restorable projection: <path>` |
| PATH is not a managed item | `'{path}' is not a managed item` |
| Managed copy missing (leftover dangling symlink) | `Error: Dangling symlink: managed copy does not exist at <managed>` |
| Managed copy missing (regular path) | `Error: Managed copy does not exist at <managed>` |
| MD5 checksum mismatch (leftover symlink restore) | `Error: Checksum mismatch — restored copy deleted. Managed copy preserved.` |
| No managed project targets CWD | `No managed project found for current directory: <cwd>` |
| Daemon is down | `Error: daemon is not running. Start it with: blf daemon start` |

---

## `upgrade` — Self-Upgrade

Upgrade beyond-local-file to the latest version. Automatically detects whether the tool was
installed via `uv tool` or `pipx` and runs the appropriate upgrade command.

### Syntax

```bash
blf upgrade [OPTIONS]
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--dry-run` | Flag | Off | Show the upgrade command without executing it |

### Detection Logic

The command inspects the active Python interpreter path (`sys.executable`) to determine the
install method:

| Detected path pattern | Install method | Upgrade command run |
|-----------------------|----------------|---------------------|
| `…/uv/tools/beyond-local-file/…` | `uv tool` | `uv tool install --upgrade beyond-local-file` |
| `…/pipx/venvs/beyond-local-file/…` | `pipx` | `pipx upgrade beyond-local-file` |
| Anything else | unknown | Prints manual instructions and exits 1 |

### Examples

```bash
# Upgrade to latest version
blf upgrade

# Preview what would be run (no changes made)
blf upgrade --dry-run
```

### Output

```
Detected install method: uv tool
Running: uv tool install --upgrade beyond-local-file
```

When the install method cannot be determined:

```
Cannot determine install method.
sys.executable: /path/to/python

Upgrade manually using the command that matches how you installed the tool:

  uv tool install --upgrade beyond-local-file
  pipx upgrade beyond-local-file
  uv tool install --upgrade git+https://github.com/xingyuli/beyond-local-file.git
```

---

## Exit Codes

| Code | Description |
|------|-------------|
| `0` | Success |
| `1` | Error (invalid config, file not found, daemon down, etc.) |
| `2` | User aborted operation |

---

## Configuration Set

One daemon process loads one **configuration set** — the mapping yaml files that worker uses. The **global set** is the pointer list in `~/.blf/config`. `-c PATH` is a **singleton set** identified by that file's resolved path. With neither, `config.yml` in the current directory is a singleton set.

### Resolution order

The tool resolves which set to load in this order:

1. **`-c` / `--config` flag** — explicit mapping yaml; a singleton set
2. **`~/.blf/config`** — if present and it lists mapping yaml paths; the global set
3. **`config.yml`** in the current directory — a singleton set

Pid, port, log, mapping snapshot, and baseline live under `~/.blf/run/global/` (global set) or `~/.blf/run/file-<sha256 of the resolved mapping yaml>/` (singleton set). Held copies live under `~/.blf/held/<sha256 of the managed project path>/`. Mapping files stay where you keep them.

A mapping file already loaded by a running set is served by that process — `-c` does not start a second watcher. Starting a set that shares a mapping file with another running set is an error and names the owner.

`revlink`, `remove`, and `link check` without `-c` use the global process when `~/.blf/config` exists.

### `~/.blf/config` — Global pointer list

Create `~/.blf/config` to avoid specifying `--config` on every invocation, or to load several mapping files in **one** daemon process (for example personal and company projects):

```yaml
# ~/.blf/config — not itself a mapping document
config_file: ~/my-dev-files/config.yml

# OR several mapping files in one set (personal + company)
config_file:
  - ~/personal/config.yml
  - ~/company/config.yml
```

**Path formats supported:** absolute (`/path/to/config.yml`), tilde (`~/path/to/config.yml`), or relative to the home directory (`path/to/config.yml`).

**Disabling temporarily:** Comment out `config_file` to fall back to `config.yml` in CWD — no need to rename or delete the file:

```yaml
# config_file: ~/my-dev-files/config.yml  # temporarily disabled
```

**Several mapping files:** The global list is one configuration set, loaded by one OS process. Each managed project must appear in exactly one mapping file (identified by its absolute path). Duplicate managed project paths across files are an error.

`~/.blfrc` is not read.

See [Configuration Reference](configuration-reference.md) for mapping-file format documentation.

---

## Common Workflows

### Initial Setup

```bash
# 1. Create config.yml in your managed files directory
cd ~/my-dev-files
cat > config.yml << EOF
my-project: /Users/username/workspace/my-project
EOF

# 2. Start the daemon
blf daemon start

# 3. Verify
blf link check
```

### Daily Usage

```bash
# Keep the daemon running
blf daemon status

# Check copy status
blf link check

# After editing a mapping file by hand
blf daemon reload
```

### Troubleshooting

```bash
# Check status with verbose output
blf link check --format verbose

# Check for extra exclude entries
blf link check --extra-exclude

# Inspect isolation state
blf daemon status

# Follow daemon output
blf logs
```

---

## Environment

### Working Directory

With neither `-c` nor `~/.blf/config`, start the daemon from the directory that contains `config.yml`. With a global set, `link check` without `-c` talks to that one process from any directory. Shells that take a `PATH` (`revlink`, `remove`) run from the target project.

```bash
cd ~/my-dev-files
blf daemon start
blf link check
```

### Configuration set

See [Configuration set](#configuration-set). Override with `-c` or `--config`:

```bash
blf -c /path/to/custom.yml daemon start
blf --config /path/to/custom.yml link check
```

### Git Integration

For Git repositories, projected items are automatically added to `.git/info/exclude` (not `.gitignore`).

**Why `.git/info/exclude`?**
- Local to your repository
- Not committed to Git
- Doesn't affect other developers

---

## See Also

- **[Configuration Reference](configuration-reference.md)** - Complete configuration documentation
- **[Config Format Clarification](config-format-clarification.md)** - Format vs architecture concepts
- **[Platform Support](platform-support.md)** - Cross-platform compatibility
- **[Windows Support](windows-support.md)** - Windows-specific guide
- **[Main README](../README.md)** - Getting started guide
