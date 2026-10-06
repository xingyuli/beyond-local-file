"""Daemon operation results over IPC."""

from pathlib import Path

import pytest

from beyond_local_file.daemon.client import _print_response
from beyond_local_file.daemon.handlers import handle_request
from beyond_local_file.operations.result import FailedResult, from_ipc, render, to_ipc


def test_failed_result_round_trips_through_ipc() -> None:
    """FailedResult survives to_ipc then from_ipc."""
    result = FailedResult(1, ("Stopped",))
    assert to_ipc(result) == {"exit_code": 1, "kind": "failed", "lines": ["Stopped"]}
    assert from_ipc(to_ipc(result)) == result


def test_render_failed_result_matches_today_stopped_transcript() -> None:
    """FailedResult Stopped prints as today's Stopped newline."""
    assert render(FailedResult(1, ("Stopped",))) == "Stopped\n"


def test_print_response_echoes_stdout_when_kind_is_missing(capsys: pytest.CaptureFixture[str]) -> None:
    """Leftover status transcripts still print stdout."""
    code = _print_response({"exit_code": 0, "stdout": "Daemon is running (pid 12, phase ready)\n"})
    assert code == 0
    assert capsys.readouterr().out == "Daemon is running (pid 12, phase ready)\n"


def test_print_response_renders_failed_result(capsys: pytest.CaptureFixture[str]) -> None:
    """A failed envelope prints the same Stopped transcript as today."""
    code = _print_response(to_ipc(FailedResult(1, ("Stopped",))))
    assert code == 1
    assert capsys.readouterr().out == "Stopped\n"


def test_unknown_op_returns_failed_result(tmp_path: Path) -> None:
    """An unknown daemon operation is a failed envelope, not a stdout blob."""
    response = handle_request(tmp_path / "config.yml", {"op": "nope"})
    assert from_ipc(response) == FailedResult(1, ("Error: unknown daemon operation 'nope'",))
    assert render(from_ipc(response)) == "Error: unknown daemon operation 'nope'\n"
