"""Daemon operation results over IPC."""

from pathlib import Path

import pytest

from beyond_local_file.daemon.client import _print_response
from beyond_local_file.daemon.handlers import handle_request
from beyond_local_file.operations.link_check import CopyCheckDetails, GitExcludeStatus, LinkCheckResult
from beyond_local_file.operations.result import (
    CheckResult,
    CheckRow,
    CreateResult,
    FailedResult,
    from_ipc,
    payload_text,
    render,
    to_ipc,
)
from beyond_local_file.options import OutputFormat


def test_failed_result_round_trips_through_ipc() -> None:
    """FailedResult survives to_ipc then from_ipc."""
    result = FailedResult(1, ("Stopped",))
    assert to_ipc(result) == {"exit_code": 1, "kind": "failed", "lines": ["Stopped"]}
    assert from_ipc(to_ipc(result)) == result


def test_render_failed_result_matches_today_stopped_transcript() -> None:
    """FailedResult Stopped prints as today's Stopped newline."""
    assert render(FailedResult(1, ("Stopped",))) == "Stopped\n"


def test_check_result_round_trips_through_ipc() -> None:
    """CheckResult survives to_ipc then from_ipc, with git sets as sorted lists on the wire."""
    result = CheckResult(
        exit_code=0,
        extra_exclude=True,
        output_format=OutputFormat.TABLE,
        rows=(
            CheckRow(
                project_name="lab-app",
                target_path="/tmp/alpha",
                skip=None,
                copy=LinkCheckResult(
                    exists=["example"],
                    missing=[],
                    incorrect=[],
                    details=CopyCheckDetails(in_sync=["example"]),
                ),
                git=GitExcludeStatus(present={"example"}, missing=set(), extra={"z-extra", "a-extra"}),
            ),
            CheckRow(
                project_name="lab-app",
                target_path="/tmp/missing",
                skip="missing_target",
                copy=None,
                git=None,
            ),
        ),
        not_found=None,
    )
    payload = to_ipc(result)
    assert payload["kind"] == "check"
    assert payload["rows"][0]["git"]["extra"] == ["a-extra", "z-extra"]
    assert payload["rows"][0]["git"]["present"] == ["example"]
    assert "unit" not in payload["rows"][0]
    assert from_ipc(payload) == result


def test_render_check_not_found_is_one_line(capsys: pytest.CaptureFixture[str]) -> None:
    """A missing project name renders as today's not-found line."""
    result = CheckResult(
        exit_code=1,
        extra_exclude=False,
        output_format=OutputFormat.TABLE,
        rows=(),
        not_found="Project 'lab-app' not found in config",
    )
    assert render(result) == "Project 'lab-app' not found in config\n"
    assert payload_text(to_ipc(result)) == "Project 'lab-app' not found in config\n"
    code = _print_response(to_ipc(result))
    assert code == 1
    assert capsys.readouterr().out == "Project 'lab-app' not found in config\n"


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


def _create_result(**fields: object) -> CreateResult:
    """Return a CreateResult with lab-app / alpha / example stand-ins."""
    values: dict[str, object] = {
        "exit_code": 0,
        "dry_run": False,
        "errors": (),
        "already_managed": None,
        "force_overwrite": None,
        "source": "/tmp/alpha/example",
        "dest": "/tmp/lab-app/example",
        "git_exclude": "added",
        "git_exclude_name": "example",
        "fan_out": (("/tmp/lab-app/example", "/tmp/example/example"),),
        "config_entry": "example",
        "persist_warning": None,
    }
    values.update(fields)
    return CreateResult(**values)  # type: ignore[arg-type]


def test_create_result_round_trips_through_ipc() -> None:
    """CreateResult survives to_ipc then from_ipc, with fan-out pairs as lists on the wire."""
    result = _create_result()
    payload = to_ipc(result)
    assert payload["kind"] == "create"
    assert payload["fan_out"] == [["/tmp/lab-app/example", "/tmp/example/example"]]
    assert payload["git_exclude"] == "added"
    assert payload["errors"] == []
    assert from_ipc(payload) == result


def test_render_create_success_story_matches_today_order() -> None:
    """Create success prints force, copy, target, git, config, then fan-out."""
    result = _create_result(force_overwrite="/tmp/lab-app/example")
    assert render(result) == (
        "Warning: overwriting existing managed copy at /tmp/lab-app/example\n"
        "Copying /tmp/alpha/example -> /tmp/lab-app/example\n"
        "✓ Target path left in place: /tmp/alpha/example\n"
        "Added 'example' to .git/info/exclude\n"
        "Added 'example' to config subpath list\n"
        "Fan-out /tmp/lab-app/example -> /tmp/example/example\n"
    )
    assert payload_text(to_ipc(result)) == render(result)


def test_render_create_dry_run_prefixes_each_line() -> None:
    """Dry-run is data; render prefixes each story line with [dry-run]."""
    result = _create_result(dry_run=True, force_overwrite=None, persist_warning=None)
    assert render(result) == (
        "[dry-run] Copying /tmp/alpha/example -> /tmp/lab-app/example\n"
        "[dry-run] ✓ Target path left in place: /tmp/alpha/example\n"
        "[dry-run] Added 'example' to .git/info/exclude\n"
        "[dry-run] Added 'example' to config subpath list\n"
        "[dry-run] Fan-out /tmp/lab-app/example -> /tmp/example/example\n"
    )


def test_render_create_errors_and_already_managed() -> None:
    """Errors take Error: prefix; already-managed is the info line at exit 0."""
    missing = _create_result(
        exit_code=1,
        errors=("Path does not exist: /tmp/alpha/example",),
        git_exclude=None,
        git_exclude_name=None,
        fan_out=(),
        config_entry=None,
    )
    assert render(missing) == "Error: Path does not exist: /tmp/alpha/example\n"
    dry_err = _create_result(exit_code=1, dry_run=True, errors=("Path is already a symlink: /tmp/alpha/example",))
    assert render(dry_err) == "[dry-run] Error: Path is already a symlink: /tmp/alpha/example\n"
    managed = _create_result(
        already_managed=(
            "'.kiro' is a managed symlink — '.kiro/specs/foo.txt' is already managed through it. Nothing to do."
        ),
        git_exclude=None,
        git_exclude_name=None,
        fan_out=(),
        config_entry=None,
    )
    assert render(managed) == (
        "'.kiro' is a managed symlink — '.kiro/specs/foo.txt' is already managed through it. Nothing to do.\n"
    )


def test_render_create_persist_warning_is_last_and_keeps_exit_zero() -> None:
    """Persist failure is a field; the warning is last and exit_code stays 0."""
    result = _create_result(persist_warning="disk full")
    assert result.exit_code == 0
    assert render(result).endswith("Warning: could not persist mapping snapshot: disk full\n")
