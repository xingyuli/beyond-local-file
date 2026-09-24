"""Localhost resolve UI served while the daemon is ready."""

from __future__ import annotations

import hmac
import html
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from beyond_local_file.held import list_held_copies
from beyond_local_file.model.config import ConfigProject
from beyond_local_file.project_processor import load_set_projects

from .process import resolve_port_path, resolve_token_path
from .store import get_state, iter_out_of_sync, load_baseline, load_snapshot

_HOST = "127.0.0.1"
_TOKEN_BYTES = 32
_MAX_PORT = 65535


class ResolveHttp:
    """HTTP server and files for one ready daemon."""

    def __init__(self, server: HTTPServer, thread: threading.Thread, config_path: Path) -> None:
        self._server = server
        self._thread = thread
        self._config_path = config_path

    def stop(self) -> None:
        """Stop serving and unlink the resolve port and token files."""
        self._server.shutdown()
        self._thread.join(timeout=2)
        self._server.server_close()
        _unlink_resolve_files(self._config_path)


def resolve_ui_url(config_path: Path) -> str | None:
    """Return the localhost resolve UI URL when port and token files exist.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        ``http://127.0.0.1:<port>/?token=<token>``, or None.
    """
    port = _read_port(resolve_port_path(config_path))
    token = _read_text(resolve_token_path(config_path))
    if port is None or not token:
        return None
    return f"http://127.0.0.1:{port}/?token={token}"


def start_resolve_ui(config_path: Path) -> ResolveHttp:
    """Bind a localhost HTTP port, write port and token files, and serve.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        A handle that stops the server and unlinks the files.
    """
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    handler = _handler_for(config_path, token)
    server = HTTPServer((_HOST, 0), handler)
    port = int(server.server_address[1])
    token_file = resolve_token_path(config_path)
    port_file = resolve_port_path(config_path)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(f"{token}\n", encoding="utf-8")
    port_file.write_text(f"{port}\n", encoding="utf-8")
    started = threading.Event()

    def serve() -> None:
        started.set()
        server.serve_forever()

    thread = threading.Thread(target=serve, name="blf-resolve-ui", daemon=True)
    thread.start()
    started.wait(timeout=2)
    return ResolveHttp(server, thread, config_path)


def stop_resolve_ui(handle: ResolveHttp | None) -> None:
    """Stop *handle* when one is running."""
    if handle is None:
        return
    handle.stop()


def _unlink_resolve_files(config_path: Path) -> None:
    resolve_port_path(config_path).unlink(missing_ok=True)
    resolve_token_path(config_path).unlink(missing_ok=True)


def _read_port(path: Path) -> int | None:
    text = _read_text(path)
    if not text:
        return None
    try:
        port = int(text.splitlines()[0])
    except ValueError:
        return None
    if port <= 0 or port > _MAX_PORT:
        return None
    return port


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _handler_for(config_path: Path, token: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            got = (parse_qs(parsed.query).get("token") or [""])[0]
            if not got or not hmac.compare_digest(got, token):
                self.send_error(HTTPStatus.UNAUTHORIZED, "Unauthorized")
                return
            body = _page_html(config_path).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            del fmt, args

    return Handler


def _page_html(config_path: Path) -> str:
    oos_items, held_items = _isolation(config_path)
    oos_rows = "\n".join(_oos_row(replica, rel, clause) for replica, rel, clause in oos_items) or "<li>None</li>"
    held_rows = "\n".join(_held_row(clause, slot) for clause, slot in held_items) or "<li>None</li>"
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Resolve UI</title></head><body>'
        "<h1>Out-of-sync</h1><ul>"
        f"{oos_rows}"
        "</ul><h1>Held copies</h1><ul>"
        f"{held_rows}"
        "</ul></body></html>"
    )


def _oos_row(replica: Path, rel: str, clause: str) -> str:
    line = f"{html.escape(replica.as_posix())} {html.escape(rel)}"
    if clause:
        line += f"<br>{html.escape(clause)}"
    return f"<li>{line}</li>"


def _held_row(clause: str, slot: Path) -> str:
    return f"<li>{html.escape(clause)}<br>{html.escape(slot.as_posix())}</li>"


def _isolation(config_path: Path) -> tuple[list[tuple[Path, str, str]], list[tuple[str, Path]]]:
    trees = load_baseline(config_path) or {}
    oos: list[tuple[Path, str, str]] = []
    for replica, rel in iter_out_of_sync(trees):
        clause = str(get_state(trees, replica, rel).get("clause") or "")
        oos.append((replica, rel, clause))
    held: list[tuple[str, Path]] = []
    for project in _projects(config_path).values():
        for copy in list_held_copies(project.managed_project_path):
            held.append((copy.clause, copy.slot))
    return oos, held


def _projects(config_path: Path) -> dict[str, ConfigProject]:
    snapshot = load_snapshot(config_path)
    if snapshot is not None:
        return snapshot
    return load_set_projects(config_path)
