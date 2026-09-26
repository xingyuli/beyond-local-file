"""Localhost resolve UI served while the daemon is ready."""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from beyond_local_file.held import list_held_copies
from beyond_local_file.model.config import ConfigProject, Mapping
from beyond_local_file.project_processor import load_set_projects

from .catchup import rel_in_items
from .merge import is_binary
from .process import resolve_port_path, resolve_token_path
from .store import BaselineTrees, get_state, is_out_of_sync, iter_out_of_sync, load_baseline, load_snapshot

_HOST = "127.0.0.1"
_TOKEN_BYTES = 32
_MAX_PORT = 65535
_MAX_POST = 8 * 1024 * 1024
_MIN_SHARED_PATH_PARTS = 2
_STATIC_PREFIX = "/static/"
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_STATIC_ASSETS: dict[str, str] = {
    "vendor/codemirror.js": "text/javascript; charset=utf-8",
    "vendor/codemirror.css": "text/css; charset=utf-8",
    "vendor/merge.js": "text/javascript; charset=utf-8",
    "vendor/merge.css": "text/css; charset=utf-8",
    "vendor/diff_match_patch.js": "text/javascript; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
    "app.css": "text/css; charset=utf-8",
}


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


type ResolveApply = Callable[[str, str, bytes], dict]


def start_resolve_ui(config_path: Path, apply_resolve: ResolveApply | None = None) -> ResolveHttp:
    """Bind a localhost HTTP port, write port and token files, and serve.

    Args:
        config_path: Path to the loaded config file.
        apply_resolve: Callback that enqueues resolve on the worker unit for
            that managed project. The HTTP thread must not write the hub.

    Returns:
        A handle that stops the server and unlinks the files.
    """
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    handler = _handler_for(config_path, token, apply_resolve)
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


def _handler_for(
    config_path: Path,
    token: str,
    apply_resolve: ResolveApply | None = None,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed_path = urlparse(self.path).path
            if parsed_path.startswith(_STATIC_PREFIX):
                _serve_static(self, parsed_path[len(_STATIC_PREFIX) :])
                return
            query = _authorized_query(self, token)
            if query is None:
                return
            project = (query.get("project") or [""])[0]
            rel = (query.get("path") or [""])[0]
            if not project or not rel:
                default = _first_nav_selection(config_path)
                if default is not None:
                    _redirect(self, _detail_href(token, *default))
                    return
            body = _page_html(config_path, token=token, project=project, rel=rel).encode("utf-8")
            _send(self, HTTPStatus.OK, body, "text/html; charset=utf-8")

        def do_POST(self) -> None:
            query = _authorized_query(self, token)
            if query is None:
                return
            payload = _read_json_payload(self)
            if payload is None:
                return
            project = str(payload.get("project") or (query.get("project") or [""])[0])
            rel = str(payload.get("path") or (query.get("path") or [""])[0])
            action = str(payload.get("action") or "")
            body = json.dumps(
                _resolve_post(
                    config_path,
                    {**payload, "project": project, "path": rel, "action": action},
                    apply_resolve,
                )
            ).encode("utf-8")
            _send(self, HTTPStatus.OK, body, "application/json; charset=utf-8")

        def log_message(self, fmt: str, *args: object) -> None:
            del fmt, args

    return Handler


def _serve_static(handler: BaseHTTPRequestHandler, name: str) -> None:
    """Serve one static asset by exact allow-listed name; no token required.

    Args:
        handler: The active request handler.
        name: The path segment after ``/static/``, checked against a fixed allowlist.
    """
    content_type = _STATIC_ASSETS.get(name)
    path = _STATIC_DIR / name if content_type is not None else None
    if content_type is None or path is None or not path.is_file():
        handler.send_error(HTTPStatus.NOT_FOUND, "Not found")
        return
    _send(handler, HTTPStatus.OK, path.read_bytes(), content_type)


def _authorized_query(handler: BaseHTTPRequestHandler, token: str) -> dict[str, list[str]] | None:
    query = parse_qs(urlparse(handler.path).query)
    got = (query.get("token") or [""])[0]
    if not got or not hmac.compare_digest(got, token):
        handler.send_error(HTTPStatus.UNAUTHORIZED, "Unauthorized")
        return None
    return query


def _read_json_payload(handler: BaseHTTPRequestHandler) -> dict | None:
    length = _content_length(handler)
    if length is None:
        handler.send_error(HTTPStatus.BAD_REQUEST, "Bad request")
        return None
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        handler.send_error(HTTPStatus.BAD_REQUEST, "Bad request")
        return None
    if not isinstance(payload, dict):
        handler.send_error(HTTPStatus.BAD_REQUEST, "Bad request")
        return None
    return payload


def _content_length(handler: BaseHTTPRequestHandler) -> int | None:
    raw = handler.headers.get("Content-Length", "0")
    try:
        length = int(raw)
    except ValueError:
        return None
    if length < 0 or length > _MAX_POST:
        return None
    return length


def _send(handler: BaseHTTPRequestHandler, status: int, body: bytes, content_type: str) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _redirect(handler: BaseHTTPRequestHandler, location: str) -> None:
    handler.send_response(HTTPStatus.FOUND)
    handler.send_header("Location", location)
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def _first_nav_selection(config_path: Path) -> tuple[str, str] | None:
    """Return the (project, rel) that opens by default: the first out-of-sync row, or else held.

    Matches ``_default_nav_tab``'s pane priority, so landing on the index is indistinguishable
    from clicking that row yourself — same URL, same highlighted nav item.
    """
    projects = _projects(config_path)
    trees = load_baseline(config_path) or {}
    rows = _nav_rows(projects, trees)
    for row in rows:
        if row[2]:
            return row[0], row[1]
    for row in rows:
        if row[3]:
            return row[0], row[1]
    return None


def _page_html(config_path: Path, *, token: str, project: str, rel: str) -> str:
    projects = _projects(config_path)
    trees = load_baseline(config_path) or {}
    rows = _nav_rows(projects, trees)
    nav = _nav_html(rows, token, (project, rel))
    detail = _detail_html(projects, trees, (project, rel))
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Resolve UI</title>'
        '<link rel="stylesheet" href="/static/vendor/codemirror.css">'
        '<link rel="stylesheet" href="/static/vendor/merge.css">'
        '<link rel="stylesheet" href="/static/app.css">'
        "</head><body>"
        '<nav class="index">'
        '<div class="nav-toggle-wrap">'
        '<button type="button" class="btn nav-toggle" id="nav-toggle" aria-expanded="true" aria-controls="nav-body" aria-label="Hide files">'
        '<svg class="nav-toggle-icon" viewBox="0 0 16 16" aria-hidden="true">'
        '<rect x="2" y="2.5" width="12" height="11" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.35"/>'
        '<path d="M6 2.5v11" fill="none" stroke="currentColor" stroke-width="1.35"/>'
        '<path class="nav-toggle-chevron-in" d="M10.4 6.1 8.3 8l2.1 1.9" fill="none" stroke="currentColor" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path class="nav-toggle-chevron-out" d="M8.3 6.1 10.4 8 8.3 9.9" fill="none" stroke="currentColor" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg></button>"
        '<span class="nav-toggle-keys" id="nav-toggle-keys"></span>'
        "</div>"
        f'<div id="nav-body">{nav}</div>'
        "</nav><main>"
        f"{detail}</main>"
        '<script src="/static/vendor/codemirror.js"></script>'
        '<script src="/static/vendor/diff_match_patch.js"></script>'
        '<script src="/static/vendor/merge.js"></script>'
        '<script src="/static/app.js"></script>'
        "</body></html>"
    )


def _nav_rows(projects: dict[str, ConfigProject], trees: BaselineTrees) -> list[tuple[str, str, bool, bool]]:
    flags: dict[tuple[str, str], list[bool]] = {}
    for replica, rel in iter_out_of_sync(trees):
        project = _owner(projects, replica, rel)
        if project is None:
            continue
        flags.setdefault((project.managed_project_name, rel), [False, False])[0] = True
    for project in projects.values():
        for copy in list_held_copies(project.managed_project_path):
            flags.setdefault((project.managed_project_name, copy.path), [False, False])[1] = True
    return [(name, rel, oos, held) for (name, rel), (oos, held) in sorted(flags.items())]


def _nav_html(rows: list[tuple[str, str, bool, bool]], token: str, selection: tuple[str, str]) -> str:
    """Render the left nav as two top panes (out-of-sync / held), not a per-row type label.

    The two categories are a natural hierarchy (pick a category, then a path), so a tab switcher
    communicates that with position and a background highlight instead of a repeated text badge
    on every row. When only one category has anything in it, the switcher itself is redundant and
    is left out; the lone pane is simply the whole nav.
    """
    if not rows:
        return "<p>None</p>"
    oos_rows = [row for row in rows if row[2]]
    held_rows = [row for row in rows if row[3]]
    default_tab = _default_nav_tab(oos_rows, held_rows, selection)
    tabs = ""
    if oos_rows and held_rows:
        tabs = (
            '<div class="nav-tabs">'
            '<label class="nav-tab-label" for="nav-tab-oos">Out of sync'
            f'<span class="nav-tab-count">{len(oos_rows)}</span></label>'
            '<label class="nav-tab-label" for="nav-tab-held">Held'
            f'<span class="nav-tab-count">{len(held_rows)}</span></label>'
            "</div>"
        )
    oos_checked = " checked" if default_tab == "oos" else ""
    held_checked = " checked" if default_tab == "held" else ""
    return (
        f'<input type="radio" name="nav-tab" id="nav-tab-oos" class="nav-tab-radio"{oos_checked}>'
        f'<input type="radio" name="nav-tab" id="nav-tab-held" class="nav-tab-radio"{held_checked}>'
        f"{tabs}"
        f'<div class="nav-pane" id="nav-pane-oos">{_nav_pane_body(oos_rows, token, selection)}</div>'
        f'<div class="nav-pane" id="nav-pane-held">{_nav_pane_body(held_rows, token, selection)}</div>'
    )


def _default_nav_tab(
    oos_rows: list[tuple[str, str, bool, bool]],
    held_rows: list[tuple[str, str, bool, bool]],
    selection: tuple[str, str],
) -> str:
    """Return which pane should open checked: whichever already holds the current selection."""
    if any((name, rel) == selection for name, rel, _oos, _held in oos_rows):
        return "oos"
    if any((name, rel) == selection for name, rel, _oos, _held in held_rows):
        return "held"
    return "oos" if oos_rows else "held"


def _nav_pane_body(rows: list[tuple[str, str, bool, bool]], token: str, selection: tuple[str, str]) -> str:
    if not rows:
        return ""
    sections: list[str] = []
    current = ""
    items: list[str] = []
    for name, rel, _oos, _held in rows:
        if name != current:
            if current:
                sections.append(_project_section(current, items))
            current = name
            items = []
        items.append(_nav_row_html(token, name, rel, is_current=(name, rel) == selection))
    if current:
        sections.append(_project_section(current, items))
    return "".join(sections)


def _nav_row_html(token: str, name: str, rel: str, *, is_current: bool) -> str:
    """One nav row: the path is the only label; ``data-current`` marks the open item for CSS."""
    href = html.escape(_detail_href(token, name, rel), quote=True)
    title = html.escape(rel, quote=True)
    current_attr = ' data-current="true"' if is_current else ""
    return f'<li class="nav-row"{current_attr}><a href="{href}" title="{title}">{html.escape(rel)}</a></li>'


def _project_section(name: str, items: list[str]) -> str:
    return f"<section><h2>{html.escape(name)}</h2><ul>{''.join(items)}</ul></section>"


def _detail_html(
    projects: dict[str, ConfigProject],
    trees: BaselineTrees,
    selection: tuple[str, str],
) -> str:
    project_name, rel = selection
    if not project_name or not rel:
        return ""
    project = _project_named(projects, project_name)
    if project is None:
        return ""
    oos, held = _row_flags(trees, project, rel)
    if not oos and not held:
        return ""
    parts: list[str] = []
    if oos:
        parts.append(_copy_view_html(project, trees, rel))
    if held:
        clauses = [copy.clause for copy in list_held_copies(project.managed_project_path) if copy.path == rel]
        held_rows = "".join(f"<p>{html.escape(clause)}</p>" for clause in clauses)
        parts.append(f'<section class="held">{held_rows}</section>')
    return "".join(parts)


def _copy_view_html(project: ConfigProject, trees: BaselineTrees, rel: str) -> str:
    """Return the mount point and embedded state for the client-driven sequential merge (ADR 0025)."""
    state = _resolve_state(project, trees, rel)
    return f'<div id="resolve-app"></div>{_json_script(state)}'


def _resolve_state(project: ConfigProject, trees: BaselineTrees, rel: str) -> dict:
    hub = project.managed_project_path
    replicas = _replicas_for(project, rel)
    hub_bytes = _live_bytes(hub, rel)
    binary = is_binary(hub_bytes)
    prefix = _common_prefix(replicas)
    ctx = _ReplicaCtx(hub=hub, trees=trees, rel=rel, prefix=prefix, binary=binary)
    state: dict[str, object] = {
        "binary": binary,
        "common_prefix": prefix,
        "replicas": [_replica_state(ctx, replica) for replica in replicas],
    }
    if binary:
        state["hub_hash"] = hashlib.sha256(hub_bytes).hexdigest()
        state["hub_size"] = len(hub_bytes)
        state["hub_content"] = base64.b64encode(hub_bytes).decode("ascii")
    else:
        state["hub_now"] = _bytes_as_text(hub_bytes)
    return state


@dataclass(frozen=True)
class _ReplicaCtx:
    """Fields shared by every replica entry of one path's resolve state."""

    hub: Path
    trees: BaselineTrees
    rel: str
    prefix: str
    binary: bool


def _replica_state(ctx: _ReplicaCtx, replica: Path) -> dict[str, object]:
    replica_bytes = _live_bytes(replica, ctx.rel)
    same = _same_as_hub(ctx.hub, replica, ctx.rel)
    replica_state = get_state(ctx.trees, replica, ctx.rel)
    clause = str(replica_state.get("clause") or "") if is_out_of_sync(replica_state) else ""
    posix = replica.as_posix()
    label = posix[len(ctx.prefix) :] if ctx.prefix and posix.startswith(ctx.prefix) else posix
    entry: dict[str, object] = {"path": posix, "label": label, "same_as_hub": same, "clause": clause}
    if ctx.binary:
        entry["hash"] = hashlib.sha256(replica_bytes).hexdigest()
        entry["size"] = len(replica_bytes)
        entry["content"] = base64.b64encode(replica_bytes).decode("ascii")
    else:
        entry["text"] = _bytes_as_text(replica_bytes)
    return entry


def _common_prefix(paths: list[Path]) -> str:
    """Return the longest shared leading directory path across *paths*, or "" when not worth it."""
    if len(paths) < _MIN_SHARED_PATH_PARTS:
        return ""
    parts_lists = [path.as_posix().split("/") for path in paths]
    common: list[str] = []
    for parts in zip(*parts_lists, strict=False):
        if len(set(parts)) != 1:
            break
        common.append(parts[0])
    if len(common) < _MIN_SHARED_PATH_PARTS:
        return ""
    return "/".join(common) + "/"


def _resolve_post(config_path: Path, payload: dict, apply_resolve: ResolveApply | None) -> dict:
    del config_path
    action = str(payload.get("action") or "")
    if action != "submit":
        return {"ok": False, "error": "unknown action"}
    project = str(payload.get("project") or "")
    rel = str(payload.get("path") or "")
    content = _confirmed_bytes(payload)
    if not project or not rel:
        return {"ok": False, "error": "missing project or path"}
    if content is None:
        return {"ok": False, "error": "missing confirmed fact"}
    if apply_resolve is None:
        return {"ok": False, "error": "worker unit cannot take the op"}
    return apply_resolve(project, rel, content)


def _confirmed_bytes(payload: dict) -> bytes | None:
    if payload.get("binary"):
        content = payload.get("content")
        if not isinstance(content, str):
            return None
        try:
            return base64.b64decode(content, validate=True)
        except ValueError:
            return None
    middle = payload.get("middle")
    if not isinstance(middle, str):
        return None
    return middle.encode("utf-8")


def _bytes_as_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _json_script(state: dict) -> str:
    dumped = json.dumps(state, separators=(",", ":")).replace("<", "\\u003c")
    return f'<script type="application/json" id="resolve-state">{dumped}</script>'


def _replicas_for(project: ConfigProject, rel: str) -> list[Path]:
    found: dict[str, Path] = {}
    for mapping in project.mappings:
        if not _mapping_has_rel(mapping, rel):
            continue
        for target in mapping.targets:
            resolved = target.resolve()
            found[resolved.as_posix()] = resolved
    return [found[key] for key in sorted(found)]


def _same_path(left: Path, right: Path) -> bool:
    if left == right or left.as_posix() == right.as_posix():
        return True
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def _same_as_hub(hub: Path, replica: Path, rel: str) -> bool:
    left = hub / rel
    right = replica / rel
    if not left.is_file() or left.is_symlink() or not right.is_file() or right.is_symlink():
        return False
    return left.read_bytes() == right.read_bytes()


def _live_bytes(root: Path, rel: str) -> bytes:
    path = root / rel
    if path.is_file() and not path.is_symlink():
        return path.read_bytes()
    return b""


def _mapping_has_rel(mapping: Mapping, rel: str) -> bool:
    if mapping.subpaths is None:
        return True
    return rel_in_items(rel, mapping.subpaths)


def _owner(projects: dict[str, ConfigProject], replica: Path, rel: str) -> ConfigProject | None:
    for project in projects.values():
        for mapping in project.mappings:
            if not _mapping_has_rel(mapping, rel):
                continue
            if any(_same_path(target, replica) for target in mapping.targets):
                return project
    return None


def _project_named(projects: dict[str, ConfigProject], name: str) -> ConfigProject | None:
    for project in projects.values():
        if project.managed_project_name == name:
            return project
    return projects.get(name)


def _row_flags(trees: BaselineTrees, project: ConfigProject, rel: str) -> tuple[bool, bool]:
    oos = any(is_out_of_sync(get_state(trees, replica, rel)) for replica in _replicas_for(project, rel))
    held = any(copy.path == rel for copy in list_held_copies(project.managed_project_path))
    return oos, held


def _detail_href(token: str, project: str, rel: str) -> str:
    query = {"token": token, "project": project, "path": rel}
    return "/?" + urlencode(query)


def _projects(config_path: Path) -> dict[str, ConfigProject]:
    snapshot = load_snapshot(config_path)
    if snapshot is not None:
        return snapshot
    return load_set_projects(config_path)
