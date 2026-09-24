"""Resolve UI HTTP and non-TTY status seams."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from http import HTTPStatus
from pathlib import Path
from urllib.error import HTTPError
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


def _resolve_url(config_path: Path, *, token: str | None = None) -> str:
    port = _read_int_file(_resolve_port_path(config_path))
    assert port is not None
    if token is None:
        token = _read_token(config_path)
    return f"http://127.0.0.1:{port}/?token={token}"


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


def test_ready_daemon_serves_resolve_ui_with_token_and_rejects_without(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A ready daemon serves the resolve UI on localhost; a request without the token is rejected."""
    _live, config_path, _managed, target_a, target_b, slot = _prepare_isolation(tmp_path)
    start_daemon(config_path, isolated_home)
    try:
        _wait_until(lambda: _resolve_port_path(config_path).is_file())
        token = _read_token(config_path)
        assert token
        status, body = _get(_resolve_url(config_path))
        assert status == HTTPStatus.OK
        assert "shared.txt" in body
        assert target_b.as_posix() in body
        assert _stale_base_clause(target_b, target_a) in body
        assert "delete applied past the generation window" in body
        assert slot.as_posix() in body
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
