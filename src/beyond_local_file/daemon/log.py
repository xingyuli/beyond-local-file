"""Daemon-log lines that bypass captured request stdout.

Worker prints go to ``daemon.log`` through the timestamp wrapper (0015).
Shell-request stdout is captured with ``redirect_stdout`` for the CLI and must
not steal these lines. Bind the wrapped worker stream at process start.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import ClassVar, TextIO


class _BoundStream:
    """Process-wide worker stream; None means in-process callers stay silent."""

    stream: ClassVar[TextIO | None] = None


def bind_worker_stream(stream: TextIO | None) -> None:
    """Send worker log lines to *stream*, or unbind when *stream* is None.

    Args:
        stream: Timestamp-wrapped worker stdout, a test buffer, or None.
    """
    _BoundStream.stream = stream


def worker_print(message: str) -> None:
    """Write one line to the daemon log, bypassing request stdout capture.

    No-op when no worker stream is bound, so in-process tests stay quiet.

    Args:
        message: Line body without a trailing newline.
    """
    target = _BoundStream.stream
    if target is None:
        return
    print(message, flush=True, file=target)


def duration_ms(started: float) -> int:
    """Return milliseconds elapsed since *started* (``time.perf_counter``).

    Args:
        started: Monotonic start time.

    Returns:
        Non-negative millisecond count, rounded to nearest integer.
    """
    elapsed = time.perf_counter() - started
    if elapsed <= 0:
        return 0
    return round(elapsed * 1000)


@contextmanager
def log_duration(label: str, **fields: object) -> Iterator[dict[str, object]]:
    """Log *label* with ``key=value`` fields and ``duration_ms`` when the block ends.

    Args:
        label: Line prefix such as ``create: copy`` or ``baseline: record``.
        **fields: Initial ``key=value`` fields. The yielded dict may be updated
            before the block exits; ``duration_ms`` is appended last.

    Yields:
        Mutable field map included in the log line.
    """
    started = time.perf_counter()
    extra: dict[str, object] = dict(fields)
    try:
        yield extra
    finally:
        extra["duration_ms"] = duration_ms(started)
        body = " ".join(f"{key}={value}" for key, value in extra.items())
        worker_print(f"{label} {body}")
