"""Localhost resolve UI served while the daemon is ready."""

from __future__ import annotations

import hmac
import html
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from beyond_local_file.held import list_held_copies
from beyond_local_file.model.config import ConfigProject, Mapping
from beyond_local_file.project_processor import load_set_projects

from .catchup import rel_in_items
from .process import resolve_port_path, resolve_token_path
from .store import BaselineTrees, get_state, is_out_of_sync, iter_out_of_sync, load_baseline, load_snapshot

_HOST = "127.0.0.1"
_TOKEN_BYTES = 32
_MAX_PORT = 65535
_SAME_AS_HUB_BG = "#c8e6c9"


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
            query = parse_qs(parsed.query)
            got = (query.get("token") or [""])[0]
            if not got or not hmac.compare_digest(got, token):
                self.send_error(HTTPStatus.UNAUTHORIZED, "Unauthorized")
                return
            project = (query.get("project") or [""])[0]
            rel = (query.get("path") or [""])[0]
            replica = (query.get("replica") or [""])[0]
            body = _page_html(config_path, token=token, project=project, rel=rel, replica=replica).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            del fmt, args

    return Handler


def _page_html(config_path: Path, *, token: str, project: str, rel: str, replica: str) -> str:
    projects = _projects(config_path)
    trees = load_baseline(config_path) or {}
    rows = _nav_rows(projects, trees)
    nav = _nav_html(rows, token)
    detail = _detail_html(projects, trees, token, (project, rel, replica))
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Resolve UI</title>'
        f"<style>{_css()}</style></head><body>"
        f'<nav class="index">{nav}</nav><main>{detail}</main>'
        "</body></html>"
    )


def _css() -> str:
    return (
        "body{display:flex;margin:0;font-family:sans-serif}"
        "nav.index{width:18rem;border-right:1px solid #ccc;padding:1rem;box-sizing:border-box}"
        "nav.index h2{font-size:1rem;margin:1rem 0 .25rem}"
        "nav.index ul,nav.switcher ul{list-style:none;margin:0;padding:0}"
        ".nav-row,.switcher li{margin:.25rem 0;padding:.25rem}"
        ".badge{display:inline-block;margin-left:.4rem;font-size:.8rem;background:#eee;padding:.1rem .4rem}"
        "main{flex:1;padding:1rem;min-width:0}"
        ".panes{display:flex;gap:.5rem;align-items:stretch}"
        ".pane{flex:1;min-width:0;border:1px solid #ddd;padding:.5rem}"
        ".pane pre{white-space:pre-wrap;word-break:break-all;margin:0}"
        "nav.switcher{display:flex;flex-direction:column;min-width:12rem}"
        f".same-as-hub{{background:{_SAME_AS_HUB_BG}}}"
        ".clause,.held p{margin:0 0 1rem}"
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


def _nav_html(rows: list[tuple[str, str, bool, bool]], token: str) -> str:
    if not rows:
        return "<p>None</p>"
    sections: list[str] = []
    current = ""
    items: list[str] = []
    for name, rel, oos, held in rows:
        if name != current:
            if current:
                sections.append(_project_section(current, items))
            current = name
            items = []
        href = html.escape(_detail_href(token, name, rel), quote=True)
        badge = html.escape(_badge(oos, held))
        items.append(
            f'<li class="nav-row"><a href="{href}">{html.escape(rel)}</a><span class="badge">{badge}</span></li>'
        )
    if current:
        sections.append(_project_section(current, items))
    return "".join(sections)


def _project_section(name: str, items: list[str]) -> str:
    return f"<section><h2>{html.escape(name)}</h2><ul>{''.join(items)}</ul></section>"


def _badge(oos: bool, held: bool) -> str:
    if oos and held:
        return "both"
    if oos:
        return "out-of-sync"
    return "held"


def _detail_html(
    projects: dict[str, ConfigProject],
    trees: BaselineTrees,
    token: str,
    selection: tuple[str, str, str],
) -> str:
    project_name, rel, replica_raw = selection
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
        parts.append(_copy_view_html(project, trees, token=token, rel=rel, replica_raw=replica_raw))
    if held:
        clauses = [copy.clause for copy in list_held_copies(project.managed_project_path) if copy.path == rel]
        held_rows = "".join(f"<p>{html.escape(clause)}</p>" for clause in clauses)
        parts.append(f'<section class="held">{held_rows}</section>')
    return "".join(parts)


def _copy_view_html(
    project: ConfigProject,
    trees: BaselineTrees,
    *,
    token: str,
    rel: str,
    replica_raw: str,
) -> str:
    replicas = _replicas_for(project, rel)
    selected = _selected_replica(replicas, trees, rel, replica_raw)
    hub_text = html.escape(_live_text(project.managed_project_path, rel))
    replica_text = html.escape(_live_text(selected, rel)) if selected is not None else ""
    clause = ""
    if selected is not None:
        clause = str(get_state(trees, selected, rel).get("clause") or "")
    clause_html = f'<p class="clause">{html.escape(clause)}</p>' if clause else ""
    switcher = _switcher_html(
        project,
        token=token,
        rel=rel,
        replicas=replicas,
        selected=selected,
    )
    return (
        f'{clause_html}<div class="panes">'
        f'<section class="pane" id="hub-now"><h2>hub-now</h2><pre>{hub_text}</pre></section>'
        '<section class="pane" id="result"></section>'
        f'<section class="pane" id="replica-now"><h2>replica-now</h2><pre>{replica_text}</pre></section>'
        f'<nav class="switcher">{switcher}</nav>'
        "</div>"
    )


def _switcher_html(
    project: ConfigProject,
    *,
    token: str,
    rel: str,
    replicas: list[Path],
    selected: Path | None,
) -> str:
    hub = project.managed_project_path
    items: list[str] = []
    for replica in replicas:
        href = html.escape(_detail_href(token, project.managed_project_name, rel, replica.as_posix()), quote=True)
        classes = []
        if selected is not None and _same_path(replica, selected):
            classes.append("selected")
        same = _same_as_hub(hub, replica, rel)
        if same:
            classes.append("same-as-hub")
        class_attr = f' class="{" ".join(classes)}"' if classes else ""
        label = html.escape(replica.as_posix())
        extra = " same as hub" if same else ""
        items.append(f'<li{class_attr}><a href="{href}">{label}</a>{extra}</li>')
    return f"<ul>{''.join(items)}</ul>"


def _selected_replica(replicas: list[Path], trees: BaselineTrees, rel: str, replica_raw: str) -> Path | None:
    matched = _match_replica(replicas, replica_raw)
    if matched is not None:
        return matched
    for replica in replicas:
        if is_out_of_sync(get_state(trees, replica, rel)):
            return replica
    return replicas[0] if replicas else None


def _replicas_for(project: ConfigProject, rel: str) -> list[Path]:
    found: dict[str, Path] = {}
    for mapping in project.mappings:
        if not _mapping_has_rel(mapping, rel):
            continue
        for target in mapping.targets:
            resolved = target.resolve()
            found[resolved.as_posix()] = resolved
    return [found[key] for key in sorted(found)]


def _match_replica(replicas: list[Path], raw: str) -> Path | None:
    if not raw:
        return None
    wanted = Path(raw)
    for replica in replicas:
        if replica == wanted or replica.as_posix() == wanted.as_posix():
            return replica
        try:
            if replica.resolve() == wanted.resolve():
                return replica
        except OSError:
            continue
    return None


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


def _live_text(root: Path, rel: str) -> str:
    path = root / rel
    if path.is_file() and not path.is_symlink():
        return path.read_bytes().decode("latin-1")
    return ""


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


def _detail_href(token: str, project: str, rel: str, replica: str | None = None) -> str:
    query = {"token": token, "project": project, "path": rel}
    if replica:
        query["replica"] = replica
    return "/?" + urlencode(query)


def _projects(config_path: Path) -> dict[str, ConfigProject]:
    snapshot = load_snapshot(config_path)
    if snapshot is not None:
        return snapshot
    return load_set_projects(config_path)
