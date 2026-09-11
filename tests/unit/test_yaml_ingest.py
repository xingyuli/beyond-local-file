"""External YAML ingest on daemon start and reload at the public CLI seams."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from beyond_local_file.cli import cli
from tests.daemon_support import invoke_cli, start_daemon, stop_daemon
from tests.unit.test_daemon import _pid_alive, _read_pid, _snapshot_path

_READY_WAIT_S = 15.0
_POLL_S = 0.05


def _wait_until(predicate, *, timeout: float = _READY_WAIT_S) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(_POLL_S)
    raise TimeoutError("condition was not met")


def _write_selective_workspace(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path, Path]:
    """Two managed projects, three targets, and one selective mapping."""
    proj0 = tmp_path / "proj-0"
    proj1 = tmp_path / "proj-1"
    target_a = tmp_path / "target-a"
    target_b = tmp_path / "target-b"
    target_c = tmp_path / "target-c"
    for path in (proj0, proj1, target_a, target_b, target_c):
        path.mkdir()
    (proj0 / "shared.txt").write_text("hub-0")
    (proj0 / "extra.txt").write_text("extra-hub")
    (proj1 / "only.txt").write_text("hub-1")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "\n".join(
            [
                "proj-0:",
                f"  - {target_a}",
                f"  - target: {target_b}",
                "    subpath:",
                "      - shared.txt",
                "      - extra.txt",
                f"proj-1: {target_c}",
                "",
            ]
        )
    )
    return config_path, proj0, proj1, target_a, target_b, target_c


def _invoke_start(
    config_path: Path,
    env: dict[str, str],
    *,
    input_text: str | None = None,
) -> Result:
    return CliRunner().invoke(
        cli,
        ["--config", str(config_path), "daemon", "start"],
        env=env,
        input=input_text,
    )


@pytest.fixture
def ingest_env(isolated_home: dict[str, str]) -> dict[str, str]:
    return isolated_home


@pytest.fixture
def selective_workspace(
    tmp_path: Path, ingest_env: dict[str, str]
) -> Iterator[tuple[Path, Path, Path, Path, Path, Path]]:
    config_path, proj0, proj1, target_a, target_b, target_c = _write_selective_workspace(tmp_path)
    try:
        yield config_path, proj0, proj1, target_a, target_b, target_c
    finally:
        stop_daemon(config_path, ingest_env)


def test_start_when_file_differs_prints_coarse_to_fine_plan_and_waits_for_confirm(
    selective_workspace: tuple[Path, Path, Path, Path, Path, Path],
    ingest_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """file ≠ snapshot stays foreground: one plan, coarsest first, one yes/no."""
    config_path, _proj0, _proj1, target_a, target_b, target_c = selective_workspace
    start_daemon(config_path, ingest_env)
    stopped = invoke_cli(["--config", str(config_path), "daemon", "stop"], env=ingest_env)
    assert stopped.exit_code == 0, stopped.output

    config_path.write_text(
        "\n".join(
            [
                "proj-0:",
                f"  - target: {target_b}",
                "    subpath:",
                "      - shared.txt",
                "",
            ]
        )
    )
    monkeypatch.setattr("beyond_local_file.daemon.ingest.stdin_is_tty", lambda: True)
    result = _invoke_start(config_path, ingest_env, input_text="n\n")

    assert "project-remove" in result.output
    assert "target-remove" in result.output
    assert "item-remove" in result.output
    assert result.output.index("project-remove") < result.output.index("target-remove")
    assert result.output.index("target-remove") < result.output.index("item-remove")
    assert "proj-1" in result.output
    assert str(target_a.resolve()) in result.output
    assert "extra.txt" in result.output
    assert result.output.lower().count("project-remove") == 1
    assert "target-c" not in result.output or result.output.index("project-remove") < result.output.find(str(target_c))
    assert result.exit_code != 0
    assert _read_pid(config_path) is None or not _pid_alive(_read_pid(config_path) or 0)


def test_decline_leaves_snapshot_and_files_unchanged_and_does_not_daemonize(
    selective_workspace: tuple[Path, Path, Path, Path, Path, Path],
    ingest_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Answering no commits nothing and does not start the daemon."""
    config_path, proj0, proj1, target_a, target_b, target_c = selective_workspace
    start_daemon(config_path, ingest_env)
    stopped = invoke_cli(["--config", str(config_path), "daemon", "stop"], env=ingest_env)
    assert stopped.exit_code == 0, stopped.output
    snapshot_bytes = _snapshot_path(config_path).read_bytes()

    config_path.write_text(f"proj-0: {target_b}\n")
    monkeypatch.setattr("beyond_local_file.daemon.ingest.stdin_is_tty", lambda: True)
    result = _invoke_start(config_path, ingest_env, input_text="n\n")

    assert result.exit_code != 0
    assert _read_pid(config_path) is None or not _pid_alive(_read_pid(config_path) or 0)
    assert _snapshot_path(config_path).read_bytes() == snapshot_bytes
    assert (target_a / "shared.txt").read_text() == "hub-0"
    assert (target_b / "shared.txt").read_text() == "hub-0"
    assert (target_c / "only.txt").read_text() == "hub-1"
    assert (proj0 / "shared.txt").read_text() == "hub-0"
    assert (proj1 / "only.txt").read_text() == "hub-1"


def test_noninteractive_start_with_removals_does_not_commit_or_start(
    selective_workspace: tuple[Path, Path, Path, Path, Path, Path],
    ingest_env: dict[str, str],
) -> None:
    """No TTY plus removals fails: nothing committed, daemon does not start."""
    config_path, proj0, _proj1, target_a, target_b, target_c = selective_workspace
    start_daemon(config_path, ingest_env)
    stopped = invoke_cli(["--config", str(config_path), "daemon", "stop"], env=ingest_env)
    assert stopped.exit_code == 0, stopped.output
    snapshot_bytes = _snapshot_path(config_path).read_bytes()

    config_path.write_text(f"proj-0: {target_b}\n")
    result = _invoke_start(config_path, ingest_env)

    assert result.exit_code != 0
    assert "interactive" in result.output.lower() or "confirm" in result.output.lower()
    assert _read_pid(config_path) is None or not _pid_alive(_read_pid(config_path) or 0)
    assert _snapshot_path(config_path).read_bytes() == snapshot_bytes
    assert (target_a / "shared.txt").is_file()
    assert (target_c / "only.txt").is_file()
    assert (proj0 / "shared.txt").read_text() == "hub-0"


def test_yes_commits_deletes_target_copies_keeps_hub_then_backgrounds(
    selective_workspace: tuple[Path, Path, Path, Path, Path, Path],
    ingest_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Yes commits removals, deletes target copies, keeps hub content, then backgrounds."""
    config_path, proj0, proj1, target_a, target_b, target_c = selective_workspace
    start_daemon(config_path, ingest_env)
    stopped = invoke_cli(["--config", str(config_path), "daemon", "stop"], env=ingest_env)
    assert stopped.exit_code == 0, stopped.output

    config_path.write_text(
        "\n".join(
            [
                "proj-0:",
                f"  - target: {target_b}",
                "    subpath:",
                "      - shared.txt",
                "",
            ]
        )
    )
    monkeypatch.setattr("beyond_local_file.daemon.ingest.stdin_is_tty", lambda: True)
    result = _invoke_start(config_path, ingest_env, input_text="y\n")

    assert result.exit_code == 0, result.output
    pid = _read_pid(config_path)
    assert pid is not None
    assert _pid_alive(pid)
    assert not (target_a / "shared.txt").exists()
    assert not (target_a / "extra.txt").exists()
    assert not (target_b / "extra.txt").exists()
    assert not (target_c / "only.txt").exists()
    assert (target_b / "shared.txt").read_text() == "hub-0"
    assert (proj0 / "shared.txt").read_text() == "hub-0"
    assert (proj0 / "extra.txt").read_text() == "extra-hub"
    assert (proj1 / "only.txt").read_text() == "hub-1"


def test_adding_a_target_fans_hub_onto_that_replica_only(
    tmp_path: Path,
    ingest_env: dict[str, str],
) -> None:
    """A new target gets a fresh catch-up; other replicas are not reset."""
    managed = tmp_path / "proj-0"
    target_a = tmp_path / "target-a"
    target_b = tmp_path / "target-b"
    for path in (managed, target_a, target_b):
        path.mkdir()
    (managed / "shared.txt").write_text("hub-0")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"proj-0: {target_a}\n")
    try:
        start_daemon(config_path, ingest_env)
        stopped = invoke_cli(["--config", str(config_path), "daemon", "stop"], env=ingest_env)
        assert stopped.exit_code == 0, stopped.output
        (target_a / "shared.txt").write_text("target-a-edit")

        config_path.write_text(f"proj-0:\n  - {target_a}\n  - {target_b}\n")
        result = _invoke_start(config_path, ingest_env)
        assert result.exit_code == 0, result.output
        pid = _read_pid(config_path)
        assert pid is not None
        assert _pid_alive(pid)
        _wait_until((target_b / "shared.txt").is_file)
        assert (target_b / "shared.txt").read_text() == "hub-0"
        assert (target_a / "shared.txt").read_text() == "target-a-edit"
        assert (managed / "shared.txt").read_text() == "hub-0"
    finally:
        stop_daemon(config_path, ingest_env)


def test_adding_subpath_with_hub_file_fans_out_without_prompt(
    tmp_path: Path,
    ingest_env: dict[str, str],
) -> None:
    """Adding a subpath whose hub file exists fans out with no confirmation."""
    managed = tmp_path / "proj-0"
    target = tmp_path / "target-0"
    managed.mkdir()
    target.mkdir()
    (managed / "shared.txt").write_text("hub-0")
    (managed / "extra.txt").write_text("extra-hub")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "\n".join(
            [
                "proj-0:",
                f"  target: {target}",
                "  subpath:",
                "    - shared.txt",
                "",
            ]
        )
    )
    try:
        start_daemon(config_path, ingest_env)
        stopped = invoke_cli(["--config", str(config_path), "daemon", "stop"], env=ingest_env)
        assert stopped.exit_code == 0, stopped.output
        assert not (target / "extra.txt").exists()

        config_path.write_text(
            "\n".join(
                [
                    "proj-0:",
                    f"  target: {target}",
                    "  subpath:",
                    "    - shared.txt",
                    "    - extra.txt",
                    "",
                ]
            )
        )
        result = _invoke_start(config_path, ingest_env)
        assert result.exit_code == 0, result.output
        assert "Apply these mapping removals" not in result.output
        pid = _read_pid(config_path)
        assert pid is not None
        assert _pid_alive(pid)
        _wait_until((target / "extra.txt").is_file)
        assert (target / "extra.txt").read_text() == "extra-hub"
        assert (target / "shared.txt").read_text() == "hub-0"
        assert (managed / "extra.txt").read_text() == "extra-hub"
    finally:
        stop_daemon(config_path, ingest_env)


def test_adding_subpath_with_missing_hub_file_errors_and_does_not_create_empty(
    tmp_path: Path,
    ingest_env: dict[str, str],
) -> None:
    """A missing hub file errors that path and does not create an empty target file."""
    managed = tmp_path / "proj-0"
    target = tmp_path / "target-0"
    managed.mkdir()
    target.mkdir()
    (managed / "shared.txt").write_text("hub-0")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "\n".join(
            [
                "proj-0:",
                f"  target: {target}",
                "  subpath:",
                "    - shared.txt",
                "",
            ]
        )
    )
    try:
        start_daemon(config_path, ingest_env)
        stopped = invoke_cli(["--config", str(config_path), "daemon", "stop"], env=ingest_env)
        assert stopped.exit_code == 0, stopped.output
        snapshot_bytes = _snapshot_path(config_path).read_bytes()

        config_path.write_text(
            "\n".join(
                [
                    "proj-0:",
                    f"  target: {target}",
                    "  subpath:",
                    "    - shared.txt",
                    "    - missing.txt",
                    "",
                ]
            )
        )
        result = _invoke_start(config_path, ingest_env)
        assert result.exit_code != 0
        assert "missing.txt" in result.output
        assert not (target / "missing.txt").exists()
        assert (managed / "shared.txt").read_text() == "hub-0"
        assert _snapshot_path(config_path).read_bytes() == snapshot_bytes
        assert _read_pid(config_path) is None or not _pid_alive(_read_pid(config_path) or 0)
    finally:
        stop_daemon(config_path, ingest_env)


def test_editing_config_while_running_has_no_effect_until_reload(
    tmp_path: Path,
    ingest_env: dict[str, str],
) -> None:
    """Edits to config.yml are ignored until an explicit reload."""
    managed = tmp_path / "proj-0"
    target_a = tmp_path / "target-a"
    target_b = tmp_path / "target-b"
    for path in (managed, target_a, target_b):
        path.mkdir()
    (managed / "shared.txt").write_text("hub-0")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"proj-0: {target_a}\n")
    try:
        start_daemon(config_path, ingest_env)
        _wait_until((target_a / "shared.txt").is_file)
        config_path.write_text(f"proj-0:\n  - {target_a}\n  - {target_b}\n")
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            assert not (target_b / "shared.txt").exists()
            time.sleep(_POLL_S)
        reloaded = invoke_cli(["--config", str(config_path), "daemon", "reload"], env=ingest_env)
        assert reloaded.exit_code == 0, reloaded.output
        _wait_until((target_b / "shared.txt").is_file)
        assert (target_b / "shared.txt").read_text() == "hub-0"
        assert (target_a / "shared.txt").read_text() == "hub-0"
        assert (managed / "shared.txt").read_text() == "hub-0"
    finally:
        stop_daemon(config_path, ingest_env)


def test_reload_with_removals_prompts_then_deletes_target_copies_keeps_hub(
    selective_workspace: tuple[Path, Path, Path, Path, Path, Path],
    ingest_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload is a shell prompt; confirmed target removal deletes copies and keeps hub."""
    config_path, proj0, proj1, target_a, target_b, target_c = selective_workspace
    start_daemon(config_path, ingest_env)
    config_path.write_text(
        "\n".join(
            [
                "proj-0:",
                f"  - target: {target_b}",
                "    subpath:",
                "      - shared.txt",
                "      - extra.txt",
                f"proj-1: {target_c}",
                "",
            ]
        )
    )
    monkeypatch.setattr("beyond_local_file.daemon.ingest.stdin_is_tty", lambda: True)
    reloaded = CliRunner().invoke(
        cli,
        ["--config", str(config_path), "daemon", "reload"],
        env=ingest_env,
        input="y\n",
    )
    assert reloaded.exit_code == 0, reloaded.output
    assert "target-remove" in reloaded.output
    assert "Apply these mapping removals" in reloaded.output
    _wait_until(lambda: not (target_a / "shared.txt").exists())
    assert not (target_a / "extra.txt").exists()
    assert (target_b / "shared.txt").read_text() == "hub-0"
    assert (target_b / "extra.txt").read_text() == "extra-hub"
    assert (target_c / "only.txt").read_text() == "hub-1"
    assert (proj0 / "shared.txt").read_text() == "hub-0"
    assert (proj1 / "only.txt").read_text() == "hub-1"
    pid = _read_pid(config_path)
    assert pid is not None
    assert _pid_alive(pid)
