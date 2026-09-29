"""Desktop notices: first-isolation OS banners."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass

from beyond_local_file.held import list_held_copies

from .live import LiveSync

_TITLE_OOS = "blf: out-of-sync"
_TITLE_HELD = "blf: held copy"
_NOTIFY_ENV = "BLF_NOTIFY"
_SEND_LOCK = threading.Lock()


@dataclass(frozen=True)
class Banner:
    """One OS banner: kind in the title, path and managed project in the body."""

    title: str
    body: str


@dataclass(frozen=True)
class IsolationSnapshot:
    """Out-of-sync pairs and held slots observed at one moment."""

    oos: frozenset[tuple[str, str]]
    held: frozenset[tuple[str, str]]


def banners_for(
    *,
    project: str,
    oos_rels: tuple[str, ...],
    held_rels: tuple[str, ...],
) -> tuple[Banner, ...]:
    """Return the banners for newly isolated paths on one managed project.

    Args:
        project: Managed project name.
        oos_rels: Relative paths with a new out-of-sync pair.
        held_rels: Relative paths with a new held slot.

    Returns:
        At most one out-of-sync banner and one held banner.
    """
    banners: list[Banner] = []
    oos_body = _body(oos_rels, project)
    if oos_body is not None:
        banners.append(Banner(title=_TITLE_OOS, body=oos_body))
    held_body = _body(held_rels, project)
    if held_body is not None:
        banners.append(Banner(title=_TITLE_HELD, body=held_body))
    return tuple(banners)


def snapshot_isolation(live: LiveSync) -> IsolationSnapshot:
    """Return the current out-of-sync pairs and held slots for *live*.

    Args:
        live: Observer for one managed project.

    Returns:
        Isolation keys that a later snapshot can diff against.
    """
    oos = frozenset((str(replica), rel) for replica, rel in live.out_of_sync)
    held: set[tuple[str, str]] = set()
    seen: set[str] = set()
    for project in live.projects.values():
        hub = str(project.managed_project_path)
        if hub in seen:
            continue
        seen.add(hub)
        for copy in list_held_copies(project.managed_project_path):
            held.add((str(copy.slot), copy.path))
    return IsolationSnapshot(oos=oos, held=frozenset(held))


def new_isolation_rels(
    before: IsolationSnapshot,
    after: IsolationSnapshot,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return newly isolated relative paths, out-of-sync then held.

    Args:
        before: Snapshot from before persist.
        after: Snapshot from after persist.

    Returns:
        Unique new out-of-sync rels and unique new held rels, each sorted.
    """
    oos_rels = {rel for _replica, rel in after.oos - before.oos}
    held_rels = {rel for _slot, rel in after.held - before.held}
    return tuple(sorted(oos_rels)), tuple(sorted(held_rels))


def emit_isolation_notices(
    *,
    project: str,
    before: IsolationSnapshot,
    after: IsolationSnapshot,
    skip: bool,
) -> None:
    """Send desktop notices for isolation that appeared between two snapshots.

    Args:
        project: Managed project name.
        before: Snapshot from before persist.
        after: Snapshot from after persist.
        skip: True when this isolation was caused by a TTY shell.
    """
    if skip or not _notices_enabled():
        return
    oos_rels, held_rels = new_isolation_rels(before, after)
    for banner in banners_for(project=project, oos_rels=oos_rels, held_rels=held_rels):
        _send(banner.title, banner.body)


def send_banner(title: str, body: str) -> None:
    """Show one OS banner. Tests replace this at the system boundary.

    Args:
        title: Banner title (kind).
        body: Banner body (path and managed project, or a count).
    """
    from desktop_notifier.sync import DesktopNotifierSync  # noqa: PLC0415 -- import OS adapter only when sending

    DesktopNotifierSync(app_name="blf").send(title=title, message=body)


def _notices_enabled() -> bool:
    return os.environ.get(_NOTIFY_ENV) != "0"


def _send(title: str, body: str) -> None:
    with _SEND_LOCK:
        try:
            send_banner(title, body)
        except Exception:
            return


def _body(rels: tuple[str, ...], project: str) -> str | None:
    unique = tuple(dict.fromkeys(rels))
    if not unique:
        return None
    if len(unique) == 1:
        return f"{unique[0]} in {project}"
    return f"{len(unique)} paths in {project}"
