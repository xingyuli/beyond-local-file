"""Resolve UI HTTP and non-TTY status seams."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http import HTTPStatus
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPErrorProcessor, Request, build_opener, urlopen

import pytest

from beyond_local_file.daemon.live import LiveSync
from beyond_local_file.daemon.process import port_path, state_dir
from beyond_local_file.daemon.screen import _ShellScreen
from beyond_local_file.held import REASON_DELETE_GAP, list_held_copies, store_held_copy
from tests.daemon_support import invoke_cli, start_daemon, stop_daemon
from tests.unit.test_out_of_sync_and_held import (
    _live_sync,
    _mark_loser_out_of_sync,
    _persist,
    _stale_base_clause,
    _write_two_target_workspace,
)

_READY_WAIT_S = 15.0
_POLL_S = 0.05
_HOLD_ENV = "BLF_TEST_CATCHUP_HOLD"
_REPO_ROOT = Path(__file__).resolve().parents[2]
RESOLVE_PORT_NAME = "resolve.port"
RESOLVE_TOKEN_NAME = "resolve.token"


def _resolve_port_path(config_path: Path) -> Path:
    return state_dir(config_path) / RESOLVE_PORT_NAME


def _resolve_token_path(config_path: Path) -> Path:
    return state_dir(config_path) / RESOLVE_TOKEN_NAME


def _wait_until(predicate, *, timeout: float = _READY_WAIT_S) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(_POLL_S)
    raise TimeoutError("condition was not met")


def _read_int_file(path: Path) -> int | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    return int(text.splitlines()[0])


def _read_token(config_path: Path) -> str:
    return _resolve_token_path(config_path).read_text(encoding="utf-8").strip()


def _resolve_url(
    config_path: Path,
    *,
    token: str | None = None,
    project: str | None = None,
    path: str | None = None,
) -> str:
    port = _read_int_file(_resolve_port_path(config_path))
    assert port is not None
    if token is None:
        token = _read_token(config_path)
    query: dict[str, str] = {"token": token}
    if project is not None:
        query["project"] = project
    if path is not None:
        query["path"] = path
    return f"http://127.0.0.1:{port}/?{urlencode(query)}"


def _get(url: str) -> tuple[int, str]:
    try:
        with urlopen(url, timeout=3) as response:
            return response.status, response.read().decode("utf-8")
    except HTTPError as error:
        return error.code, error.read().decode("utf-8")


class _NoRedirect(HTTPErrorProcessor):
    """An error processor that returns 3xx responses as-is instead of following them."""

    def http_response(self, request: Request, response: object) -> object:
        return response

    https_response = http_response


def _get_no_redirect(url: str) -> tuple[int, str]:
    opener = build_opener(_NoRedirect)
    with opener.open(url, timeout=3) as response:
        return response.status, response.headers.get("Location", "")


def _post(url: str, payload: dict) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=15) as response:
            return response.status, response.read().decode("utf-8")
    except HTTPError as error:
        return error.code, error.read().decode("utf-8")


def _resolve_state(body: str) -> dict:
    match = re.search(r'<script type="application/json" id="resolve-state">(.*?)</script>', body, re.DOTALL)
    assert match is not None, "missing resolve-state JSON"
    return json.loads(match.group(1))


def _replica_by_path(state: dict, path: Path) -> dict:
    for replica in state["replicas"]:
        if replica["path"] == path.as_posix():
            return replica
    raise AssertionError(f"{path.as_posix()} not in replicas: {state['replicas']}")


def _file_snapshot(paths: list[Path]) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in paths}


def _prepare_isolation(tmp_path: Path) -> tuple[LiveSync, Path, Path, Path, Path, Path]:
    config_path, managed, target_a, target_b = _write_two_target_workspace(tmp_path)
    live = _live_sync(config_path)
    _mark_loser_out_of_sync(live, target_a, target_b)
    sidecar = tmp_path / "hub-bytes.txt"
    sidecar.write_text("kept-hub-bytes")
    slot = store_held_copy(
        managed,
        rel_path=Path("shared.txt"),
        source=sidecar,
        replica=target_b,
        reason=REASON_DELETE_GAP,
    )
    _persist(config_path, live)
    return live, config_path, managed, target_a, target_b, slot


@contextmanager
def _ready_resolve_ui(
    config_path: Path,
    isolated_home: dict[str, str],
    extra_env: dict[str, str] | None = None,
) -> Iterator[None]:
    """Start a ready daemon that serves the resolve UI, then stop it."""
    env = {**isolated_home, **(extra_env or {})}
    start_daemon(config_path, env)
    try:
        _wait_until(lambda: _resolve_port_path(config_path).is_file())
        yield
    finally:
        stop_daemon(config_path, env)


def _write_two_managed_workspace(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path, Path, Path]:
    """Create lab-app and alpha, each with two targets and shared.txt."""
    lab = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    lab_a = tmp_path / "lab-app-a"
    lab_b = tmp_path / "lab-app-b"
    alpha_a = tmp_path / "alpha-a"
    alpha_b = tmp_path / "alpha-b"
    for directory in (lab, alpha, lab_a, lab_b, alpha_a, alpha_b):
        directory.mkdir()
    (lab / "shared.txt").write_text("v0")
    (alpha / "shared.txt").write_text("v0")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"lab-app:\n  - {lab_a}\n  - {lab_b}\nalpha:\n  - {alpha_a}\n  - {alpha_b}\n")
    return config_path, lab, lab_a, lab_b, alpha, alpha_a, alpha_b


def _write_three_target_workspace(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    """Create one managed project with three target replicas and a shared file."""
    managed = tmp_path / "proj"
    target_a = tmp_path / "target-a"
    target_b = tmp_path / "target-b"
    target_c = tmp_path / "target-c"
    for directory in (managed, target_a, target_b, target_c):
        directory.mkdir()
    (managed / "shared.txt").write_text("v0")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"proj:\n  - {target_a}\n  - {target_b}\n  - {target_c}\n")
    return config_path, managed, target_a, target_b, target_c


def _mark_three_out_of_sync(live: LiveSync, target_a: Path, target_b: Path, target_c: Path) -> None:
    """Three replicas edit the same path; first apply wins and the others are isolated."""
    (target_a / "shared.txt").write_text("from-a")
    (target_b / "shared.txt").write_text("from-b")
    (target_c / "shared.txt").write_text("from-c")
    live.tick()


def _prepare_two_managed_out_of_sync(tmp_path: Path) -> Path:
    """Two managed projects, each with the same relative path out-of-sync."""
    config_path, _lab, lab_a, lab_b, _alpha, alpha_a, alpha_b = _write_two_managed_workspace(tmp_path)
    live = _live_sync(config_path)
    (lab_a / "shared.txt").write_text("from-a")
    (lab_b / "shared.txt").write_text("from-b")
    (alpha_a / "shared.txt").write_text("from-a")
    (alpha_b / "shared.txt").write_text("from-b")
    live.tick()
    _persist(config_path, live)
    return config_path


def _prepare_three_target_out_of_sync(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """One path out-of-sync on two replicas; the winner stays in-sync."""
    config_path, _managed, target_a, target_b, target_c = _write_three_target_workspace(tmp_path)
    live = _live_sync(config_path)
    _mark_three_out_of_sync(live, target_a, target_b, target_c)
    _persist(config_path, live)
    return config_path, target_a, target_b, target_c


def _prepare_held_only(tmp_path: Path) -> tuple[Path, Path]:
    """Held copy of shared.txt with no out-of-sync replica."""
    config_path, managed, _target_a, target_b = _write_two_target_workspace(tmp_path)
    live = _live_sync(config_path)
    sidecar = tmp_path / "hub-bytes.txt"
    sidecar.write_text("kept-hub-bytes")
    store_held_copy(
        managed,
        rel_path=Path("shared.txt"),
        source=sidecar,
        replica=target_b,
        reason=REASON_DELETE_GAP,
    )
    _persist(config_path, live)
    return config_path, target_b


def _prepare_oos_text(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Two-target race: hub from-a, first out-of-sync replica from-b."""
    config_path, managed, target_a, target_b = _write_two_target_workspace(tmp_path)
    live = _live_sync(config_path)
    _mark_loser_out_of_sync(live, target_a, target_b)
    _persist(config_path, live)
    return config_path, managed, target_a, target_b


def _prepare_two_oos_paths(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Two items each isolated on target-b after a lost compare-and-swap."""
    config_path, managed, target_a, target_b = _write_two_target_workspace(tmp_path)
    (managed / "other.txt").write_text("other-v0")
    live = _live_sync(config_path)
    _mark_loser_out_of_sync(live, target_a, target_b)
    (target_a / "other.txt").write_text("other-a")
    (target_b / "other.txt").write_text("other-b")
    live.tick()
    _persist(config_path, live)
    return config_path, managed, target_a, target_b


def _project_section(body: str, name: str) -> str:
    """Return the nav section HTML grouped under *name*."""
    match = re.search(rf"<h2>{re.escape(name)}</h2>(.*?)</section>", body, re.DOTALL)
    assert match is not None, f"missing managed project group {name!r}"
    return match.group(1)


def _nav_pane_html(body: str, pane: str) -> str:
    """Return the HTML inside the ``out-of-sync`` or ``held`` top nav pane (``pane`` is ``oos``/``held``)."""
    match = re.search(rf'<div class="nav-pane" id="nav-pane-{pane}">(.*?)</div>', body, re.DOTALL)
    assert match is not None, f"missing nav pane {pane!r}"
    return match.group(1)


def test_ready_daemon_serves_resolve_ui_with_token_and_rejects_without(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A ready daemon serves the resolve UI on localhost; a request without the token is rejected."""
    _live, config_path, _managed, _target_a, _target_b, _slot = _prepare_isolation(tmp_path)
    start_daemon(config_path, isolated_home)
    try:
        _wait_until(lambda: _resolve_port_path(config_path).is_file())
        token = _read_token(config_path)
        assert token
        status, body = _get(_resolve_url(config_path))
        assert status == HTTPStatus.OK
        assert "shared.txt" in body
        assert "proj" in body
        # shared.txt is both out-of-sync and held, so it is listed in both top nav panes.
        assert "shared.txt" in _project_section(_nav_pane_html(body, "oos"), "proj")
        assert "shared.txt" in _project_section(_nav_pane_html(body, "held"), "proj")
        ipc_port = _read_int_file(port_path(config_path))
        resolve_port = _read_int_file(_resolve_port_path(config_path))
        assert ipc_port is not None and resolve_port is not None
        assert ipc_port != resolve_port
        denied, _body = _get(f"http://127.0.0.1:{resolve_port}/")
        assert denied == HTTPStatus.UNAUTHORIZED
        wrong, _wrong_body = _get(_resolve_url(config_path, token="not-the-token"))
        assert wrong == HTTPStatus.UNAUTHORIZED
    finally:
        port = _read_int_file(_resolve_port_path(config_path))
        stop_daemon(config_path, isolated_home)
    assert not _resolve_port_path(config_path).exists()
    assert not _resolve_token_path(config_path).exists()
    assert port is not None
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe,
        pytest.raises(ConnectionRefusedError),
    ):
        probe.connect(("127.0.0.1", port))


def test_catch_up_does_not_serve_resolve_ui(tmp_path: Path, isolated_home: dict[str, str]) -> None:
    """HTTP is not bound during catch-up; JSON IPC stays on daemon.port."""
    config_path, _managed, _target_a, _target_b = _write_two_target_workspace(tmp_path)
    hold = tmp_path / "catchup.hold"
    hold.write_text("hold\n", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "beyond_local_file", "--config", str(config_path), "daemon", "start"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        env={**os.environ, **isolated_home, _HOLD_ENV: str(hold)},
    )
    try:
        _wait_until(lambda: port_path(config_path).is_file())
        assert not _resolve_port_path(config_path).exists()
        assert not _resolve_token_path(config_path).exists()
        ipc_port = _read_int_file(port_path(config_path))
        assert ipc_port is not None
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(1)
            probe.connect(("127.0.0.1", ipc_port))
    finally:
        hold.unlink(missing_ok=True)
        stdout, stderr = proc.communicate(timeout=_READY_WAIT_S)
        stop_daemon(config_path, isolated_home)
    assert proc.returncode == 0, stdout + stderr
    assert not _resolve_port_path(config_path).exists()


def test_non_tty_status_with_isolation_prints_url_and_does_not_open_browser(
    tmp_path: Path,
    isolated_home: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-TTY status with isolation prints the URL and does not open a browser."""
    opened: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url, *args, **kwargs: opened.append(url))
    _live, config_path, _managed, _target_a, _target_b, _slot = _prepare_isolation(tmp_path)
    start_daemon(config_path, isolated_home)
    try:
        _wait_until(lambda: _resolve_port_path(config_path).is_file())
        result = invoke_cli(["--config", str(config_path), "daemon", "status"], env=isolated_home)
        url = _resolve_url(config_path)
    finally:
        stop_daemon(config_path, isolated_home)
    assert result.exit_code == 0, result.output
    assert url in result.output
    assert "http://127.0.0.1:" in result.output
    assert opened == []


def test_non_tty_status_without_isolation_does_not_print_url(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Non-TTY status with no isolation does not print a resolve UI URL."""
    config_path, _managed, _target_a, _target_b = _write_two_target_workspace(tmp_path)
    start_daemon(config_path, isolated_home)
    try:
        _wait_until(lambda: _resolve_port_path(config_path).is_file())
        result = invoke_cli(["--config", str(config_path), "daemon", "status"], env=isolated_home)
    finally:
        stop_daemon(config_path, isolated_home)
    assert result.exit_code == 0, result.output
    assert "http://" not in result.output
    assert "token=" not in result.output
    assert "Daemon is running" in result.output


def test_status_when_daemon_down_is_unchanged_and_prints_no_url(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Daemon not running: status is unchanged and no page or URL is served."""
    _live, config_path, _managed, _target_a, _target_b, _slot = _prepare_isolation(tmp_path)
    result = invoke_cli(["--config", str(config_path), "daemon", "status"], env=isolated_home)
    assert result.exit_code == 0, result.output
    assert "Daemon is not running" in result.output
    assert "http://" not in result.output
    assert not _resolve_port_path(config_path).exists()
    assert not _resolve_token_path(config_path).exists()


def test_finished_status_o_opens_browser_and_closes_the_screen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pressing o on a finished status screen opens the resolve UI and closes."""
    opened: list[str] = []
    monkeypatch.setattr(
        "beyond_local_file.daemon.screen.webbrowser.open",
        lambda url, *args, **kwargs: opened.append(url) or True,
    )
    url = "http://127.0.0.1:9/?token=abc"
    screen = _ShellScreen("1  ready", single=False, fallback="", op="status", trailer=(url,))
    screen.finish(
        {
            "exit_code": 0,
            "stdout": "Daemon is running (pid 1, phase ready)\n",
            "pid": 1,
            "phase": "ready",
        }
    )
    assert screen._hint_text() == "o: open  q: close"
    screen._on_key("o", None)
    assert opened == [url]
    assert screen._closed


def test_two_managed_projects_same_rel_are_two_nav_rows_grouped_by_name(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Two managed projects with the same relative path are two nav rows, grouped by name."""
    config_path = _prepare_two_managed_out_of_sync(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        status, body = _get(_resolve_url(config_path))
    assert status == HTTPStatus.OK
    lab = _project_section(body, "lab-app")
    alpha = _project_section(body, "alpha")
    assert lab.count('class="nav-row"') == 1
    assert alpha.count('class="nav-row"') == 1
    assert "shared.txt" in lab
    assert "shared.txt" in alpha
    assert "project=lab-app" in lab
    assert "project=alpha" in alpha
    assert "token=" in lab
    assert "token=" in alpha


def test_several_out_of_sync_replicas_are_one_nav_row_and_the_state_lists_every_target(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Several out-of-sync replicas of one path are one nav row; the state lists every target."""
    config_path, target_a, target_b, target_c = _prepare_three_target_out_of_sync(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        status, body = _get(_resolve_url(config_path, project="proj", path="shared.txt"))
    assert status == HTTPStatus.OK
    assert body.count('class="nav-row"') == 1
    assert "shared.txt" in _project_section(body, "proj")
    state = _resolve_state(body)
    paths = {replica["path"] for replica in state["replicas"]}
    assert {target_a.as_posix(), target_b.as_posix(), target_c.as_posix()} == paths
    assert _replica_by_path(state, target_a)["same_as_hub"] is True


def test_state_hub_now_and_pending_replicas_exclude_same_as_hub(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """hub_now is from the winner; replicas that live-match hub are flagged same_as_hub."""
    config_path, target_a, target_b, target_c = _prepare_three_target_out_of_sync(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        status, body = _get(_resolve_url(config_path, project="proj", path="shared.txt"))
    assert status == HTTPStatus.OK
    state = _resolve_state(body)
    assert "from-a" in state["hub_now"]
    a = _replica_by_path(state, target_a)
    b = _replica_by_path(state, target_b)
    c = _replica_by_path(state, target_c)
    assert a["same_as_hub"] is True
    assert "from-a" in a["text"]
    assert b["same_as_hub"] is False
    assert "from-b" in b["text"]
    assert c["same_as_hub"] is False
    assert "from-c" in c["text"]
    assert "source" not in body.lower()


def test_reason_clause_is_carried_per_replica(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Each out-of-sync replica carries its own reason clause in the state, not just the first."""
    config_path, target_a, target_b, target_c = _prepare_three_target_out_of_sync(tmp_path)
    clause_b = _stale_base_clause(target_b, target_a)
    clause_c = _stale_base_clause(target_c, target_a)
    with _ready_resolve_ui(config_path, isolated_home):
        status, body = _get(_resolve_url(config_path, project="proj", path="shared.txt"))
    assert status == HTTPStatus.OK
    state = _resolve_state(body)
    assert _replica_by_path(state, target_b)["clause"] == clause_b
    assert _replica_by_path(state, target_c)["clause"] == clause_c
    assert _replica_by_path(state, target_a)["clause"] == ""


def test_held_only_path_shows_hold_reason_and_no_copy_view(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A held-only path shows its hold-reason clause(s) and no resolve app mount."""
    config_path, _target_b = _prepare_held_only(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        index_status, index_body = _get(_resolve_url(config_path))
        status, body = _get(_resolve_url(config_path, project="proj", path="shared.txt"))
    assert index_status == HTTPStatus.OK
    assert "shared.txt" in _project_section(_nav_pane_html(index_body, "held"), "proj")
    assert status == HTTPStatus.OK
    assert "delete applied past the generation window" in body
    assert 'id="resolve-app"' not in body
    assert 'id="resolve-state"' not in body
    assert "from-a" not in body
    assert "from-b" not in body


def test_path_both_out_of_sync_and_held_shows_copy_view_and_hold_clauses(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A path that is both out-of-sync and held shows the copy view and hold-reason clauses."""
    _live, config_path, _managed, target_a, target_b, _slot = _prepare_isolation(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        index_status, index_body = _get(_resolve_url(config_path))
        status, body = _get(_resolve_url(config_path, project="proj", path="shared.txt"))
    assert index_status == HTTPStatus.OK
    assert "shared.txt" in _project_section(_nav_pane_html(index_body, "oos"), "proj")
    assert "shared.txt" in _project_section(_nav_pane_html(index_body, "held"), "proj")
    assert status == HTTPStatus.OK
    assert 'id="resolve-app"' in body
    state = _resolve_state(body)
    assert "from-a" in state["hub_now"]
    assert "from-b" in _replica_by_path(state, target_b)["text"]
    assert _stale_base_clause(target_b, target_a) in body
    assert "delete applied past the generation window" in body


def test_selected_path_is_highlighted_not_labeled_and_survives_reload(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """The open nav row carries a data-current marker for CSS; unselected rows do not."""
    config_path = _prepare_two_managed_out_of_sync(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        status, body = _get(_resolve_url(config_path, project="alpha", path="shared.txt"))
    assert status == HTTPStatus.OK
    lab = _project_section(body, "lab-app")
    alpha = _project_section(body, "alpha")
    assert 'data-current="true"' not in lab
    assert 'data-current="true"' in alpha


def test_nav_tab_switcher_is_left_out_when_only_one_category_has_items(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """No tab switcher renders when every row is out-of-sync (or every row is held) — nothing to pick."""
    oos_root = tmp_path / "oos-only"
    held_root = tmp_path / "held-only"
    oos_root.mkdir()
    held_root.mkdir()
    oos_only_config, _managed, _target_a, _target_b = _prepare_oos_text(oos_root)
    held_only_config, _target_b2 = _prepare_held_only(held_root)
    with _ready_resolve_ui(oos_only_config, isolated_home):
        oos_status, oos_body = _get(_resolve_url(oos_only_config))
    with _ready_resolve_ui(held_only_config, isolated_home):
        held_status, held_body = _get(_resolve_url(held_only_config))
    assert oos_status == HTTPStatus.OK
    assert held_status == HTTPStatus.OK
    assert 'class="nav-tabs"' not in oos_body
    assert 'class="nav-tabs"' not in held_body
    assert "shared.txt" in _nav_pane_html(oos_body, "oos")
    assert "shared.txt" in _nav_pane_html(held_body, "held")


def test_index_without_selection_redirects_to_the_first_out_of_sync_row(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """GET with no project/path redirects to the first out-of-sync row, as if it had been clicked."""
    config_path = _prepare_two_managed_out_of_sync(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        token = _read_token(config_path)
        status, location = _get_no_redirect(_resolve_url(config_path, token=token))
    assert status == HTTPStatus.FOUND
    # "alpha" sorts before "lab-app"; both have shared.txt out-of-sync.
    assert "project=alpha" in location
    assert "path=shared.txt" in location
    assert f"token={token}" in location


def test_index_without_selection_redirects_to_a_held_row_when_nothing_is_out_of_sync(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """GET with no project/path falls back to a held row when there is no out-of-sync row at all."""
    config_path, _target_b = _prepare_held_only(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        token = _read_token(config_path)
        status, location = _get_no_redirect(_resolve_url(config_path, token=token))
    assert status == HTTPStatus.FOUND
    assert "project=proj" in location
    assert "path=shared.txt" in location


def test_nav_tab_switcher_shown_and_defaults_to_the_selected_path_s_category(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """When both categories have rows, the switcher shows and opens on the selected path's tab."""
    config_path, _managed, _target_a, _target_b, _slot = _prepare_isolation(tmp_path)[1:]
    with _ready_resolve_ui(config_path, isolated_home):
        status, body = _get(_resolve_url(config_path, project="proj", path="shared.txt"))
    assert status == HTTPStatus.OK
    assert 'class="nav-tabs"' in body
    assert 'id="nav-tab-oos" class="nav-tab-radio" checked' in body


def test_nav_includes_a_collapse_control(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Every resolve page has a sidebar collapse control at the top of the left nav."""
    config_path, _managed, _target_a, _target_b = _prepare_oos_text(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        status, body = _get(_resolve_url(config_path, project="proj", path="shared.txt"))
    assert status == HTTPStatus.OK
    assert 'id="nav-toggle"' in body
    assert 'id="nav-toggle-keys"' in body
    assert 'id="nav-body"' in body
    assert 'aria-controls="nav-body"' in body


def test_cli_reference_describes_nav_toolbar_row_and_same_as_hub() -> None:
    """docs/cli-reference.md describes the nav, the toolbar row of replica chips, and same as hub."""
    text = (_REPO_ROOT / "docs" / "cli-reference.md").read_text(encoding="utf-8")
    assert "grouped by managed project name" in text
    assert "toolbar row" in text
    assert "same as hub" in text


def test_opening_oos_text_path_embeds_hub_and_first_pending_replica_text(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Opening an out-of-sync text path embeds hub-now and every replica's live text; no server hunks."""
    config_path, _managed, _target_a, _target_b = _prepare_oos_text(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        status, body = _get(_resolve_url(config_path, project="proj", path="shared.txt"))
    assert status == HTTPStatus.OK
    state = _resolve_state(body)
    assert state["binary"] is False
    assert "from-a" in state["hub_now"]
    pending = [replica for replica in state["replicas"] if not replica["same_as_hub"]]
    assert pending
    assert "from-b" in pending[0]["text"]
    assert "hunks" not in state
    assert "middle" not in state
    assert "ancestor" not in state


def test_text_detail_references_vendored_assets_and_resolve_app_no_cdn(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """An out-of-sync text path mounts #resolve-app and references vendored + app static assets, not a CDN."""
    config_path, _managed, _target_a, _target_b = _prepare_oos_text(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        status, body = _get(_resolve_url(config_path, project="proj", path="shared.txt"))
    assert status == HTTPStatus.OK
    assert '<script src="/static/vendor/codemirror.js">' in body
    assert '<script src="/static/vendor/diff_match_patch.js">' in body
    assert '<script src="/static/vendor/merge.js">' in body
    assert '<script src="/static/app.js">' in body
    assert '<link rel="stylesheet" href="/static/vendor/codemirror.css">' in body
    assert '<link rel="stylesheet" href="/static/vendor/merge.css">' in body
    assert '<link rel="stylesheet" href="/static/app.css">' in body
    assert "cdn." not in body.lower()
    assert "unpkg.com" not in body
    assert "jsdelivr" not in body
    assert 'id="resolve-app"' in body
    # The interactive markup (mark as merged, submit, CodeMirror.MergeView call) is built by
    # app.js at runtime in the browser; a plain HTTP fetch never executes it, so it correctly
    # does not appear in the server-rendered body.
    assert "CodeMirror.MergeView" not in body


def test_source_is_shown_as_plain_text_not_rendered_markdown(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Source bytes are embedded as plain text for the client editor, not rendered Markdown."""
    config_path, managed, target_a, target_b = _write_two_target_workspace(tmp_path)
    (managed / "shared.txt").write_text("# Heading\n\nv0\n")
    live = _live_sync(config_path)
    (target_a / "shared.txt").write_text("# Heading\n\nfrom-a\n")
    (target_b / "shared.txt").write_text("# Heading\n\nfrom-b\n")
    live.tick()
    _persist(config_path, live)
    with _ready_resolve_ui(config_path, isolated_home):
        status, body = _get(_resolve_url(config_path, project="proj", path="shared.txt"))
    assert status == HTTPStatus.OK
    assert "<h1>" not in body
    assert "<strong>" not in body
    state = _resolve_state(body)
    assert "# Heading" in state["hub_now"]
    pending = [replica for replica in state["replicas"] if not replica["same_as_hub"]]
    assert any("# Heading" in replica["text"] for replica in pending)


def test_common_path_prefix_is_collapsed_across_replicas(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Replica paths sharing a leading directory are collapsed to a common_prefix plus short labels."""
    config_path, target_a, target_b, target_c = _prepare_three_target_out_of_sync(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        status, body = _get(_resolve_url(config_path, project="proj", path="shared.txt"))
    assert status == HTTPStatus.OK
    state = _resolve_state(body)
    prefix = state["common_prefix"]
    assert prefix
    assert target_a.as_posix().startswith(prefix)
    assert target_b.as_posix().startswith(prefix)
    assert target_c.as_posix().startswith(prefix)
    for replica in state["replicas"]:
        assert replica["label"] == replica["path"][len(prefix) :]
        assert prefix not in replica["label"]


def test_static_vendor_and_app_assets_are_served_with_content_type(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Vendored and app static assets are served with the right content type; unknown names 404."""
    config_path, _managed, _target_a, _target_b = _write_two_target_workspace(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        port = _read_int_file(_resolve_port_path(config_path))
        assert port is not None
        js_status, js_body = _get(f"http://127.0.0.1:{port}/static/vendor/codemirror.js")
        css_status, css_body = _get(f"http://127.0.0.1:{port}/static/vendor/merge.css")
        app_js_status, app_js_body = _get(f"http://127.0.0.1:{port}/static/app.js")
        app_css_status, app_css_body = _get(f"http://127.0.0.1:{port}/static/app.css")
        missing_status, _missing_body = _get(f"http://127.0.0.1:{port}/static/vendor/does-not-exist.js")
        traversal_status, _traversal_body = _get(f"http://127.0.0.1:{port}/static/vendor/..%2F..%2Fpyproject.toml")
    assert js_status == HTTPStatus.OK
    assert "CodeMirror" in js_body
    assert css_status == HTTPStatus.OK
    assert len(css_body) > 0
    assert app_js_status == HTTPStatus.OK
    assert "resolve-state" in app_js_body
    assert app_css_status == HTTPStatus.OK
    assert len(app_css_body) > 0
    assert missing_status == HTTPStatus.NOT_FOUND
    assert traversal_status == HTTPStatus.NOT_FOUND


def test_static_assets_require_no_token(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Static assets are public (no token needed); the page and JSON API still are."""
    config_path, _managed, _target_a, _target_b = _write_two_target_workspace(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        port = _read_int_file(_resolve_port_path(config_path))
        assert port is not None
        status, body = _get(f"http://127.0.0.1:{port}/static/vendor/diff_match_patch.js")
    assert status == HTTPStatus.OK
    assert len(body) > 0


def test_utf8_source_is_shown_as_characters(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """UTF-8 hub-now and replica text are shown as characters, not latin-1 mojibake."""
    config_path, managed, target_a, target_b = _write_two_target_workspace(tmp_path)
    (managed / "shared.txt").write_text("祖先\n", encoding="utf-8")
    live = _live_sync(config_path)
    (target_a / "shared.txt").write_text("从甲\n", encoding="utf-8")
    (target_b / "shared.txt").write_text("从乙\n", encoding="utf-8")
    live.tick()
    _persist(config_path, live)
    with _ready_resolve_ui(config_path, isolated_home):
        status, body = _get(_resolve_url(config_path, project="proj", path="shared.txt"))
    assert status == HTTPStatus.OK
    state = _resolve_state(body)
    assert "从甲" in state["hub_now"]
    assert "从乙" in _replica_by_path(state, target_b)["text"]


def test_binary_path_shows_hash_and_size_for_hub_and_every_replica(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A binary path's state carries hash and size for hub and every replica; no text field."""
    config_path, managed, target_a, target_b = _write_two_target_workspace(tmp_path)
    (managed / "shared.txt").write_bytes(b"v0\x00")
    live = _live_sync(config_path)
    (target_a / "shared.txt").write_bytes(b"from-a\x00")
    (target_b / "shared.txt").write_bytes(b"from-b\x00")
    live.tick()
    _persist(config_path, live)
    hub_bytes = (managed / "shared.txt").read_bytes()
    replica_bytes = (target_b / "shared.txt").read_bytes()
    with _ready_resolve_ui(config_path, isolated_home):
        status, body = _get(_resolve_url(config_path, project="proj", path="shared.txt"))
    assert status == HTTPStatus.OK
    state = _resolve_state(body)
    assert state["binary"] is True
    assert state["hub_hash"] == hashlib.sha256(hub_bytes).hexdigest()
    assert state["hub_size"] == len(hub_bytes)
    replica_b = _replica_by_path(state, target_b)
    assert replica_b["hash"] == hashlib.sha256(replica_bytes).hexdigest()
    assert replica_b["size"] == len(replica_bytes)
    assert "text" not in replica_b


def test_submit_writes_confirmed_fact_as_hub_generation_and_every_replica(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """POST submit writes the confirmed fact to the hub and every replica of that item."""
    config_path, managed, target_a, target_b = _prepare_oos_text(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        url = _resolve_url(config_path, project="proj", path="shared.txt")
        status, raw = _post(url, {"action": "submit", "middle": "confirmed fact", "binary": False})
    assert status == HTTPStatus.OK
    data = json.loads(raw)
    assert data["ok"] is True
    assert data["applied"] is True
    assert (managed / "shared.txt").read_text() == "confirmed fact"
    assert (target_a / "shared.txt").read_text() == "confirmed fact"
    assert (target_b / "shared.txt").read_text() == "confirmed fact"


def test_submit_clears_out_of_sync_for_that_path_only(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Resolve clears out-of-sync for the submitted path and leaves other paths isolated."""
    config_path, managed, target_a, target_b = _prepare_two_oos_paths(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        url = _resolve_url(config_path, project="proj", path="shared.txt")
        status, raw = _post(url, {"action": "submit", "middle": "confirmed fact", "binary": False})
        assert status == HTTPStatus.OK
        assert json.loads(raw)["applied"] is True
        body_status, body = _get(_resolve_url(config_path))
    assert (managed / "shared.txt").read_text() == "confirmed fact"
    assert (target_a / "shared.txt").read_text() == "confirmed fact"
    assert (target_b / "shared.txt").read_text() == "confirmed fact"
    assert (target_b / "other.txt").read_text() == "other-b"
    assert (managed / "other.txt").read_text() == "other-a"
    assert body_status == HTTPStatus.OK
    oos_pane = _nav_pane_html(body, "oos")
    assert "other.txt" in oos_pane
    assert "shared.txt" not in oos_pane


def test_submit_does_not_hold_discarded_isolated_bytes(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Isolated replica bytes that did not enter the confirmed fact are gone and not held."""
    config_path, managed, target_a, target_b = _prepare_oos_text(tmp_path)
    isolated = (target_b / "shared.txt").read_bytes()
    assert isolated == b"from-b"
    with _ready_resolve_ui(config_path, isolated_home):
        url = _resolve_url(config_path, project="proj", path="shared.txt")
        status, raw = _post(url, {"action": "submit", "middle": "confirmed fact", "binary": False})
    assert status == HTTPStatus.OK
    assert json.loads(raw)["applied"] is True
    assert (target_b / "shared.txt").read_text() == "confirmed fact"
    assert list_held_copies(managed) == ()
    held_root = tmp_path / "home" / ".blf" / "held"
    if held_root.is_dir():
        leftover = [path.read_bytes() for path in held_root.rglob("content") if path.is_file()]
        assert isolated not in leftover
    assert (target_a / "shared.txt").read_text() == "confirmed fact"


def test_later_hub_edit_skips_remaining_out_of_sync_replicas_on_other_paths(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A later live hub edit still skips remaining out-of-sync replicas on other paths."""
    config_path, managed, target_a, target_b = _prepare_two_oos_paths(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home, extra_env={"BLF_IDLE_OBSERVE_S": "0.2"}):
        url = _resolve_url(config_path, project="proj", path="shared.txt")
        status, raw = _post(url, {"action": "submit", "middle": "confirmed fact", "binary": False})
        assert status == HTTPStatus.OK
        assert json.loads(raw)["applied"] is True
        (managed / "other.txt").write_text("hub-later")
        _wait_until(lambda: (target_a / "other.txt").read_text() == "hub-later")
        assert (target_b / "other.txt").read_text() == "other-b"
    assert (managed / "shared.txt").read_text() == "confirmed fact"
    assert (target_b / "shared.txt").read_text() == "confirmed fact"


def test_submit_fails_clearly_when_worker_unit_cannot_take_the_op(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """POST submit returns an error JSON and writes nothing when no worker unit owns the project."""
    config_path, managed, target_a, target_b = _prepare_oos_text(tmp_path)
    paths = [managed / "shared.txt", target_a / "shared.txt", target_b / "shared.txt"]
    before = _file_snapshot(paths)
    with _ready_resolve_ui(config_path, isolated_home):
        url = _resolve_url(config_path, project="proj", path="shared.txt")
        status, raw = _post(
            url,
            {
                "action": "submit",
                "project": "no-such-project",
                "path": "shared.txt",
                "middle": "confirmed fact",
                "binary": False,
            },
        )
    assert status == HTTPStatus.OK
    data = json.loads(raw)
    assert data["ok"] is False
    assert "worker unit" in data["error"]
    assert _file_snapshot(paths) == before


def test_submit_fails_when_daemon_is_down(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """POST submit fails at the HTTP seam when the daemon is not serving."""
    config_path, managed, target_a, target_b = _prepare_oos_text(tmp_path)
    paths = [managed / "shared.txt", target_a / "shared.txt", target_b / "shared.txt"]
    before = _file_snapshot(paths)
    with _ready_resolve_ui(config_path, isolated_home):
        url = _resolve_url(config_path, project="proj", path="shared.txt")
    with pytest.raises(URLError):
        _post(url, {"action": "submit", "middle": "confirmed fact", "binary": False})
    assert _file_snapshot(paths) == before


def test_nav_leaves_once_the_path_is_resolved(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """After resolve, the path is gone from the nav; landing shows remaining work or none."""
    config_path, _managed, _target_a, _target_b = _prepare_oos_text(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        url = _resolve_url(config_path, project="proj", path="shared.txt")
        status, raw = _post(url, {"action": "submit", "middle": "confirmed fact", "binary": False})
        assert status == HTTPStatus.OK
        assert json.loads(raw)["applied"] is True
        land_status, body = _get(_resolve_url(config_path))
    assert land_status == HTTPStatus.OK
    assert "<p>None</p>" in body
    assert "shared.txt" not in body


def test_submit_writes_binary_confirmed_fact_without_rereading_replicas(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Binary submit sends the pick's bytes; the daemon writes those exact bytes to every replica."""
    config_path, managed, target_a, target_b = _write_two_target_workspace(tmp_path)
    (managed / "shared.txt").write_bytes(b"v0\x00")
    live = _live_sync(config_path)
    (target_a / "shared.txt").write_bytes(b"from-a\x00")
    (target_b / "shared.txt").write_bytes(b"from-b\x00")
    live.tick()
    _persist(config_path, live)
    confirmed = b"pick-b\x00"
    with _ready_resolve_ui(config_path, isolated_home):
        url = _resolve_url(config_path, project="proj", path="shared.txt")
        status, raw = _post(
            url,
            {
                "action": "submit",
                "binary": True,
                "content": base64.b64encode(confirmed).decode("ascii"),
            },
        )
    assert status == HTTPStatus.OK
    data = json.loads(raw)
    assert data["ok"] is True
    assert data["applied"] is True
    assert (managed / "shared.txt").read_bytes() == confirmed
    assert (target_a / "shared.txt").read_bytes() == confirmed
    assert (target_b / "shared.txt").read_bytes() == confirmed
    assert list_held_copies(managed) == ()


def test_get_and_unknown_action_post_do_not_write_hub_or_replica_files(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """GET and unknown-action POST do not change hub or replica files; submit does write."""
    config_path, managed, target_a, target_b = _prepare_oos_text(tmp_path)
    paths = [managed / "shared.txt", target_a / "shared.txt", target_b / "shared.txt"]
    before = _file_snapshot(paths)
    with _ready_resolve_ui(config_path, isolated_home):
        url = _resolve_url(config_path, project="proj", path="shared.txt")
        _get(url)
        _post(url, {"action": "unknown"})
        assert _file_snapshot(paths) == before
        status, raw = _post(url, {"action": "submit", "middle": "edited", "binary": False})
    assert status == HTTPStatus.OK
    assert json.loads(raw)["applied"] is True
    assert (managed / "shared.txt").read_text() == "edited"
    assert (target_a / "shared.txt").read_text() == "edited"
    assert (target_b / "shared.txt").read_text() == "edited"


def test_cli_reference_describes_the_sequential_merge_editor() -> None:
    """docs/cli-reference.md describes the sequential, client-driven merge editor and its vendoring."""
    text = (_REPO_ROOT / "docs" / "cli-reference.md").read_text(encoding="utf-8")
    assert "middle pane is empty until merge lands" not in text
    assert "CodeMirror" in text
    assert "mark as merged" in text
    assert "same as hub" in text
    assert "common leading path segments collapsed" in text or "collapsed to one line" in text
    assert "submit" in text
    assert "ADR 0025" in text
    assert "vendored" in text
    assert "CDN" in text
    assert "confirmed fact" in text
    assert "new hub generation" in text
    assert "every replica" in text
    assert "not held" in text
    assert "nav row leaves" in text or "row leaves" in text
