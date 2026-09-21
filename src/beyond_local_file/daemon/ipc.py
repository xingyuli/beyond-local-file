"""Localhost TCP request channel between shells and the daemon worker."""

from __future__ import annotations

import json
import os
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock
from typing import Any, Literal

from .log import duration_ms, worker_print
from .process import port_path

type Request = dict[str, Any]
type Response = dict[str, Any]
type ProgressCallback = Callable[[str], None]
type RequestHandler = Callable[[Path, Request, ProgressCallback | None], Response]
type DaemonPhase = Literal["catch-up", "ready"]


def format_status_line(verb: str, index: int, total: int, item: str) -> str:
    """Return one status line: verb, unit i/n, and the current item name.

    Args:
        verb: Leading verb, such as ``Catching up`` or ``Checking``.
        index: 1-based processing-unit index.
        total: Number of processing units.
        item: Current item name (not a per-file path).

    Returns:
        A single-line status string.
    """
    return f"{verb} {index}/{total} … {item}".rstrip()


_RECV_SIZE = 65536
_ACCEPT_TIMEOUT_S = 0.25
_CLIENT_TIMEOUT_S = 120.0
_HOST = "127.0.0.1"
_MAX_PORT = 65535


class WorkerState:
    """Shared daemon phase and catch-up progress for IPC waiters."""

    def __init__(self) -> None:
        self.ready = Event()
        self._lock = Lock()
        self._phase: DaemonPhase = "catch-up"
        self._index = 0
        self._total = 0
        self._item = ""

    @property
    def phase(self) -> DaemonPhase:
        """Return the current daemon phase."""
        with self._lock:
            return self._phase

    def set_progress(self, index: int, total: int, item: str) -> None:
        """Record the current catch-up unit and item name.

        Args:
            index: 1-based processing-unit index.
            total: Number of processing units.
            item: Current item name (not a per-file path).
        """
        with self._lock:
            self._index = index
            self._total = total
            self._item = item

    def set_ready(self) -> None:
        """Mark the daemon as ready for live observation and mutating ops."""
        with self._lock:
            self._phase = "ready"
        self.ready.set()

    def progress_line(self) -> str | None:
        """Return the current catch-up status line, or None when not catching up."""
        with self._lock:
            if self._phase != "catch-up":
                return None
            index = self._index
            total = self._total
            item = self._item
        if total <= 0 and not item:
            return None
        return format_status_line("Catching up", index, total, item)

    def status_response(self) -> Response:
        """Return the immediate status RPC payload."""
        pid = os.getpid()
        phase = self.phase
        return {
            "exit_code": 0,
            "stdout": f"Daemon is running (pid {pid}, phase {phase})\n",
            "phase": phase,
            "pid": pid,
        }


def send_request(
    config_path: Path,
    request: Request,
    on_progress: ProgressCallback | None = None,
) -> Response:
    """Send one JSON request to the daemon and return its response.

    Progress messages streamed on this connection are delivered to *on_progress*.

    Args:
        config_path: Path to the loaded config file.
        request: JSON-serialisable request object.
        on_progress: Optional callback for streamed status lines.

    Returns:
        The daemon's JSON response.

    Raises:
        OSError: If the port file is missing or the reply cannot be read.
    """
    port = _read_port(config_path)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(_CLIENT_TIMEOUT_S)
    try:
        client.connect((_HOST, port))
        _write_json(client, request)
        buffer = bytearray()
        while True:
            message = _read_json(client, buffer)
            progress = message.get("progress")
            if progress is not None and "exit_code" not in message:
                if on_progress is not None:
                    on_progress(str(progress))
                continue
            return message
    finally:
        client.close()


@dataclass
class ServeLoop:
    """Accept-loop configuration for one worker process."""

    shutdown: Event
    bound: Event | None = None
    state: WorkerState | None = None
    on_idle: Callable[[], None] | None = None
    before_request: Callable[[], None] | None = None


def serve_requests(
    config_path: Path,
    handler: RequestHandler,
    loop: ServeLoop,
) -> None:
    """Bind a localhost port and handle requests until shutdown.

    Catch-up waiters are queued until *loop.state* is ready. ``status`` is
    answered immediately in both phases. Live-observe hooks run only after ready.

    Args:
        config_path: Path to the loaded config file.
        handler: Callback that turns a request into a response.
        loop: Shutdown, bind, phase, and live-observe hooks.
    """
    path = port_path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    pending: list[_Pending] = []
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((_HOST, 0))
        server.listen(16)
        server.settimeout(_ACCEPT_TIMEOUT_S)
        path.write_text(f"{server.getsockname()[1]}\n", encoding="utf-8")
        if loop.bound is not None:
            loop.bound.set()
        while not loop.shutdown.is_set():
            try:
                conn, _addr = server.accept()
            except TimeoutError:
                _on_idle(pending, config_path, handler, loop)
                continue
            except OSError:
                continue
            _accept_one(conn, pending, config_path, handler, loop)
    finally:
        for item in pending:
            item.conn.close()
        server.close()
        path.unlink(missing_ok=True)


def _on_idle(
    pending: list[_Pending],
    config_path: Path,
    handler: RequestHandler,
    loop: ServeLoop,
) -> None:
    state = loop.state
    if state is not None and not state.ready.is_set():
        _flush_progress(pending, state)
        return
    _release_pending(pending, config_path, handler, loop.before_request)
    _run_hook(loop.on_idle)


def _accept_one(
    conn: socket.socket,
    pending: list[_Pending],
    config_path: Path,
    handler: RequestHandler,
    loop: ServeLoop,
) -> None:
    try:
        request = _read_json(conn)
    except Exception:
        conn.close()
        return
    op = request.get("op")
    state = loop.state
    if op == "status":
        payload = state.status_response() if state is not None else _status_without_state()
        _reply(conn, payload)
        return
    if op == "wait":
        if state is not None and not state.ready.is_set():
            _queue_waiter(pending, conn, request, state)
            return
        _reply(conn, {"exit_code": 0, "stdout": "", "phase": "ready", "pid": os.getpid()})
        return
    if state is not None and not state.ready.is_set():
        _queue_waiter(pending, conn, request, state)
        return
    _run_and_reply(conn, request, config_path, handler, loop.before_request)


def _queue_waiter(
    pending: list[_Pending],
    conn: socket.socket,
    request: Request,
    state: WorkerState,
) -> None:
    item = _Pending(conn=conn, request=request)
    pending.append(item)
    if not _write_progress(item, state):
        pending.remove(item)


def _release_pending(
    pending: list[_Pending],
    config_path: Path,
    handler: RequestHandler,
    before_request: Callable[[], None] | None,
) -> None:
    while pending:
        item = pending.pop(0)
        if item.request.get("op") == "wait":
            _reply(item.conn, {"exit_code": 0, "stdout": "", "phase": "ready", "pid": os.getpid()})
            continue
        _run_and_reply(item.conn, item.request, config_path, handler, before_request)


def _flush_progress(pending: list[_Pending], state: WorkerState) -> None:
    still: list[_Pending] = []
    for item in pending:
        if _write_progress(item, state):
            still.append(item)
    pending[:] = still


def _write_progress(item: _Pending, state: WorkerState) -> bool:
    line = state.progress_line()
    if not line or line == item.last_progress:
        return True
    try:
        _write_json(item.conn, {"progress": line})
        item.last_progress = line
        return True
    except OSError:
        item.conn.close()
        return False


def _run_and_reply(
    conn: socket.socket,
    request: Request,
    config_path: Path,
    handler: RequestHandler,
    before_request: Callable[[], None] | None,
) -> None:
    def emit_progress(line: str) -> None:
        try:
            _write_json(conn, {"progress": line})
        except OSError:
            return

    fields = _request_log_fields(request)
    worker_print(_format_fields("request: start", fields))
    started = time.perf_counter()
    _run_hook(before_request)
    try:
        response = handler(config_path, request, emit_progress)
    except Exception as error:
        response = {"exit_code": 1, "stdout": f"Error: {error}\n"}
    done = {**fields, "exit": response.get("exit_code"), "duration_ms": duration_ms(started)}
    worker_print(_format_fields("request: done", done))
    _reply(conn, response)


def _reply(conn: socket.socket, response: Response) -> None:
    try:
        _write_json(conn, response)
    except OSError:
        return
    finally:
        conn.close()


def _status_without_state() -> Response:
    pid = os.getpid()
    return {
        "exit_code": 0,
        "stdout": f"Daemon is running (pid {pid}, phase ready)\n",
        "phase": "ready",
        "pid": pid,
    }


def _request_log_fields(request: Request) -> dict[str, object]:
    fields: dict[str, object] = {"op": request.get("op") or ""}
    path = request.get("path")
    if path:
        fields["path"] = path
    cwd = request.get("cwd")
    if cwd:
        fields["cwd"] = cwd
    if request.get("dry_run"):
        fields["dry_run"] = "true"
    return fields


def _format_fields(label: str, fields: dict[str, object]) -> str:
    body = " ".join(f"{key}={value}" for key, value in fields.items())
    return f"{label} {body}" if body else label


def _run_hook(hook: Callable[[], None] | None) -> None:
    if hook is None:
        return
    try:
        hook()
    except Exception as error:
        print(f"live: observe error: {error}", flush=True)


def _read_port(config_path: Path) -> int:
    path = port_path(config_path)
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise OSError("daemon port file is empty")
    try:
        port = int(text.splitlines()[0])
    except ValueError as error:
        raise OSError("daemon port file is invalid") from error
    if port <= 0 or port > _MAX_PORT:
        raise OSError("daemon port file is invalid")
    return port


def _write_json(conn: socket.socket, payload: Request | Response) -> None:
    conn.sendall(json.dumps(payload).encode("utf-8") + b"\n")


def _read_json(conn: socket.socket, buffer: bytearray | None = None) -> Request | Response:
    chunks = buffer if buffer is not None else bytearray()
    while True:
        newline = chunks.find(b"\n")
        if newline >= 0:
            line = bytes(chunks[:newline])
            del chunks[: newline + 1]
            if not line:
                continue
            data = json.loads(line.decode("utf-8"))
            if not isinstance(data, dict):
                raise OSError("daemon request is not a JSON object")
            return data
        piece = conn.recv(_RECV_SIZE)
        if not piece:
            break
        chunks.extend(piece)
    raise OSError("daemon closed the request channel")


@dataclass
class _Pending:
    conn: socket.socket
    request: Request
    last_progress: str | None = None
