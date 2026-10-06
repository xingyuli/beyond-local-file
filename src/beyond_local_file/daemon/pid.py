"""Pidfile read and process-liveness probes."""

from __future__ import annotations

import os
from pathlib import Path


def read_pid_file(path: Path) -> int | None:
    """Read a pidfile if it exists and contains an integer.

    Args:
        path: Path to the pidfile.

    Returns:
        The stored pid, or None when missing or invalid.
    """
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    try:
        return int(text.splitlines()[0])
    except ValueError:
        return None


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


def _pid_is_alive_windows(pid: int) -> bool:
    import ctypes  # noqa: PLC0415

    synch = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(synch, 0, pid)  # type: ignore[attr-defined]
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
        return True
    return False
