"""Daemon operation results over IPC."""

from pathlib import Path

import pytest

from beyond_local_file.contribution import ItemOverlap
from beyond_local_file.daemon.client import _print_response
from beyond_local_file.daemon.handlers import handle_request
from beyond_local_file.operations.link_check import CopyCheckDetails, GitExcludeStatus, LinkCheckResult
from beyond_local_file.operations.result import (
    CheckResult,
    CheckRow,
    CreateResult,
    FailedResult,
    ReloadResult,
    RemoveResult,
    RestoreResult,
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


def _restore_result(**fields: object) -> RestoreResult:
    """Return a RestoreResult with lab-app / alpha / example stand-ins."""
    values: dict[str, object] = {
        "exit_code": 0,
        "dry_run": False,
        "errors": (),
        "leftover_symlink": False,
        "source": "/tmp/alpha/example",
        "managed": "/tmp/lab-app/example",
        "replica_deletes": ("/tmp/example/example",),
        "git_excludes": (("example", "removed"),),
        "config_removed": "example",
        "persist_warning": None,
    }
    values.update(fields)
    return RestoreResult(**values)  # type: ignore[arg-type]


def _remove_result(**fields: object) -> RemoveResult:
    """Return a RemoveResult with lab-app / alpha / example stand-ins."""
    values: dict[str, object] = {
        "exit_code": 0,
        "dry_run": False,
        "errors": (),
        "artifacts": (
            ("/tmp/alpha/example", "copy", True),
            ("/tmp/example/example", "symlink", True),
        ),
        "excludes": (
            ("example", "/tmp/alpha/.git/info/exclude", True),
            ("example", "/tmp/example/.git/info/exclude", False),
        ),
        "managed_copy": "/tmp/lab-app/example",
        "config": "updated",
        "config_path": "/tmp/config.yml",
        "config_entry": "example",
        "persist_warning": None,
    }
    values.update(fields)
    return RemoveResult(**values)  # type: ignore[arg-type]


def test_restore_result_round_trips_through_ipc() -> None:
    """RestoreResult survives to_ipc then from_ipc, with tuples as lists on the wire."""
    result = _restore_result(git_excludes=(("example", "removed"), ("example", "not_found")))
    payload = to_ipc(result)
    assert payload["kind"] == "restore"
    assert payload["git_excludes"] == [["example", "removed"], ["example", "not_found"]]
    assert payload["replica_deletes"] == ["/tmp/example/example"]
    assert payload["errors"] == []
    assert from_ipc(payload) == result


def test_render_restore_leave_in_place_matches_today_order() -> None:
    """Leave-in-place restore prints target, hub delete, replicas, git, then config."""
    result = _restore_result()
    assert render(result) == (
        "Leaving target file in place: /tmp/alpha/example\n"
        "✓ Managed copy deleted: /tmp/lab-app/example\n"
        "Deleted replica copy: /tmp/example/example\n"
        "Removed 'example' from .git/info/exclude\n"
        "Removed 'example' from config subpath list\n"
    )
    assert payload_text(to_ipc(result)) == render(result)


def test_render_restore_leftover_symlink_matches_today_order() -> None:
    """Leftover-symlink restore prints unlink, copy-back, then the same deletes."""
    result = _restore_result(leftover_symlink=True)
    assert render(result) == (
        "Removing symlink at /tmp/alpha/example\n"
        "Copying /tmp/lab-app/example -> /tmp/alpha/example\n"
        "✓ Managed copy deleted: /tmp/lab-app/example\n"
        "Deleted replica copy: /tmp/example/example\n"
        "Removed 'example' from .git/info/exclude\n"
        "Removed 'example' from config subpath list\n"
    )


def test_render_restore_dry_run_prefixes_each_line() -> None:
    """Dry-run is data; render prefixes each restore echo with [dry-run]."""
    result = _restore_result(dry_run=True, leftover_symlink=True)
    assert render(result) == (
        "[dry-run] Removing symlink at /tmp/alpha/example\n"
        "[dry-run] Copying /tmp/lab-app/example -> /tmp/alpha/example\n"
        "[dry-run] ✓ Managed copy deleted: /tmp/lab-app/example\n"
        "[dry-run] Deleted replica copy: /tmp/example/example\n"
        "[dry-run] Removed 'example' from .git/info/exclude\n"
        "[dry-run] Removed 'example' from config subpath list\n"
    )


def test_render_restore_errors_and_permission_unlink() -> None:
    """Errors take Error: prefix; a started leftover unlink still prints Removing symlink."""
    missing = _restore_result(
        exit_code=1,
        errors=("Path does not exist: /tmp/alpha/example",),
        leftover_symlink=False,
        replica_deletes=(),
        git_excludes=(),
        config_removed=None,
    )
    assert render(missing) == "Error: Path does not exist: /tmp/alpha/example\n"
    denied = _restore_result(
        exit_code=1,
        leftover_symlink=True,
        errors=("Permission denied removing symlink at /tmp/alpha/example",),
        replica_deletes=(),
        git_excludes=(),
        config_removed=None,
    )
    assert render(denied) == (
        "Removing symlink at /tmp/alpha/example\nError: Permission denied removing symlink at /tmp/alpha/example\n"
    )
    dry_err = _restore_result(
        exit_code=1,
        dry_run=True,
        errors=("Managed copy does not exist at /tmp/lab-app/example",),
    )
    assert render(dry_err) == "[dry-run] Error: Managed copy does not exist at /tmp/lab-app/example\n"


def test_render_restore_persist_warning_is_last_and_keeps_exit_zero() -> None:
    """Persist failure is a field; the warning is last and exit_code stays 0."""
    result = _restore_result(persist_warning="disk full")
    assert result.exit_code == 0
    assert render(result).endswith("Warning: could not persist mapping snapshot: disk full\n")


def test_remove_result_round_trips_through_ipc() -> None:
    """RemoveResult survives to_ipc then from_ipc, with tuples as lists on the wire."""
    result = _remove_result(artifacts=(("/tmp/alpha/example", None, False),))
    payload = to_ipc(result)
    assert payload["kind"] == "remove"
    assert payload["artifacts"] == [["/tmp/alpha/example", None, False]]
    assert payload["excludes"] == [
        ["example", "/tmp/alpha/.git/info/exclude", True],
        ["example", "/tmp/example/.git/info/exclude", False],
    ]
    assert payload["config"] == "updated"
    assert from_ipc(payload) == result


def test_render_remove_success_story_matches_today_order() -> None:
    """Remove success prints artifacts, excludes, hub delete, then config update."""
    result = _remove_result()
    assert render(result) == (
        "Removed copy artifact: /tmp/alpha/example\n"
        "Removed symlink artifact: /tmp/example/example\n"
        "Removed Git exclude entry 'example' from /tmp/alpha/.git/info/exclude\n"
        "Skipping absent Git exclude entry 'example' in /tmp/example/.git/info/exclude\n"
        "Deleted managed copy: /tmp/lab-app/example\n"
        "Removed 'example' from selective-sync configuration: /tmp/config.yml\n"
    )
    assert payload_text(to_ipc(result)) == render(result)


def test_render_remove_dry_run_prefixes_each_line() -> None:
    """Dry-run is data; render prefixes each remove line with [dry-run]."""
    result = _remove_result(dry_run=True, artifacts=(("/tmp/alpha/example", None, False),), config="skipped")
    assert render(result) == (
        "[dry-run] Skipping absent artifact: /tmp/alpha/example\n"
        "[dry-run] Removed Git exclude entry 'example' from /tmp/alpha/.git/info/exclude\n"
        "[dry-run] Skipping absent Git exclude entry 'example' in /tmp/example/.git/info/exclude\n"
        "[dry-run] Deleted managed copy: /tmp/lab-app/example\n"
        "[dry-run] Skipping configuration update: no participating selective mapping\n"
    )


def test_render_remove_errors_and_config_repair() -> None:
    """Validation errors are Error: lines; repair prints the error then the manual line."""
    refused = _remove_result(
        exit_code=1,
        errors=("invocation path does not match managed copy: /tmp/alpha/example",),
        artifacts=(),
        excludes=(),
        config=None,
        config_path=None,
        config_entry=None,
    )
    assert render(refused) == "Error: invocation path does not match managed copy: /tmp/alpha/example\n"
    repair = _remove_result(
        exit_code=1,
        errors=("Could not update configuration /tmp/config.yml: disk failure",),
        config="repair",
    )
    assert render(repair) == (
        "Removed copy artifact: /tmp/alpha/example\n"
        "Removed symlink artifact: /tmp/example/example\n"
        "Removed Git exclude entry 'example' from /tmp/alpha/.git/info/exclude\n"
        "Skipping absent Git exclude entry 'example' in /tmp/example/.git/info/exclude\n"
        "Deleted managed copy: /tmp/lab-app/example\n"
        "Error: Could not update configuration /tmp/config.yml: disk failure\n"
        "Managed copy /tmp/lab-app/example was deleted; remove 'example' from configuration manually.\n"
    )


def test_render_remove_persist_warning_is_last_and_keeps_exit_zero() -> None:
    """Persist failure is a field; the warning is last and exit_code stays 0."""
    result = _remove_result(persist_warning="disk full")
    assert result.exit_code == 0
    assert render(result).endswith("Warning: could not persist mapping snapshot: disk full\n")


def _reload_result(**fields: object) -> ReloadResult:
    """Return a ReloadResult with lab-app / alpha / example stand-ins."""
    values: dict[str, object] = {
        "exit_code": 0,
        "affected": (),
        "problem": None,
        "overlaps": (),
        "missing_hubs": (),
    }
    values.update(fields)
    return ReloadResult(**values)  # type: ignore[arg-type]


def test_reload_result_round_trips_through_ipc() -> None:
    """ReloadResult survives to_ipc then from_ipc, with overlap paths as posix lists."""
    overlap = ItemOverlap(
        target=Path("/tmp/alpha"),
        project_a="lab-app",
        item_a="example",
        project_b="beta",
        item_b="example",
    )
    result = _reload_result(
        exit_code=1,
        problem="overlap",
        overlaps=(overlap,),
        missing_hubs=("/tmp/lab-app/notes.md",),
        affected=("lab-app",),
    )
    payload = to_ipc(result)
    assert payload["kind"] == "reload"
    assert payload["problem"] == "overlap"
    assert payload["affected"] == ["lab-app"]
    assert payload["overlaps"] == [["/tmp/alpha", "lab-app", "example", "beta", "example"]]
    assert payload["missing_hubs"] == ["/tmp/lab-app/notes.md"]
    assert from_ipc(payload) == result


def test_render_reload_success_is_empty() -> None:
    """A successful reload has no transcript; catch-up progress was streamed."""
    result = _reload_result(affected=("lab-app",))
    assert render(result) == ""
    assert payload_text(to_ipc(result)) == ""


def test_render_reload_problems_match_today_error_strings() -> None:
    """Each reload problem renders today's Error: line; overlap uses format_item_overlap."""
    missing = _reload_result(exit_code=1, problem="snapshot_missing")
    assert render(missing) == "Error: mapping snapshot is missing\n"
    overlap = _reload_result(
        exit_code=1,
        problem="overlap",
        overlaps=(
            ItemOverlap(
                target=Path("/tmp/alpha"),
                project_a="lab-app",
                item_a="example",
                project_b="beta",
                item_b="example",
            ),
        ),
    )
    assert render(overlap) == ("Error: overlapping items on /tmp/alpha: lab-app 'example' and beta 'example'\n")
    hubs = _reload_result(
        exit_code=1,
        problem="missing_hub",
        missing_hubs=("/tmp/lab-app/example", "/tmp/lab-app/notes.md"),
    )
    assert render(hubs) == (
        "Error: hub file does not exist: /tmp/lab-app/example\nError: hub file does not exist: /tmp/lab-app/notes.md\n"
    )
    unconfirmed = _reload_result(exit_code=1, problem="unconfirmed")
    assert render(unconfirmed) == "Error: mapping removals require interactive confirmation\n"
    assert payload_text(to_ipc(missing)) == render(missing)


def test_reload_without_snapshot_returns_reload_result(tmp_path: Path) -> None:
    """Reload with no mapping snapshot is a reload envelope, not a stdout blob."""
    hub = tmp_path / "lab-app"
    alpha = tmp_path / "alpha"
    hub.mkdir()
    alpha.mkdir()
    (hub / "example").write_text("canonical")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"lab-app: {alpha}\n")
    response = handle_request(config_path, {"op": "reload"})
    assert from_ipc(response) == ReloadResult(1, (), "snapshot_missing", (), ())
    assert render(from_ipc(response)) == "Error: mapping snapshot is missing\n"
    assert "stdout" not in response
