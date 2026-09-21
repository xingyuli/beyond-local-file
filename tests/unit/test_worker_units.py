"""Accept thread never hashes: status stays live during idle observe."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from click.testing import Result

from beyond_local_file.daemon.client import send_when_up
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


def _two_project_workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    alpha_hub = tmp_path / "alpha"
    beta_hub = tmp_path / "beta"
    alpha_target = tmp_path / "lab-app"
    beta_target = tmp_path / "lab-notes"
    for hub, target, name in (
        (alpha_hub, alpha_target, "a"),
        (beta_hub, beta_target, "b"),
    ):
        hub.mkdir()
        target.mkdir()
        (hub / f"shared-{name}.txt").write_text(name)
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"alpha: {alpha_target}\nbeta: {beta_target}\n")
    return config_path, alpha_target, beta_target


def test_link_check_waits_for_idle_observe_on_each_worker_unit(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A set-wide link check enqueues on every worker unit and merges the table."""
    config_path, _alpha_target, _beta_target = _two_project_workspace(tmp_path)
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

        def _check() -> None:
            started = time.perf_counter()
            result["response"] = invoke_cli(["--config", str(config_path), "link", "check"], env=env)
            result["elapsed"] = time.perf_counter() - started

        thread = threading.Thread(target=_check)
        thread.start()
        thread.join(1.0)
        hold.unlink(missing_ok=True)
        thread.join(2.0)
        assert not thread.is_alive()
        checked = result["response"]
        assert isinstance(checked, Result)
        assert checked.exit_code == 0, checked.output
        elapsed = result["elapsed"]
        assert isinstance(elapsed, float)
        assert elapsed >= _SAME_UNIT_WAIT_S, f"set-wide check returned in {elapsed:.3f}s without waiting for alpha"
        assert "alpha" in checked.output
        assert "beta" in checked.output
    finally:
        hold.unlink(missing_ok=True)
        stop_daemon(config_path, env)


def test_link_check_of_one_project_is_not_blocked_by_another_unit_idle(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """link check PROJECT enqueues only that worker unit."""
    config_path, _alpha_target, _beta_target = _two_project_workspace(tmp_path)
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

        def _check() -> None:
            started = time.perf_counter()
            result["response"] = invoke_cli(
                ["--config", str(config_path), "link", "check", "beta"],
                env=env,
            )
            result["elapsed"] = time.perf_counter() - started

        thread = threading.Thread(target=_check)
        thread.start()
        thread.join(1.0)
        hold.unlink(missing_ok=True)
        thread.join(2.0)
        assert not thread.is_alive()
        checked = result["response"]
        assert isinstance(checked, Result)
        assert checked.exit_code == 0, checked.output
        elapsed = result["elapsed"]
        assert isinstance(elapsed, float)
        assert elapsed < _STATUS_FAST_S, f"beta check blocked for {elapsed:.3f}s on alpha idle observe"
        assert "beta" in checked.output
        assert "alpha" not in checked.output
    finally:
        hold.unlink(missing_ok=True)
        stop_daemon(config_path, env)


def test_link_check_runs_other_units_while_one_unit_is_held(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Set-wide check jobs start on idle units without waiting for a held peer."""
    config_path, _alpha_target, _beta_target = _two_project_workspace(tmp_path)
    hold = tmp_path / "idle-hold"
    hold.write_text("1")
    entered = Path(str(hold) + ".entered")
    started = tmp_path / "check-started"
    env = {
        **isolated_home,
        "BLF_TEST_IDLE_HOLD": str(hold),
        "BLF_TEST_IDLE_HOLD_PROJECT": "alpha",
        "BLF_TEST_CHECK_STARTED": str(started),
    }
    start_daemon(config_path, env)
    thread: threading.Thread | None = None
    try:
        deadline = time.monotonic() + _HOLD_WAIT_S
        while time.monotonic() < deadline and not entered.exists():
            time.sleep(_POLL_S)
        assert entered.exists(), "alpha idle observe never entered the test hold"
        thread = threading.Thread(
            target=lambda: invoke_cli(["--config", str(config_path), "link", "check"], env=env)
        )
        thread.start()
        mark = started / "beta"
        mark_deadline = time.monotonic() + _HOLD_WAIT_S
        while time.monotonic() < mark_deadline and not mark.exists():
            time.sleep(_POLL_S)
        assert mark.exists(), "beta check did not start while alpha idle observe was held"
        hold.unlink(missing_ok=True)
        thread.join(2.0)
        assert not thread.is_alive()
    finally:
        hold.unlink(missing_ok=True)
        if thread is not None and thread.is_alive():
            thread.join(2.0)
        stop_daemon(config_path, env)


def test_reload_of_one_project_does_not_catch_up_another_held_unit(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Reload catch-up jobs run only for worker units whose mappings changed."""
    config_path, _alpha_target, beta_target = _two_project_workspace(tmp_path)
    beta_hub = tmp_path / "beta"
    extra_target = tmp_path / "lab-notes-2"
    extra_target.mkdir()
    hold = tmp_path / "idle-hold"
    hold.write_text("1")
    entered = Path(str(hold) + ".entered")
    started = tmp_path / "catchup-started"
    env = {
        **isolated_home,
        "BLF_TEST_IDLE_HOLD": str(hold),
        "BLF_TEST_IDLE_HOLD_PROJECT": "alpha",
        "BLF_TEST_CATCHUP_STARTED": str(started),
    }
    start_daemon(config_path, env)
    try:
        deadline = time.monotonic() + _HOLD_WAIT_S
        while time.monotonic() < deadline and not entered.exists():
            time.sleep(_POLL_S)
        assert entered.exists(), "alpha idle observe never entered the test hold"
        if started.exists():
            for mark in started.iterdir():
                mark.unlink()
        config_path.write_text(f"alpha: {_alpha_target}\nbeta:\n  - {beta_target}\n  - {extra_target}\n")
        result: dict[str, Result | float] = {}

        def _reload() -> None:
            started_at = time.perf_counter()
            result["response"] = invoke_cli(["--config", str(config_path), "daemon", "reload"], env=env)
            result["elapsed"] = time.perf_counter() - started_at

        thread = threading.Thread(target=_reload)
        thread.start()
        thread.join(1.0)
        hold.unlink(missing_ok=True)
        thread.join(2.0)
        assert not thread.is_alive()
        reloaded = result["response"]
        assert isinstance(reloaded, Result)
        assert reloaded.exit_code == 0, reloaded.output
        elapsed = result["elapsed"]
        assert isinstance(elapsed, float)
        assert elapsed < _STATUS_FAST_S, f"beta-only reload blocked for {elapsed:.3f}s on alpha idle observe"
        assert (started / "beta").is_file()
        assert not (started / "alpha").exists()
        assert (extra_target / "shared-b.txt").read_text() == "b"
        assert (beta_hub / "shared-b.txt").read_text() == "b"
    finally:
        hold.unlink(missing_ok=True)
        stop_daemon(config_path, env)


def test_create_streams_waiting_while_the_worker_unit_is_busy(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A mutating TTY status line is Waiting while that unit is in idle observe."""
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
        progress: list[str] = []
        result: dict[str, object] = {}

        def _create() -> None:
            result["response"] = send_when_up(
                config_path,
                {
                    "op": "create",
                    "cwd": str(target),
                    "path": "item.txt",
                    "project_name": "alpha",
                },
                on_progress=progress.append,
            )

        thread = threading.Thread(target=_create)
        thread.start()
        wait_deadline = time.monotonic() + _HOLD_WAIT_S
        while time.monotonic() < wait_deadline and not any(line.startswith("Waiting") for line in progress):
            time.sleep(_POLL_S)
        assert any(line.startswith("Waiting") for line in progress), progress
        hold.unlink(missing_ok=True)
        thread.join(2.0)
        assert not thread.is_alive()
        response = result["response"]
        assert isinstance(response, dict)
        assert int(response.get("exit_code", 1)) == 0
        assert (managed / "item.txt").read_text() == "adopt me"
    finally:
        hold.unlink(missing_ok=True)
        stop_daemon(config_path, env)


def test_create_streams_op_and_baseline_status_lines(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """After Waiting, a mutating TTY shows the op then the item baseline write."""
    managed = tmp_path / "alpha"
    target = tmp_path / "lab-app"
    managed.mkdir()
    target.mkdir()
    (managed / "shared.txt").write_text("hello")
    (target / "item.txt").write_text("adopt me")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"alpha: {target}\n")
    start_daemon(config_path, isolated_home)
    try:
        progress: list[str] = []
        response = send_when_up(
            config_path,
            {
                "op": "create",
                "cwd": str(target),
                "path": "item.txt",
                "project_name": "alpha",
            },
            on_progress=progress.append,
        )
        assert int(response.get("exit_code", 1)) == 0
        assert any(line.startswith("Creating") for line in progress), progress
        assert any(line.startswith("Writing baseline") for line in progress), progress
    finally:
        stop_daemon(config_path, isolated_home)
