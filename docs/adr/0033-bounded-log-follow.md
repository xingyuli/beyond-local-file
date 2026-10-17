# Log follow shows recent work, and each log stays bounded

`blf logs` shows a short window of recent work and then follows. The daemon keeps each log from growing without a limit. A tick that found nothing stays in the idle log and is not part of that reading.

## Status

accepted

## Context

0022 puts idle observe, shell requests, and process lifecycle in three files, and has `blf logs` print every stored line from the start of those files, merged by stamp. A tick under 100ms that finds nothing is omitted. A slower tick that finds nothing is stored. On a set whose trees take seconds to scan, that tick is almost every idle line, so the command reprints a long history of ticks that found nothing. The files are append-only. The daemon holds them open for the life of the process, so a rotator outside the process does not move later lines to a new file.

## Decision

- `blf logs` prints the latest 40 included lines, then follows new lines until Ctrl+C. Ctrl+C stops the follow and leaves the daemon running. The lines are merged by the write-time stamp. A terminal colors `[daemon]`, `[idle]`, and `[requests]`. A pipe keeps the prefix and drops the color. A pipe prints the same lines as a terminal.
- The included lines are the whole request log, the whole daemon log, and idle-log lines other than a tick that found nothing. `blf logs requests`, `blf logs idle`, and `blf logs daemon` print that same selection from the named log and print no prefix. A tick that found nothing neither applied a path nor changed out-of-sync. A tick that did apply, or that changed out-of-sync, stays in the reading, including its tick line.
- The opening window may read the live file and the three kept generations, newest first, until it has 40 included lines. Fewer than 40 prints whatever is kept. The follow watches the live file only and reopens that path when the daemon replaces it. The command prints log lines only. There is no flag that prints a file from the first byte. The files in the logs directory are the full record.
- The idle log still records a tick that finds nothing when the look takes 100ms or more (0022). A quicker tick that finds nothing stays omitted.
- The daemon rotates each of the three logs. When the live file is past 8 MiB (8388608 bytes), it closes the file, drops a generation past three, shifts the ones it keeps, and opens a new live file, between lines. The generations are `<record>.log.1`, `<record>.log.2`, and `<record>.log.3`. A file that is already over the cap moves to `.1` as one file. Rotation writes no log line.

## Considered Options

- Print from the first byte of the live files. Rejected: that reprint is the flood of stored ticks.
- A flag to print from the first byte. Rejected: a reader who wants the whole record opens the file in the logs directory.
- A pipe prints from the first byte while a terminal shows the short window. Rejected: the command has one behavior.
- `blf logs idle` prints only ticks that found nothing, or prints every idle line. Rejected: a line from the named log is a line the merge would show for that log.
- Stop storing ticks that found nothing. Rejected: the series stays in the file so a reader can see a tree getting slower.
- Rotate only the idle log, or rotate at midnight and keep seven days. Rejected: one size cap covers a request log that later grows, and it does not depend on the machine being awake at midnight.
- A rotator outside the daemon. Rejected: the daemon holds the live files open, so it is the process that closes, renames, and reopens them.

## Consequences

0022's three records, what each record stores, the millisecond write-time stamp, the merge prefix and its color, and the retired `daemon logs` command still hold. A follow can outlive a rotation. History older than the live file and its three generations is dropped. The shell transcript is still not a substitute.
