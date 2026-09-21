"""Pidfile, spawn, stop, status, and log following for the daemon process."""

from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import click

from beyond_local_file.blfrc import (
    get_home_directory,
    global_config_path,
    is_global_config_path,
    resolve_global_mapping_files,
    runtime_home,
)
from beyond_local_file.constants import HUB_LOCAL_DIR

PID_NAME = "daemon.pid"
LOG_NAME = "daemon.log"
READY_NAME = "daemon.ready"
PORT_NAME = "daemon.port"
MAPPING_FILES_NAME = "mapping-files"
GLOBAL_SET_ID = "global"
_START_TIMEOUT_S = 30.0
_STOP_TIMEOUT_S = 10.0
_POLL_S = 0.05
_FOLLOW_POLL_S = 0.2


def singleton_set_id(config_path: Path) -> str:
    """Return the run-directory name for the singleton set of *config_path*.

    Args:
        config_path: Path to the loaded mapping file.

    Returns:
        ``file-<sha256 of the resolved mapping yaml path>``.
    """
    digest = hashlib.sha256(str(config_path.resolve()).encode("utf-8")).hexdigest()
    return f"file-{digest}"


def set_id_for(config_path: Path) -> str:
    """Return the run-directory name for the configuration set of *config_path*.

    Args:
        config_path: Set identity path (global config or a mapping yaml).

    Returns:
        ``global`` or ``file-<sha256 of the resolved mapping yaml path>``.
    """
    if is_global_config_path(config_path):
        return GLOBAL_SET_ID
    return singleton_set_id(config_path)


def state_dir(config_path: Path) -> Path:
    """Return the set run directory for the configuration set of *config_path*.

    Args:
        config_path: Set identity path (global config or a mapping yaml).

    Returns:
        Directory that holds pid, log, port, snapshot, and item-document baseline.
    """
    return runtime_home() / "run" / set_id_for(config_path)


def mapping_files_for(config_path: Path) -> list[Path]:
    """Return the mapping files loaded by the set identified by *config_path*.

    Args:
        config_path: Set identity path (global config or a mapping yaml).

    Returns:
        Resolved mapping yaml paths.
    """
    if is_global_config_path(config_path):
        return list(resolve_global_mapping_files() or [])
    return [Path(config_path).resolve()]


def running_owner_of(mapping_file: Path) -> Path | None:
    """Return the identity path of the running set that loaded *mapping_file*.

    Args:
        mapping_file: A mapping yaml path.

    Returns:
        Global config path or the singleton mapping path, or None.
    """
    resolved = mapping_file.resolve()
    overlap = overlapping_running_set([resolved])
    if overlap is None:
        return None
    identity, _pid, _mapping = overlap
    return identity


def overlapping_running_set(mapping_files: list[Path]) -> tuple[Path, int, Path] | None:
    """Return a running set that already loaded one of *mapping_files*.

    Args:
        mapping_files: Mapping yaml paths the caller wants to load.

    Returns:
        ``(identity_path, pid, overlapping_mapping_file)`` or None.
    """
    wanted = {path.resolve() for path in mapping_files}
    if not wanted:
        return None
    run_root = runtime_home() / "run"
    if not run_root.is_dir():
        return None
    for entry in sorted(run_root.iterdir(), key=lambda path: path.name):
        if not entry.is_dir():
            continue
        pid = _read_pid_file(entry / PID_NAME)
        if pid is None or not pid_is_alive(pid):
            continue
        loaded = _loaded_mapping_files(entry)
        if not loaded and entry.name != GLOBAL_SET_ID:
            loaded = [path for path in wanted if singleton_set_id(path) == entry.name]
        for loaded_path in loaded:
            if loaded_path.resolve() in wanted:
                identity = _identity_path_for_run_dir(entry, loaded)
                if identity is None:
                    continue
                return identity, pid, loaded_path.resolve()
    return None


def pid_path(config_path: Path) -> Path:
    """Return the daemon pidfile path.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        Path to ``daemon.pid``.
    """
    return state_dir(config_path) / PID_NAME


def log_path(config_path: Path) -> Path:
    """Return the daemon log path.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        Path to ``daemon.log``.
    """
    return state_dir(config_path) / LOG_NAME


def ready_path(config_path: Path) -> Path:
    """Return the daemon ready-marker path.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        Path to ``daemon.ready``.
    """
    return state_dir(config_path) / READY_NAME


def port_path(config_path: Path) -> Path:
    """Return the daemon request-port file path.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        Path to ``daemon.port``.
    """
    return state_dir(config_path) / PORT_NAME


def read_pid(config_path: Path) -> int | None:
    """Read the pidfile if it exists and contains an integer.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        The stored pid, or None when missing or invalid.
    """
    return _read_pid_file(pid_path(config_path))


def pid_is_alive(pid: int) -> bool:
    """Return whether *pid* currently names a live process.

    Reaps *pid* when it is a zombie child of this process so a dead worker
    is not reported as running.

    Args:
        pid: Process id to probe.

    Returns:
        True if the process exists and is not a reaped zombie child.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        return _pid_is_alive_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return not _reap_if_child(pid)


def is_running(config_path: Path) -> bool:
    """Return whether a live daemon is recorded for *config_path*.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        True if the pidfile names a live process.
    """
    pid = read_pid(config_path)
    return pid is not None and pid_is_alive(pid)


def spawn_and_wait(config_path: Path) -> int:
    """Spawn the daemon worker and wait until it is ready.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        0 when the daemon is running, 1 on error.
    """
    if is_running(config_path):
        click.echo(f"Error: daemon is already running (pid {read_pid(config_path)})")
        return 1

    mapping_files = mapping_files_for(config_path)
    for mapping in mapping_files:
        for path in _remove_hub_local_state(mapping):
            click.echo(str(path))
    _clear_runtime_files(config_path)
    _write_mapping_files(config_path, mapping_files)
    log_file = log_path(config_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_handle = open(log_file, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    try:
        worker_env = os.environ.copy()
        worker_env["BLF_HOME"] = str(get_home_directory())
        proc = subprocess.Popen(
            _worker_argv(config_path),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=worker_env,
            cwd=str(config_path.parent),
            **_popen_kwargs(),
        )
    finally:
        log_handle.close()

    _write_pid(config_path, proc.pid)
    if not _wait_for_port(config_path, proc):
        _clear_runtime_files(config_path)
        click.echo("Error: daemon failed to start")
        _echo_log_tail(log_file)
        return 1
    from .client import wait_until_ready  # noqa: PLC0415

    if wait_until_ready(config_path) != 0 or proc.poll() is not None:
        _clear_runtime_files(config_path)
        click.echo("Error: daemon failed to start")
        _echo_log_tail(log_file)
        return 1

    click.echo(f"Daemon started (pid {proc.pid})")
    return 0


def stop_process(config_path: Path) -> int:
    """Terminate the daemon if it is running.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        0 after the daemon is not running.
    """
    pid = read_pid(config_path)
    if pid is None or not pid_is_alive(pid):
        _clear_runtime_files(config_path)
        click.echo("Daemon is not running")
        return 0

    _terminate_pid(pid)
    _reap_if_child(pid)
    _clear_runtime_files(config_path)
    click.echo("Daemon stopped")
    return 0


def print_status(config_path: Path) -> int:
    """Print whether the daemon is running, including phase and pid.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        0 after printing status.
    """
    pid = read_pid(config_path)
    if pid is None or not pid_is_alive(pid):
        click.echo("Daemon is not running")
        return 0
    from .client import send_when_up  # noqa: PLC0415

    try:
        response = send_when_up(config_path, {"op": "status"})
    except OSError:
        click.echo(f"Daemon is running (pid {pid})")
        return 0
    stdout = response.get("stdout") or ""
    if stdout:
        click.echo(stdout, nl=not str(stdout).endswith("\n"))
    return 0


def follow_log(config_path: Path) -> int:
    """Print the daemon log and follow new lines until interrupted.

    Ctrl-C stops following; the daemon process is left running.

    Args:
        config_path: Path to the loaded config file.

    Returns:
        0 on a clean interrupt, 1 if the log file is missing.
    """
    path = log_path(config_path)
    if not path.exists():
        click.echo("Daemon log not found")
        return 1
    try:
        with open(path, encoding="utf-8") as handle:
            while True:
                line = handle.readline()
                if line:
                    click.echo(line, nl=False)
                else:
                    time.sleep(_FOLLOW_POLL_S)
    except KeyboardInterrupt:
        return 0


def write_ready(config_path: Path) -> None:
    """Mark the daemon worker as ready.

    Args:
        config_path: Path to the loaded config file.
    """
    path = ready_path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ready\n", encoding="utf-8")


def _worker_argv(config_path: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "beyond_local_file",
        "--config",
        str(config_path),
        "daemon",
        "start",
        "--worker",
    ]


def _popen_kwargs() -> dict[str, object]:
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        return {"creationflags": flags}
    return {"start_new_session": True}


def _write_pid(config_path: Path, pid: int) -> None:
    path = pid_path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pid}\n", encoding="utf-8")


def _clear_runtime_files(config_path: Path) -> None:
    for path in (pid_path(config_path), ready_path(config_path), port_path(config_path)):
        path.unlink(missing_ok=True)


def _remove_hub_local_state(config_path: Path) -> list[Path]:
    leftover = config_path.parent / HUB_LOCAL_DIR
    try:
        if leftover.resolve() == runtime_home().resolve():
            return []
    except OSError:
        return []
    if leftover.is_symlink() or leftover.is_file():
        leftover.unlink()
        return [leftover]
    if not leftover.is_dir():
        return []
    removed: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(leftover, topdown=False):
        current = Path(dirpath)
        removed.extend(current / name for name in filenames)
        removed.append(current)
    shutil.rmtree(leftover)
    return removed


def _wait_for_port(config_path: Path, proc: subprocess.Popen[bytes]) -> bool:
    marker = port_path(config_path)
    deadline = time.monotonic() + _START_TIMEOUT_S
    while time.monotonic() < deadline:
        if marker.exists() and marker.read_text(encoding="utf-8").strip():
            return True
        if proc.poll() is not None:
            return False
        time.sleep(_POLL_S)
    return False


def _reap_if_child(pid: int) -> bool:
    """Reap *pid* when it is a dead child of this process.

    Args:
        pid: Process id that may be a zombie child.

    Returns:
        True if the child was reaped (and is therefore not running).
    """
    if os.name == "nt":
        return False
    try:
        waited_pid, _status = os.waitpid(pid, os.WNOHANG)
    except (ChildProcessError, OSError):
        return False
    return waited_pid == pid


def _terminate_pid(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        return
    deadline = time.monotonic() + _STOP_TIMEOUT_S
    while time.monotonic() < deadline:
        if _reap_if_child(pid) or not pid_is_alive(pid):
            return
        time.sleep(_POLL_S)
    if os.name != "nt":
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            return
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if _reap_if_child(pid) or not pid_is_alive(pid):
                return
            time.sleep(_POLL_S)


def _echo_log_tail(path: Path, *, lines: int = 20) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    tail = "\n".join(text.splitlines()[-lines:])
    if tail:
        click.echo(tail)


def _write_mapping_files(config_path: Path, mapping_files: list[Path]) -> None:
    path = state_dir(config_path) / MAPPING_FILES_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{item.resolve()}\n" for item in mapping_files), encoding="utf-8")


def _read_mapping_files(run_dir: Path) -> list[Path]:
    path = run_dir / MAPPING_FILES_NAME
    if not path.exists():
        return []
    files: list[Path] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            files.append(Path(text))
    return files


def _loaded_mapping_files(run_dir: Path) -> list[Path]:
    files = _read_mapping_files(run_dir)
    if files:
        return files
    if run_dir.name == GLOBAL_SET_ID:
        return list(resolve_global_mapping_files() or [])
    return []


def _identity_path_for_run_dir(run_dir: Path, loaded: list[Path]) -> Path | None:
    if run_dir.name == GLOBAL_SET_ID:
        return global_config_path()
    if loaded:
        return loaded[0].resolve()
    return None


def _read_pid_file(path: Path) -> int | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    try:
        return int(text.splitlines()[0])
    except ValueError:
        return None


def _pid_is_alive_windows(pid: int) -> bool:
    import ctypes  # noqa: PLC0415

    synch = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(synch, 0, pid)  # type: ignore[attr-defined]
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
        return True
    return False
