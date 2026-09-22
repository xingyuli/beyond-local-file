# Shell screen

A shell on a terminal draws a full screen for a daemon request and leaves it up until the user closes it. One row per worker unit. Questions are lines of output.

## Status

accepted

## Context

0021 showed progress as one rewritten status line (`Waiting …`, then Creating, Restoring, or Removing, then `Writing baseline …`, and `Checking i/n` for check). The line could not show a row per worker unit, and it was cleared before the result could be read. A few-file mutation finishes in tens of milliseconds. Catch-up, a busy worker unit, and a large check are the waits a person notices. The shell is the process attached to the terminal. The daemon streams progress. It does not draw.

## Decision

- Every shell that sends a daemon request opens the shell screen, including a fast create, `daemon status`, and `daemon start` through ready. The screen stays up after the work finishes. `daemon stop`, `upgrade`, and reading logs do not open it. A reload that never sends a request prints its sentence and returns.
- The header names the command and its target: a path, a project, or all projects. For status the header is pid and phase.
- One row per worker unit that request uses: managed project, state (`waiting`, `working`, `done`, or `failed`), the current item or step, and elapsed time. The header, the rows, and the hint stay put. The output scrolls.
- When the command finishes, the plain result fills the output: the check table, the create, restore, or remove transcript, the status text, or the ready message. Closing the screen restores the terminal and prints that same result.
- The shell's questions are lines of output. The input line appears only while a question is open, directly above the hint. A hub choice is answered with its number. A yes/no question is answered with `y` or `n`. Any other submission prints one line and the question stays open. Create's hub choice, a removal confirm, and a held-copy or out-of-sync ack are asked on this screen before the request is sent, one at a time. Nothing is sent until they are answered.
- The hint line at the very bottom lists only the keys that apply in the current state:
  - A question before a request has been sent: `Enter: answer` and `Ctrl+C: cancel`. Ctrl+C closes the screen and sends nothing.
  - Request running, no question open: `Ctrl+C: stop`. That prints `Stop this command?`.
  - Stop question open: `Enter: answer`, `Ctrl+C: confirm stop`, and `Esc: continue`.
  - Work finished: `q: close` and `Ctrl+C: close`. Closing does not ask for confirmation.
- A shell with no terminal prints the plain result and exits with the command's exit code. There is no screen and no hint. A removal is not applied. A hub is not guessed. An isolation warning continues without a question.

## Consequences

0021's status-line sentences no longer hold. Worker-unit scheduling in 0021 stands. A mistake while a request is running takes a confirm. A mistake before the request is sent, or after it has finished, does not. The result remains in the terminal after the screen closes.
