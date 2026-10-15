"""`blf debug notice` posts one desktop notice and says whether this process showed it."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from beyond_local_file.cli import cli

_TITLE = "blf: notice check"
_BODY = "If you can see this, the desktop notice works on this machine."


def test_notice_sends_the_check_banner(monkeypatch: pytest.MonkeyPatch) -> None:
    """The command sends one fixed check banner through the daemon sender."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "beyond_local_file.operations.notice.send_banner",
        lambda title, body: sent.append((title, body)),
    )

    result = CliRunner().invoke(cli, ["debug", "notice"])

    assert result.exit_code == 0
    assert sent == [(_TITLE, _BODY)]
    assert result.output == f"Sent desktop notice: {_TITLE} — {_BODY}\n"


def test_send_error_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """A sender exception is the command result, not a traceback."""

    def _fail(title: str, body: str) -> None:
        del title, body
        raise RuntimeError("denied")

    monkeypatch.setattr("beyond_local_file.operations.notice.send_banner", _fail)

    result = CliRunner().invoke(cli, ["debug", "notice"])

    assert result.exit_code == 1
    assert result.output == "Desktop notice was not shown: denied.\n"


def test_notice_is_not_a_top_level_command() -> None:
    """The probe lives under debug. The old top-level command is gone."""
    missing = CliRunner().invoke(cli, ["notice", "--help"])
    assert missing.exit_code != 0
    assert "no such command" in missing.output.lower()

    listed = CliRunner().invoke(cli, ["debug", "--help"])
    assert listed.exit_code == 0
    assert "notice" in listed.output
