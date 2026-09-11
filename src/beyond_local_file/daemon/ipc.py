"""Localhost TCP request channel between shells and the daemon worker."""

from __future__ import annotations

import json
import socket
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

from .process import port_path, write_ready

type Request = dict[str, Any]
type Response = dict[str, Any]
type RequestHandler = Callable[[Path, Request], Response]

_RECV_SIZE = 65536
_ACCEPT_TIMEOUT_S = 0.25
_CLIENT_TIMEOUT_S = 120.0
_HOST = "127.0.0.1"
_MAX_PORT = 65535


def send_request(config_path: Path, request: Request) -> Response:
    """Send one JSON request to the daemon and return its response.

    Args:
        config_path: Path to the loaded config file.
        request: JSON-serialisable request object.

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
        return _read_json(client)
    finally:
        client.close()


def serve_requests(
    config_path: Path,
    handler: RequestHandler,
    shutdown: Event,
    on_idle: Callable[[], None] | None = None,
    before_request: Callable[[], None] | None = None,
) -> None:
    """Bind a localhost port, mark ready, and handle requests until shutdown.

    Args:
        config_path: Path to the loaded config file.
        handler: Callback that turns a request into a response.
        shutdown: Event set when the worker should stop.
        on_idle: Optional live-observe tick run when accept times out.
        before_request: Optional live-observe tick run before each request.
    """
    path = port_path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((_HOST, 0))
        server.listen(16)
        server.settimeout(_ACCEPT_TIMEOUT_S)
        path.write_text(f"{server.getsockname()[1]}\n", encoding="utf-8")
        write_ready(config_path)
        print("daemon ready", flush=True)
        while not shutdown.is_set():
            try:
                conn, _addr = server.accept()
            except TimeoutError:
                _run_hook(on_idle)
                continue
            except OSError:
                continue
            _run_hook(before_request)
            with conn:
                _handle_connection(conn, config_path, handler)
    finally:
        server.close()
        path.unlink(missing_ok=True)


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


def _handle_connection(conn: socket.socket, config_path: Path, handler: RequestHandler) -> None:
    try:
        request = _read_json(conn)
        response = handler(config_path, request)
    except Exception as error:
        response = {"exit_code": 1, "stdout": f"Error: {error}\n"}
    try:
        _write_json(conn, response)
    except OSError:
        return


def _write_json(conn: socket.socket, payload: Request | Response) -> None:
    conn.sendall(json.dumps(payload).encode("utf-8") + b"\n")


def _read_json(conn: socket.socket) -> Request | Response:
    chunks = bytearray()
    while True:
        piece = conn.recv(_RECV_SIZE)
        if not piece:
            break
        chunks.extend(piece)
        if b"\n" in piece:
            break
    line = bytes(chunks).split(b"\n", 1)[0]
    if not line:
        raise OSError("daemon closed the request channel")
    data = json.loads(line.decode("utf-8"))
    if not isinstance(data, dict):
        raise OSError("daemon request is not a JSON object")
    return data
