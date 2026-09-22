"""Daemon log lines that bypass captured request stdout.

Worker prints are stamped at write time and routed into the idle log, the
request log, or the daemon log (0015, 0022). Shell-request stdout is captured
with ``redirect_stdout`` for the CLI and must not steal these lines. Bind the
routing stream at process start.
"""

from __future__ import annotations

import re
import sys
import threading
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import ClassVar, TextIO

_UNIT_FIELD = re.compile(r"(^|\s)unit=")
_LOG_CHANNELS = ("daemon", "idle", "requests")


class _BoundStream:
    """Process-wide worker stream; None means in-process callers stay silent."""

    stream: ClassVar[TextIO | None] = None


@dataclass
class RequestLogState:
    """Clock and logged-flag shared by one served shell request."""

    enqueued: float
    logged: bool = False


_CHANNEL: ContextVar[str] = ContextVar("blf_log_channel", default="daemon")
_UNIT: ContextVar[str | None] = ContextVar("blf_log_unit", default=None)
_REQUEST_STATE: ContextVar[RequestLogState | None] = ContextVar("blf_request_state", default=None)
_PERSIST_SAMPLES: ContextVar[list[int] | None] = ContextVar("blf_persist_samples", default=None)


def bind_worker_stream(stream: TextIO | None) -> None:
    """Send worker log lines to *stream*, or unbind when *stream* is None.

    Args:
        stream: Routing worker stream, a test buffer, or None.
    """
    _BoundStream.stream = stream


def bind_request_state(state: RequestLogState) -> Token[RequestLogState | None]:
    """Remember *state* for the shell request being served on this thread."""
    return _REQUEST_STATE.set(state)


def reset_request_state(token: Token[RequestLogState | None]) -> None:
    """Restore the request-log state that was current before :func:`bind_request_state`."""
    _REQUEST_STATE.reset(token)


def current_request_state() -> RequestLogState | None:
    """Return the shell request currently being served on this thread, if any."""
    return _REQUEST_STATE.get()


def bind_persist_samples(samples: list[int]) -> Token[list[int] | None]:
    """Collect persist durations into *samples* until the token is reset."""
    return _PERSIST_SAMPLES.set(samples)


def reset_persist_samples(token: Token[list[int] | None]) -> None:
    """Stop collecting persist durations for the current thread."""
    _PERSIST_SAMPLES.reset(token)


def note_persist_ms(elapsed: int) -> None:
    """Record one persist duration when a shell request is collecting them.

    Args:
        elapsed: Milliseconds spent in the persist that just finished.
    """
    samples = _PERSIST_SAMPLES.get()
    if samples is not None:
        samples.append(elapsed)


@contextmanager
def log_scope(channel: str, unit: str | None = None) -> Iterator[None]:
    """Route later worker prints to *channel*, naming *unit* when set.

    Args:
        channel: ``daemon``, ``idle``, or ``requests``.
        unit: Worker-unit name, or None for a line that names its own units.

    Yields:
        Nothing. The previous channel and unit are restored on exit.
    """
    channel_token = _CHANNEL.set(channel)
    unit_token = _UNIT.set(unit)
    try:
        yield
    finally:
        _UNIT.reset(unit_token)
        _CHANNEL.reset(channel_token)


def open_worker_logs(directory: Path) -> None:
    """Open the three worker logs and stamp every later print into one of them.

    Args:
        directory: Set run directory. Logs are created under ``logs/``.
    """
    logs = directory / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    router = _RoutingStream(logs)
    sys.stdout = router
    sys.stderr = router
    bind_worker_stream(router)


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


def _line_stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _with_unit(line: str, unit: str) -> str:
    if _UNIT_FIELD.search(line):
        return line
    suffix = f" unit={unit}"
    if line.endswith("\r\n"):
        return f"{line[:-2]}{suffix}\r\n"
    if line.endswith(("\n", "\r")):
        return f"{line[:-1]}{suffix}{line[-1]}"
    return f"{line}{suffix}"


class _RoutingStream:
    """Text stream that stamps each finished line and writes it to one log."""

    def __init__(self, directory: Path) -> None:
        self._files = {
            name: open(directory / f"{name}.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
            for name in _LOG_CHANNELS
        }
        self._local = threading.local()
        self._lock = threading.Lock()

    def write(self, data: str | bytes) -> int:
        if not data:
            return 0
        written = len(data)
        if isinstance(data, bytes):
            text = data.decode("utf-8", errors="replace")
        else:
            text = data
        pending = getattr(self._local, "pending", "") + text
        parts = pending.splitlines(keepends=True)
        if parts and not parts[-1].endswith(("\n", "\r")):
            self._local.pending = parts.pop()
        else:
            self._local.pending = ""
        if parts:
            with self._lock:
                for part in parts:
                    self._emit(part)
        return written

    def writelines(self, lines: Iterable[str | bytes]) -> None:
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        pending = getattr(self._local, "pending", "")
        if pending:
            self._local.pending = ""
            with self._lock:
                self._emit(pending)
        with self._lock:
            for handle in self._files.values():
                handle.flush()

    def _emit(self, line: str) -> None:
        channel = _CHANNEL.get()
        unit = _UNIT.get()
        if channel in {"idle", "requests"} and unit:
            line = _with_unit(line, unit)
        text = f"{_line_stamp()} {line}"
        if not text.endswith("\n"):
            text += "\n"
        handle = self._files.get(channel, self._files["daemon"])
        handle.write(text)
        handle.flush()

    def __getattr__(self, name: str) -> object:
        return getattr(self._files["daemon"], name)
