"""Process-wide locks so two worker units do not splice the same file."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

_guard = Lock()
_locks: dict[str, Lock] = {}


@contextmanager
def locked_path(path: Path) -> Iterator[None]:
    """Hold an exclusive lock for *path* for the duration of the with-block.

    Args:
        path: Mapping yaml or git exclude file two worker units might splice.
    """
    key = str(path.resolve())
    with _guard:
        lock = _locks.setdefault(key, Lock())
    with lock:
        yield
