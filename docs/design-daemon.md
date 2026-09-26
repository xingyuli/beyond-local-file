# Daemon design

The high-level design is a page of flowcharts:

**[design-daemon.html](design-daemon.html)** — open in a browser.

It covers hub-and-fan-out, process shape (accept thread, worker units, resolve UI), start lifecycle, the live apply path, mapping ingest, and sequential resolve. Terms are in [`CONTEXT.md`](../CONTEXT.md). Decisions are in [`docs/adr/`](adr/).
