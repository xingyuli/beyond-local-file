"""Shells talk only to the daemon: create, restore, remove, check, upgrade."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from beyond_local_file.cli import cli
from beyond_local_file.daemon.process import state_dir

_READY_WAIT_S = 15.0
_POLL_S = 0.05
_DAEMON_START_HINT = "blf daemon start"


def _invoke(args: list[str], env: dict[str, str] | None = None) -> Result:
    """Invoke the CLI in-process."""
    return CliRunner().invoke(cli, args, env=env)


def _state_dir(config_path: Path) -> Path:
    return state_dir(config_path)


def _pid_path(config_path: Path) -> Path:
    return _state_dir(config_path) / "daemon.pid"


def _port_path(config_path: Path) -> Path:
    return _state_dir(config_path) / "daemon.port"


def _snapshot_path(config_path: Path) -> Path:
    return _state_dir(config_path) / "mapping-snapshot.yml"


def _baseline_path(config_path: Path) -> Path:
    return _state_dir(config_path) / "baseline.yml"


def _read_pid(config_path: Path) -> int | None:
    path = _pid_path(config_path)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    return int(text.splitlines()[0])


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    try:
        waited, _status = os.waitpid(pid, os.WNOHANG)
    except (ChildProcessError, OSError):
        return True
    return waited != pid


def _wait_until(predicate, *, timeout: float = _READY_WAIT_S) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(_POLL_S)
    raise TimeoutError("condition was not met")


def _stop_daemon(config_path: Path, env: dict[str, str]) -> None:
    _invoke(["--config", str(config_path), "daemon", "stop"], env=env)
    pid = _read_pid(config_path)
    if pid is not None and _pid_alive(pid):
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and _pid_alive(pid):
            time.sleep(_POLL_S)


def _write_selective_workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Managed project, one target, empty selective mapping."""
    managed = tmp_path / "managed"
    target = tmp_path / "target"
    managed.mkdir()
    target.mkdir()
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"managed:\n  target: {target}\n  subpath: []\n")
    return config_path, managed, target


def _make_git_repo(directory: Path) -> Path:
    exclude = directory / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True)
    exclude.write_text("# preserved\n")
    return exclude


def _start_daemon(config_path: Path, env: dict[str, str]) -> None:
    started = _invoke(["--config", str(config_path), "daemon", "start"], env=env)
    assert started.exit_code == 0, started.output
    pid = _read_pid(config_path)
    assert pid is not None
    assert _pid_alive(pid)


@pytest.fixture
def daemon_env(isolated_home: dict[str, str]) -> dict[str, str]:
    return isolated_home


@pytest.fixture
def selective_workspace(tmp_path: Path, daemon_env: dict[str, str]) -> Iterator[tuple[Path, Path, Path]]:
    config_path, managed, target = _write_selective_workspace(tmp_path)
    try:
        yield config_path, managed, target
    finally:
        _stop_daemon(config_path, daemon_env)


def test_link_sync_is_not_a_command() -> None:
    """blf link sync is gone; Click reports it is not a command."""
    result = _invoke(["link", "sync", "--help"])

    assert result.exit_code != 0
    assert "no such command" in result.output.lower()

    help_result = _invoke(["link", "--help"])
    assert help_result.exit_code == 0
    assert "check" in help_result.output
    commands = help_result.output.split("Commands:")[-1]
    assert "sync" not in commands


def test_link_check_fails_with_start_hint_when_daemon_down(
    selective_workspace: tuple[Path, Path, Path],
    daemon_env: dict[str, str],
) -> None:
    """link check fails and tells the user to start the daemon."""
    config_path, _managed, _target = selective_workspace

    result = _invoke(["--config", str(config_path), "link", "check"], env=daemon_env)

    assert result.exit_code != 0
    assert _DAEMON_START_HINT in result.output


def test_revlink_create_fails_with_start_hint_when_daemon_down(
    selective_workspace: tuple[Path, Path, Path],
    daemon_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """revlink create fails and tells the user to start the daemon."""
    config_path, _managed, target = selective_workspace
    source = target / "item.txt"
    source.write_text("adopt me")
    monkeypatch.chdir(target)

    result = _invoke(["--config", str(config_path), "revlink", "create", "item.txt"], env=daemon_env)

    assert result.exit_code != 0
    assert _DAEMON_START_HINT in result.output
    assert not (config_path.parent / "managed" / "item.txt").exists()
    assert source.read_text() == "adopt me"
    assert "- item.txt" not in config_path.read_text()


def test_revlink_restore_fails_with_start_hint_when_daemon_down(
    selective_workspace: tuple[Path, Path, Path],
    daemon_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """revlink restore fails and tells the user to start the daemon."""
    config_path, managed, target = selective_workspace
    hub = managed / "item.txt"
    replica = target / "item.txt"
    hub.write_text("shared")
    replica.write_text("shared")
    config_path.write_text(f"managed:\n  target: {target}\n  subpath:\n    - item.txt\n")
    monkeypatch.chdir(target)

    result = _invoke(["--config", str(config_path), "revlink", "restore", "item.txt"], env=daemon_env)

    assert result.exit_code != 0
    assert _DAEMON_START_HINT in result.output
    assert hub.read_text() == "shared"
    assert replica.read_text() == "shared"
    assert "- item.txt" in config_path.read_text()


def test_remove_fails_with_start_hint_when_daemon_down(
    selective_workspace: tuple[Path, Path, Path],
    daemon_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """remove fails and tells the user to start the daemon."""
    config_path, managed, target = selective_workspace
    hub = managed / "item.txt"
    replica = target / "item.txt"
    hub.write_text("shared")
    replica.write_text("shared")
    config_path.write_text(f"managed:\n  target: {target}\n  subpath:\n    - item.txt\n")
    monkeypatch.chdir(target)

    result = _invoke(["--config", str(config_path), "remove", "item.txt"], env=daemon_env)

    assert result.exit_code != 0
    assert _DAEMON_START_HINT in result.output
    assert hub.read_text() == "shared"
    assert replica.read_text() == "shared"
    assert "- item.txt" in config_path.read_text()


def test_upgrade_refuses_while_daemon_is_running(
    selective_workspace: tuple[Path, Path, Path],
    daemon_env: dict[str, str],
) -> None:
    """blf upgrade does not run while the daemon is up."""
    config_path, _managed, _target = selective_workspace
    _start_daemon(config_path, daemon_env)

    result = _invoke(["--config", str(config_path), "upgrade"], env=daemon_env)

    assert result.exit_code != 0
    assert "daemon" in result.output.lower()
    assert "running" in result.output.lower()


def test_shell_does_not_copy_when_daemon_acks_without_work(  # noqa: PLR0915 -- fixture setup for a fake daemon is necessarily long
    tmp_path: Path,
    daemon_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A daemon that returns success without mutating still leaves the shell idle."""
    config_path, managed, target = _write_selective_workspace(tmp_path)
    source = target / "item.txt"
    source.write_text("adopt me")
    exclude = _make_git_repo(target)
    state = _state_dir(config_path)
    state.mkdir(parents=True)
    placeholder = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _pid_path(config_path).write_text(f"{placeholder.pid}\n", encoding="utf-8")
    port_file = _port_path(config_path)
    stop = threading.Event()
    listening = threading.Event()

    def _serve() -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        server.settimeout(0.2)
        port_file.write_text(f"{server.getsockname()[1]}\n", encoding="utf-8")
        listening.set()
        try:
            while not stop.is_set():
                try:
                    conn, _addr = server.accept()
                except TimeoutError:
                    continue
                with conn:
                    chunks = b""
                    while b"\n" not in chunks:
                        piece = conn.recv(65536)
                        if not piece:
                            break
                        chunks += piece
                    conn.sendall(json.dumps({"exit_code": 0, "stdout": "acked\n"}).encode() + b"\n")
        finally:
            server.close()

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    assert listening.wait(timeout=2)
    monkeypatch.chdir(target)
    try:
        result = _invoke(["--config", str(config_path), "revlink", "create", "item.txt"], env=daemon_env)
    finally:
        stop.set()
        thread.join(timeout=2)
        placeholder.kill()
        placeholder.wait(timeout=5)
        port_file.unlink(missing_ok=True)
        _pid_path(config_path).unlink(missing_ok=True)

    assert result.exit_code == 0, result.output
    assert "acked" in result.output
    assert not (managed / "item.txt").exists()
    assert source.read_text() == "adopt me"
    assert "- item.txt" not in config_path.read_text()
    assert "item.txt" not in exclude.read_text()


def test_create_restore_remove_change_state_through_the_daemon(
    selective_workspace: tuple[Path, Path, Path],
    daemon_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create, restore, and remove mutate mappings, copies, and excludes via the daemon."""
    config_path, managed, target = selective_workspace
    second = config_path.parent / "target-two"
    second.mkdir()
    config_path.write_text(f"managed:\n  - target: {target}\n    subpath: []\n  - target: {second}\n    subpath: []\n")
    exclude = _make_git_repo(target)
    second_exclude = _make_git_repo(second)
    source = target / "item.txt"
    source.write_text("adopt me")
    _start_daemon(config_path, daemon_env)
    monkeypatch.chdir(target)

    created = _invoke(["--config", str(config_path), "revlink", "create", "item.txt"], env=daemon_env)

    assert created.exit_code == 0, created.output
    hub = managed / "item.txt"
    assert hub.is_file()
    assert not hub.is_symlink()
    assert hub.read_text() == "adopt me"
    assert source.is_file()
    assert not source.is_symlink()
    replica = second / "item.txt"
    assert replica.read_text() == "adopt me"
    assert "item.txt" in exclude.read_text()
    assert "item.txt" in second_exclude.read_text()
    assert config_path.read_text().count("- item.txt") == config_path.read_text().count("target:")
    snapshot = _snapshot_path(config_path).read_text()
    assert "item.txt" in snapshot
    assert _baseline_path(config_path).is_file()

    restored = _invoke(["--config", str(config_path), "revlink", "restore", "item.txt"], env=daemon_env)

    assert restored.exit_code == 0, restored.output
    assert not hub.exists()
    assert source.read_text() == "adopt me"
    assert replica.read_text() == "adopt me"
    assert "- item.txt" not in config_path.read_text()
    assert "item.txt" not in _snapshot_path(config_path).read_text()

    source.write_text("adopt me")
    hub.write_text("adopt me")
    replica.write_text("adopt me")
    exclude.write_text("# preserved\nitem.txt\n")
    second_exclude.write_text("# preserved\nitem.txt\n")
    config_path.write_text(
        "managed:\n"
        f"  - target: {target}\n    subpath:\n      - item.txt\n"
        f"  - target: {second}\n    subpath:\n      - item.txt\n"
    )

    removed = _invoke(["--config", str(config_path), "remove", "item.txt"], env=daemon_env)

    assert removed.exit_code == 0, removed.output
    assert not hub.exists()
    assert not source.exists()
    assert not replica.exists()
    assert "item.txt" not in exclude.read_text()
    assert "item.txt" not in second_exclude.read_text()
    assert "- item.txt" not in config_path.read_text()
    assert "item.txt" not in _snapshot_path(config_path).read_text()


def test_link_check_reports_daemon_snapshot_not_uncommitted_config(
    selective_workspace: tuple[Path, Path, Path],
    daemon_env: dict[str, str],
) -> None:
    """link check is a daemon query: it reports snapshot mappings, not a dirty config file."""
    config_path, managed, target = selective_workspace
    (managed / "shared.txt").write_text("hub")
    config_path.write_text(f"managed: {target}\n")
    _start_daemon(config_path, daemon_env)
    assert (target / "shared.txt").read_text() == "hub"

    other = config_path.parent / "other-target"
    other.mkdir()
    config_path.write_text(f"managed: {other}\n")

    result = _invoke(
        ["--config", str(config_path), "link", "check", "--format", "verbose"],
        env=daemon_env,
    )

    assert result.exit_code == 0, result.output
    assert str(target) in result.output
    assert str(other) not in result.output
    assert "shared.txt" in result.output or "managed" in result.output
