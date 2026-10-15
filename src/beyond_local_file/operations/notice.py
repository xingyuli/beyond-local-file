"""Send one desktop notice so the operator can see whether this machine shows it."""

from __future__ import annotations

import click

from beyond_local_file.daemon.notice import send_banner

_TITLE = "blf: notice check"
_BODY = "If you can see this, the desktop notice works on this machine."


def run_notice_check() -> int:
    """Post one check banner through the daemon's sender.

    Returns:
        0 when the banner was handed to the OS, 1 when the sender failed.
    """
    try:
        send_banner(_TITLE, _BODY)
    except Exception as exc:
        click.echo(f"Desktop notice was not shown: {exc}.")
        return 1
    click.echo(f"Sent desktop notice: {_TITLE} — {_BODY}")
    return 0
