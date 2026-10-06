"""Desktop notices: first-isolation OS banners."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass

from .oos_held import OosAndHeld, new_rels

_TITLE_OOS = "blf: out-of-sync"
_TITLE_HELD = "blf: held copy"
_NOTIFY_ENV = "BLF_NOTIFY"
_SEND_LOCK = threading.Lock()


@dataclass(frozen=True)
class Banner:
    """One OS banner: kind in the title, path and managed project in the body."""

    title: str
    body: str


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


def emit_desktop_notices(
    *,
    project: str,
    before: OosAndHeld,
    after: OosAndHeld,
    skip: bool,
) -> None:
    """Send desktop notices for out-of-sync marks or held copies that appeared between two listings.

    Args:
        project: Managed project name.
        before: Listing from before persist.
        after: Listing from after persist.
        skip: True when a TTY shell caused the new rows.
    """
    if skip or not _notices_enabled():
        return
    oos_rels, held_rels = new_rels(before, after)
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
