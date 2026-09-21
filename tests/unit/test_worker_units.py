"""Accept thread never hashes: status stays live during idle observe."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from click.testing import Result

from tests.daemon_support import invoke_cli, start_daemon, stop_daemon

_POLL_S = 0.05
_HOLD_WAIT_S = 5.0
_STATUS_FAST_S = 0.5
_SAME_UNIT_WAIT_S = 0.9


def test_status_returns_while_idle_observe_is_held(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """status is answered on the accept thread while idle observe is blocked."""
    managed = tmp_path / "alpha"
    target = tmp_path / "lab-app"
    managed.mkdir()
    target.mkdir()
    (managed / "shared.txt").write_text("hello")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"alpha: {target}\n")
    hold = tmp_path / "idle-hold"
    hold.write_text("1")
    entered = Path(str(hold) + ".entered")
    env = {**isolated_home, "BLF_TEST_IDLE_HOLD": str(hold)}
    start_daemon(config_path, env)
    try:
        deadline = time.monotonic() + _HOLD_WAIT_S
        while time.monotonic() < deadline and not entered.exists():
            time.sleep(_POLL_S)
        assert entered.exists(), "idle observe never entered the test hold"
        result: dict[str, Result | float] = {}

        def _status() -> None:
            started = time.perf_counter()
            result["response"] = invoke_cli(["--config", str(config_path), "daemon", "status"], env=env)
            result["elapsed"] = time.perf_counter() - started

        thread = threading.Thread(target=_status)
        thread.start()
        thread.join(1.0)
        hold.unlink(missing_ok=True)
        thread.join(2.0)
        assert not thread.is_alive()
        status = result["response"]
        assert isinstance(status, Result)
        assert status.exit_code == 0, status.output
        assert "Daemon is running" in status.output
        elapsed = result["elapsed"]
        assert isinstance(elapsed, float)
        assert elapsed < _STATUS_FAST_S, f"status blocked for {elapsed:.3f}s during idle observe"
    finally:
        hold.unlink(missing_ok=True)
        stop_daemon(config_path, env)


def test_create_on_one_project_is_not_blocked_by_idle_observe_of_another(
    tmp_path: Path,
    isolated_home: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A worker-unit job for one managed project does not wait on another's idle observe."""
    alpha_hub = tmp_path / "alpha"
    beta_hub = tmp_path / "beta"
    alpha_target = tmp_path / "lab-app"
    beta_target = tmp_path / "lab-notes"
    for hub, name in ((alpha_hub, "a"), (beta_hub, "b")):
        hub.mkdir()
        (hub / f"shared-{name}.txt").write_text(name)
    alpha_target.mkdir()
    beta_target.mkdir()
    (beta_target / "item.txt").write_text("adopt me")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"alpha: {alpha_target}\nbeta: {beta_target}\n")
    hold = tmp_path / "idle-hold"
    hold.write_text("1")
    entered = Path(str(hold) + ".entered")
    env = {
        **isolated_home,
        "BLF_TEST_IDLE_HOLD": str(hold),
        "BLF_TEST_IDLE_HOLD_PROJECT": "alpha",
    }
    start_daemon(config_path, env)
    try:
        deadline = time.monotonic() + _HOLD_WAIT_S
        while time.monotonic() < deadline and not entered.exists():
            time.sleep(_POLL_S)
        assert entered.exists(), "alpha idle observe never entered the test hold"
        result: dict[str, Result | float] = {}

        def _create() -> None:
            started = time.perf_counter()
            monkeypatch.chdir(beta_target)
            result["response"] = invoke_cli(
                ["--config", str(config_path), "revlink", "create", "item.txt"],
                env=env,
            )
            result["elapsed"] = time.perf_counter() - started

        thread = threading.Thread(target=_create)
        thread.start()
        thread.join(1.0)
        hold.unlink(missing_ok=True)
        thread.join(2.0)
        assert not thread.is_alive()
        created = result["response"]
        assert isinstance(created, Result)
        assert created.exit_code == 0, created.output
        elapsed = result["elapsed"]
        assert isinstance(elapsed, float)
        assert elapsed < _STATUS_FAST_S, f"beta create blocked for {elapsed:.3f}s on alpha idle observe"
        assert (beta_hub / "item.txt").read_text() == "adopt me"
    finally:
        hold.unlink(missing_ok=True)
        stop_daemon(config_path, env)


def test_create_waits_for_idle_observe_on_the_same_worker_unit(
    tmp_path: Path,
    isolated_home: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mutating shell for a managed project waits on that unit's in-flight observe."""
    managed = tmp_path / "alpha"
    target = tmp_path / "lab-app"
    managed.mkdir()
    target.mkdir()
    (managed / "shared.txt").write_text("hello")
    (target / "item.txt").write_text("adopt me")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"alpha: {target}\n")
    hold = tmp_path / "idle-hold"
    hold.write_text("1")
    entered = Path(str(hold) + ".entered")
    env = {**isolated_home, "BLF_TEST_IDLE_HOLD": str(hold)}
    start_daemon(config_path, env)
    try:
        deadline = time.monotonic() + _HOLD_WAIT_S
        while time.monotonic() < deadline and not entered.exists():
            time.sleep(_POLL_S)
        assert entered.exists(), "idle observe never entered the test hold"
        result: dict[str, Result | float] = {}

        def _create() -> None:
            started = time.perf_counter()
            monkeypatch.chdir(target)
            result["response"] = invoke_cli(
                ["--config", str(config_path), "revlink", "create", "item.txt"],
                env=env,
            )
            result["elapsed"] = time.perf_counter() - started

        thread = threading.Thread(target=_create)
        thread.start()
        thread.join(1.0)
        hold.unlink(missing_ok=True)
        thread.join(2.0)
        assert not thread.is_alive()
        created = result["response"]
        assert isinstance(created, Result)
        assert created.exit_code == 0, created.output
        elapsed = result["elapsed"]
        assert isinstance(elapsed, float)
        assert elapsed >= _SAME_UNIT_WAIT_S, (
            f"same-unit create returned in {elapsed:.3f}s without waiting for idle observe"
        )
        assert (managed / "item.txt").read_text() == "adopt me"
    finally:
        hold.unlink(missing_ok=True)
        stop_daemon(config_path, env)
