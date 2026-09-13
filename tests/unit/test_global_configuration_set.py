"""Global configuration set: one process loads every mapping file in ~/.blf/config."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from beyond_local_file.cli import cli
from beyond_local_file.daemon.process import state_dir

_WORKER_FLAG = "--worker"
_POLL_S = 0.05


def _invoke(args: list[str], env: dict[str, str] | None = None) -> Result:
    return CliRunner().invoke(cli, args, env=env)


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


def _read_pid_file(path: Path) -> int | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    return int(text.splitlines()[0])


def _global_run_dir(home: Path) -> Path:
    return home / ".blf" / "run" / "global"


def _write_pointer(home: Path, mapping_files: list[Path]) -> Path:
    path = home / ".blf" / "config"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["config_file:"]
    lines.extend(f"  - {mapping}" for mapping in mapping_files)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_hub(root: Path, project_name: str, target: Path, item: str, content: str) -> Path:
    managed = root / project_name
    managed.mkdir(parents=True)
    (managed / item).write_text(content)
    target.mkdir(parents=True, exist_ok=True)
    config_path = root / "config.yml"
    config_path.write_text(f"{project_name}: {target}\n")
    return config_path


def _stop_global(env: dict[str, str], home: Path) -> None:
    _invoke(["daemon", "stop"], env=env)
    pid = _read_pid_file(_global_run_dir(home) / "daemon.pid")
    if pid is not None and _pid_alive(pid):
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and _pid_alive(pid):
            time.sleep(_POLL_S)


def _stop_singleton(config_path: Path, env: dict[str, str]) -> None:
    _invoke(["--config", str(config_path), "daemon", "stop"], env=env)
    pid = _read_pid_file(state_dir(config_path) / "daemon.pid")
    if pid is not None and _pid_alive(pid):
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and _pid_alive(pid):
            time.sleep(_POLL_S)


def _worker_lines(*needles: str) -> list[str]:
    listed = subprocess.check_output(["ps", "-ax", "-o", "pid=,command="], text=True)
    return [line for line in listed.splitlines() if _WORKER_FLAG in line and all(needle in line for needle in needles)]


@pytest.fixture
def daemon_env(isolated_home: dict[str, str]) -> dict[str, str]:
    return isolated_home


@pytest.fixture
def two_hubs(tmp_path: Path, daemon_env: dict[str, str]) -> Iterator[tuple[Path, Path, Path, Path, Path]]:
    home = Path(daemon_env["BLF_HOME"])
    quvanai = tmp_path / "quvanai-local-files"
    viclau = tmp_path / "viclau-local-files"
    quvanai_target = tmp_path / "target-quvanai"
    viclau_target = tmp_path / "target-viclau"
    quvanai_config = _write_hub(quvanai, "quvanai-files", quvanai_target, "from-quvanai.txt", "q")
    viclau_config = _write_hub(viclau, "viclau-local-files", viclau_target, "from-viclau.txt", "v")
    _write_pointer(home, [quvanai_config, viclau_config])
    try:
        yield home, quvanai_config, viclau_config, quvanai_target, viclau_target
    finally:
        _stop_global(daemon_env, home)
        _stop_singleton(quvanai_config, daemon_env)
        _stop_singleton(viclau_config, daemon_env)


def test_dot_blfrc_is_not_read(
    tmp_path: Path,
    daemon_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """~/.blfrc is not a pointer list; CWD config.yml is used when ~/.blf/config is absent."""
    home = Path(daemon_env["BLF_HOME"])
    ignored = tmp_path / "ignored-hub"
    ignored_target = tmp_path / "ignored-target"
    ignored_config = _write_hub(ignored, "ignored-files", ignored_target, "ignored.txt", "no")
    (home / ".blfrc").write_text(f"config_file: {ignored_config}\n")

    cwd = tmp_path / "cwd-hub"
    cwd_target = tmp_path / "cwd-target"
    cwd_config = _write_hub(cwd, "cwd-files", cwd_target, "cwd.txt", "yes")
    monkeypatch.chdir(cwd)
    try:
        started = _invoke(["daemon", "start"], env=daemon_env)
        assert started.exit_code == 0, started.output
        assert (state_dir(cwd_config) / "daemon.pid").is_file()
        assert not _global_run_dir(home).exists()
        assert (cwd_target / "cwd.txt").read_text() == "yes"
        assert not (ignored_target / "ignored.txt").exists()
    finally:
        _stop_singleton(cwd_config, daemon_env)


def test_global_config_is_the_pointer_list(
    two_hubs: tuple[Path, Path, Path, Path, Path],
    daemon_env: dict[str, str],
) -> None:
    """~/.blf/config lists mapping files; start without -c uses run/global/."""
    home, _quvanai_config, _viclau_config, quvanai_target, viclau_target = two_hubs

    started = _invoke(["daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output

    run_dir = _global_run_dir(home)
    assert (run_dir / "daemon.pid").is_file()
    assert (run_dir / "daemon.port").is_file()
    assert (run_dir / "daemon.ready").is_file()
    assert (run_dir / "daemon.log").is_file()
    assert (run_dir / "mapping-snapshot.yml").is_file()
    assert (run_dir / "baseline.yml").is_file()
    assert (quvanai_target / "from-quvanai.txt").read_text() == "q"
    assert (viclau_target / "from-viclau.txt").read_text() == "v"


def test_one_process_loads_both_mapping_files_and_link_check_shows_both(
    two_hubs: tuple[Path, Path, Path, Path, Path],
    daemon_env: dict[str, str],
) -> None:
    """blf link check (no -c) shows both mapping files through one daemon process."""
    home, quvanai_config, viclau_config, _quvanai_target, _viclau_target = two_hubs
    global_config = home / ".blf" / "config"

    started = _invoke(["daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output

    pid = _read_pid_file(_global_run_dir(home) / "daemon.pid")
    assert pid is not None
    assert _pid_alive(pid)

    checked = _invoke(["link", "check"], env=daemon_env)
    assert checked.exit_code == 0, checked.output
    assert "quvanai-files" in checked.output
    assert "viclau-local-files" in checked.output

    workers = _worker_lines(str(global_config))
    assert len(workers) == 1, workers
    assert str(pid) in workers[0]
    assert not _worker_lines(str(quvanai_config))
    assert not _worker_lines(str(viclau_config))
    assert not (state_dir(quvanai_config) / "daemon.pid").exists()
    assert not (state_dir(viclau_config) / "daemon.pid").exists()


def test_resolution_order_explicit_config_beats_global(
    two_hubs: tuple[Path, Path, Path, Path, Path],
    daemon_env: dict[str, str],
    tmp_path: Path,
) -> None:
    """-c of a yaml not in a running set is a singleton and does not start the global worker."""
    home, _quvanai_config, _viclau_config, quvanai_target, viclau_target = two_hubs
    extra_target = tmp_path / "target-extra"
    extra_config = _write_hub(tmp_path / "extra-hub", "extra-files", extra_target, "extra.txt", "e")
    try:
        started = _invoke(["--config", str(extra_config), "daemon", "start"], env=daemon_env)
        assert started.exit_code == 0, started.output
        assert (state_dir(extra_config) / "daemon.pid").is_file()
        assert not _global_run_dir(home).exists()
        assert (extra_target / "extra.txt").read_text() == "e"
        assert not (quvanai_target / "from-quvanai.txt").exists()
        assert not (viclau_target / "from-viclau.txt").exists()
    finally:
        _stop_singleton(extra_config, daemon_env)


def test_resolution_order_global_beats_cwd_config_yml(
    two_hubs: tuple[Path, Path, Path, Path, Path],
    daemon_env: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With ~/.blf/config present, CWD config.yml is not a singleton set."""
    home, _quvanai_config, _viclau_config, quvanai_target, _viclau_target = two_hubs
    cwd = tmp_path / "cwd-hub"
    cwd_target = tmp_path / "cwd-target"
    cwd_config = _write_hub(cwd, "cwd-files", cwd_target, "cwd.txt", "yes")
    monkeypatch.chdir(cwd)

    started = _invoke(["daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output
    assert (_global_run_dir(home) / "daemon.pid").is_file()
    assert not (state_dir(cwd_config) / "daemon.pid").exists()
    assert (quvanai_target / "from-quvanai.txt").read_text() == "q"
    assert not (cwd_target / "cwd.txt").exists()


def test_shell_dash_c_of_loaded_yaml_uses_running_owner(
    two_hubs: tuple[Path, Path, Path, Path, Path],
    daemon_env: dict[str, str],
) -> None:
    """-c of a yaml already in the running global set talks to that process."""
    home, _quvanai_config, viclau_config, _quvanai_target, _viclau_target = two_hubs

    started = _invoke(["daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output
    pid = _read_pid_file(_global_run_dir(home) / "daemon.pid")
    assert pid is not None

    checked = _invoke(["--config", str(viclau_config), "link", "check"], env=daemon_env)
    assert checked.exit_code == 0, checked.output
    assert "viclau-local-files" in checked.output
    assert "quvanai-files" in checked.output
    assert _read_pid_file(_global_run_dir(home) / "daemon.pid") == pid
    assert not (state_dir(viclau_config) / "daemon.pid").exists()
    assert len(_worker_lines(str(home / ".blf" / "config"))) == 1


def test_daemon_start_of_overlapping_set_errors_and_names_owner(
    two_hubs: tuple[Path, Path, Path, Path, Path],
    daemon_env: dict[str, str],
) -> None:
    """Starting a set that shares a mapping file with a running set names the owner."""
    home, _quvanai_config, viclau_config, _quvanai_target, _viclau_target = two_hubs

    started = _invoke(["daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output
    pid = _read_pid_file(_global_run_dir(home) / "daemon.pid")
    assert pid is not None

    overlapping = _invoke(["--config", str(viclau_config), "daemon", "start"], env=daemon_env)
    assert overlapping.exit_code != 0
    assert str(viclau_config) in overlapping.output
    assert "global" in overlapping.output.lower()
    assert str(pid) in overlapping.output
    assert _read_pid_file(_global_run_dir(home) / "daemon.pid") == pid
    assert _pid_alive(pid)
    assert not (state_dir(viclau_config) / "daemon.pid").exists()


def test_global_start_errors_when_singleton_already_loaded_mapping_file(
    tmp_path: Path,
    daemon_env: dict[str, str],
) -> None:
    """Global start fails if a running singleton already loaded one of its mapping files."""
    home = Path(daemon_env["BLF_HOME"])
    hub = tmp_path / "viclau-local-files"
    target = tmp_path / "target"
    config_path = _write_hub(hub, "viclau-local-files", target, "item.txt", "v")
    other = tmp_path / "other-hub"
    other_target = tmp_path / "other-target"
    other_config = _write_hub(other, "other-files", other_target, "other.txt", "o")
    _write_pointer(home, [config_path, other_config])
    try:
        started = _invoke(["--config", str(config_path), "daemon", "start"], env=daemon_env)
        assert started.exit_code == 0, started.output
        pid = _read_pid_file(state_dir(config_path) / "daemon.pid")
        assert pid is not None

        overlapping = _invoke(["daemon", "start"], env=daemon_env)
        assert overlapping.exit_code != 0
        assert str(config_path) in overlapping.output
        assert str(pid) in overlapping.output
        assert not (_global_run_dir(home) / "daemon.pid").exists()
        assert _pid_alive(pid)
    finally:
        _stop_global(daemon_env, home)
        _stop_singleton(config_path, daemon_env)


def test_link_check_revlink_remove_without_c_use_global_process(
    two_hubs: tuple[Path, Path, Path, Path, Path],
    daemon_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """revlink, remove, and link check without -c talk to the global process."""
    home, _quvanai_config, _viclau_config, _quvanai_target, viclau_target = two_hubs

    started = _invoke(["daemon", "start"], env=daemon_env)
    assert started.exit_code == 0, started.output
    pid = _read_pid_file(_global_run_dir(home) / "daemon.pid")
    assert pid is not None

    status = _invoke(["daemon", "status"], env=daemon_env)
    assert status.exit_code == 0, status.output
    assert str(pid) in status.output

    monkeypatch.chdir(viclau_target)
    created = viclau_target / "adopted.txt"
    created.write_text("adopt me")
    adopted = _invoke(["revlink", "create", "adopted.txt"], env=daemon_env)
    assert adopted.exit_code == 0, adopted.output
    hub_copy = viclau_target.parent / "viclau-local-files" / "viclau-local-files" / "adopted.txt"
    assert hub_copy.read_text() == "adopt me"

    checked = _invoke(["link", "check"], env=daemon_env)
    assert checked.exit_code == 0, checked.output
    assert "viclau-local-files" in checked.output
    assert "quvanai-files" in checked.output

    removed = _invoke(["remove", "adopted.txt"], env=daemon_env)
    assert removed.exit_code == 0, removed.output
    assert not hub_copy.exists()
    assert _read_pid_file(_global_run_dir(home) / "daemon.pid") == pid
    assert _pid_alive(pid)
