"""Resolve UI HTTP and non-TTY status seams."""

from __future__ import annotations

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
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

import pytest

from beyond_local_file.daemon.live import LiveSync
from beyond_local_file.daemon.process import port_path, state_dir
from beyond_local_file.daemon.screen import _ShellScreen
from beyond_local_file.held import REASON_DELETE_GAP, store_held_copy
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
    replica: str | None = None,
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
    if replica is not None:
        query["replica"] = replica
    return f"http://127.0.0.1:{port}/?{urlencode(query)}"


def _get(url: str) -> tuple[int, str]:
    try:
        with urlopen(url, timeout=3) as response:
            return response.status, response.read().decode("utf-8")
    except HTTPError as error:
        return error.code, error.read().decode("utf-8")


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
def _ready_resolve_ui(config_path: Path, isolated_home: dict[str, str]) -> Iterator[None]:
    """Start a ready daemon that serves the resolve UI, then stop it."""
    start_daemon(config_path, isolated_home)
    try:
        _wait_until(lambda: _resolve_port_path(config_path).is_file())
        yield
    finally:
        stop_daemon(config_path, isolated_home)


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


def _project_section(body: str, name: str) -> str:
    """Return the nav section HTML grouped under *name*."""
    match = re.search(rf"<h2>{re.escape(name)}</h2>(.*?)</section>", body, re.DOTALL)
    assert match is not None, f"missing managed project group {name!r}"
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
        assert "both" in _project_section(body, "proj")
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


def test_finished_status_o_opens_browser_and_leaves_the_screen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pressing o on a finished status screen calls webbrowser.open and does not close."""
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
    assert screen._hint_text() == "o: open  q: close  Ctrl+C: close"
    screen._on_key("o", None)
    assert opened == [url]
    assert not screen._closed
    screen._on_key("q", None)
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


def test_several_out_of_sync_replicas_are_one_nav_row_with_switcher(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Several out-of-sync replicas of one path are one nav row; the switcher lists every target."""
    config_path, target_a, target_b, target_c = _prepare_three_target_out_of_sync(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        status, body = _get(_resolve_url(config_path, project="proj", path="shared.txt"))
    assert status == HTTPStatus.OK
    assert body.count('class="nav-row"') == 1
    assert "shared.txt" in _project_section(body, "proj")
    switcher = body[body.index('class="switcher"') :]
    assert target_a.as_posix() in switcher
    assert target_b.as_posix() in switcher
    assert target_c.as_posix() in switcher
    assert "same as hub" in switcher


def test_right_pane_opens_on_first_out_of_sync_replica_and_labels_same_as_hub(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Right pane starts on the first out-of-sync replica; live matches are same as hub; no source badge."""
    config_path, target_a, target_b, _target_c = _prepare_three_target_out_of_sync(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        status, body = _get(_resolve_url(config_path, project="proj", path="shared.txt"))
    assert status == HTTPStatus.OK
    hub_now = body[body.index("hub-now") : body.index("replica-now")]
    replica_now = body[body.index("replica-now") :]
    assert "from-a" in hub_now
    assert "from-b" in replica_now
    assert "from-c" not in replica_now
    assert target_b.as_posix() in body[body.index('class="switcher"') :]
    assert "same as hub" in body
    assert target_a.as_posix() in body
    assert "#c8e6c9" in body
    assert "source" not in body.lower()


def test_reason_clause_follows_the_selected_right_replica(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Following a switcher link updates the out-of-sync reason clause to that replica."""
    config_path, target_a, target_b, target_c = _prepare_three_target_out_of_sync(tmp_path)
    clause_b = _stale_base_clause(target_b, target_a)
    clause_c = _stale_base_clause(target_c, target_a)
    with _ready_resolve_ui(config_path, isolated_home):
        _status, default_body = _get(_resolve_url(config_path, project="proj", path="shared.txt"))
        _status, selected_body = _get(
            _resolve_url(config_path, project="proj", path="shared.txt", replica=target_c.as_posix())
        )
    assert clause_b in default_body
    assert clause_c not in default_body
    assert "from-b" in default_body
    assert clause_c in selected_body
    assert clause_b not in selected_body
    assert "from-c" in selected_body
    assert "from-b" not in selected_body


def test_held_only_path_shows_hold_reason_and_no_copy_view(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A held-only path shows its hold-reason clause(s) and no hub-now/replica-now panes."""
    config_path, _target_b = _prepare_held_only(tmp_path)
    with _ready_resolve_ui(config_path, isolated_home):
        index_status, index_body = _get(_resolve_url(config_path))
        status, body = _get(_resolve_url(config_path, project="proj", path="shared.txt"))
    assert index_status == HTTPStatus.OK
    assert "held" in _project_section(index_body, "proj")
    assert status == HTTPStatus.OK
    assert "delete applied past the generation window" in body
    assert "hub-now" not in body
    assert "replica-now" not in body
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
    assert "both" in _project_section(index_body, "proj")
    assert status == HTTPStatus.OK
    assert "hub-now" in body
    assert "replica-now" in body
    assert "from-a" in body
    assert "from-b" in body
    assert _stale_base_clause(target_b, target_a) in body
    assert "delete applied past the generation window" in body


def test_cli_reference_describes_nav_switcher_and_same_as_hub() -> None:
    """docs/cli-reference.md describes the nav, the replica switcher, and same as hub."""
    text = (_REPO_ROOT / "docs" / "cli-reference.md").read_text(encoding="utf-8")
    assert "grouped by managed project name" in text
    assert "replica switcher" in text
    assert "same as hub" in text
