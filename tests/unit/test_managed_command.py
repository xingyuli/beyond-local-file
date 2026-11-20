"""``blf managed`` through the CLI and a real daemon."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from beyond_local_file.configuration_set import ConfigurationSet
from tests.daemon_support import daemon_running, invoke_cli

USAGE_ERROR = 2  # Click's exit status for a bad argument


def _workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    """One managed project ``proj-0`` with two items, projected into one target."""
    managed = tmp_path / "proj-0"
    target = tmp_path / "target-0"
    managed.mkdir()
    target.mkdir()
    (managed / "shared.txt").write_text("hub")
    (managed / "nested").mkdir()
    (managed / "nested" / "keep.txt").write_text("keep")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"proj-0: {target}\n")
    return config_path, managed, target


def test_target_root_prints_json_and_exits_zero(tmp_path: Path, isolated_home: dict[str, str]) -> None:
    """PATH naming a target root prints the answer as JSON on stdout."""
    config_path, managed, target = _workspace(tmp_path)

    with daemon_running(config_path, isolated_home):
        result = invoke_cli(["--config", str(config_path), "managed", str(target)], env=isolated_home)

    assert result.exit_code == 0, result.output
    answer = json.loads(result.stdout)
    assert answer["managed"] is True
    assert answer["target"] == str(target)
    assert answer["is_target_root"] is True
    project = answer["managed_projects"][0]
    assert project["name"] == "proj-0"
    assert project["path"] == str(managed)
    assert [item["path"] for item in project["items"]] == ["nested", "shared.txt"]


def test_default_path_is_the_current_directory(
    tmp_path: Path, isolated_home: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no PATH, a subdirectory of a target reports the target and is_target_root false."""
    config_path, _managed, target = _workspace(tmp_path)
    (target / "src").mkdir()
    monkeypatch.chdir(target / "src")

    with daemon_running(config_path, isolated_home):
        result = invoke_cli(["--config", str(config_path), "managed"], env=isolated_home)

    assert result.exit_code == 0, result.output
    answer = json.loads(result.stdout)
    assert answer["path"] == str(target / "src")
    assert answer["target"] == str(target)
    assert answer["is_target_root"] is False


def test_relative_path_is_joined_to_the_current_directory(
    tmp_path: Path, isolated_home: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative PATH is resolved against CWD, so blf can be asked about another directory."""
    config_path, _managed, target = _workspace(tmp_path)
    monkeypatch.chdir(tmp_path)

    with daemon_running(config_path, isolated_home):
        result = invoke_cli(["--config", str(config_path), "managed", "target-0/../target-0"], env=isolated_home)

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["path"] == str(target)


def test_directory_in_no_target_exits_zero_with_managed_false(tmp_path: Path, isolated_home: dict[str, str]) -> None:
    """'Not managed' is an answer, not a failure."""
    config_path, _managed, _target = _workspace(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    with daemon_running(config_path, isolated_home):
        result = invoke_cli(["--config", str(config_path), "managed", str(elsewhere)], env=isolated_home)

    assert result.exit_code == 0, result.output
    answer = json.loads(result.stdout)
    assert answer["managed"] is False
    assert answer["managed_projects"] == []


def test_daemon_down_exits_one_with_empty_stdout(tmp_path: Path, isolated_home: dict[str, str]) -> None:
    """When the daemon cannot answer, stdout stays empty and stderr carries the message."""
    config_path, _managed, target = _workspace(tmp_path)

    result = invoke_cli(["--config", str(config_path), "managed", str(target)], env=isolated_home)

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "daemon is not running" in result.stderr


def test_missing_config_exits_one_with_empty_stdout(tmp_path: Path, isolated_home: dict[str, str]) -> None:
    """A configuration set that cannot be resolved is also a failure to answer."""
    result = invoke_cli(["--config", str(tmp_path / "nope.yml"), "managed", str(tmp_path)], env=isolated_home)

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr


@pytest.mark.parametrize("kind", ["file", "missing"])
def test_path_that_is_not_a_directory_is_a_usage_error(
    tmp_path: Path, isolated_home: dict[str, str], kind: str
) -> None:
    """A file or a missing path is rejected with exit 2 before the daemon is contacted."""
    config_path, _managed, _target = _workspace(tmp_path)
    bad = tmp_path / "a-file.txt"
    if kind == "file":
        bad.write_text("x")

    result = invoke_cli(["--config", str(config_path), "managed", str(bad)], env=isolated_home)

    assert result.exit_code == USAGE_ERROR
    assert result.stdout == ""
    assert result.stderr


def test_terminal_still_gets_plain_json(
    tmp_path: Path, isolated_home: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even when the shell would draw a screen, managed prints only the JSON document."""
    config_path, _managed, target = _workspace(tmp_path)

    with daemon_running(config_path, isolated_home):
        monkeypatch.setattr("beyond_local_file.daemon.client.shell_wants_screen", lambda: True)
        monkeypatch.setattr("beyond_local_file.cli.shell_wants_screen", lambda: True)
        result = invoke_cli(["--config", str(config_path), "managed", str(target)], env=isolated_home)

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["managed"] is True


def test_schema_flag_prints_the_schema_without_a_daemon(tmp_path: Path, isolated_home: dict[str, str]) -> None:
    """--schema needs no daemon and no configuration set."""
    result = invoke_cli(["--config", str(tmp_path / "nope.yml"), "managed", "--schema"], env=isolated_home)

    assert result.exit_code == 0, result.output
    schema = json.loads(result.stdout)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["description"]
    jsonschema.Draft202012Validator.check_schema(schema)


def test_command_output_validates_against_the_printed_schema(tmp_path: Path, isolated_home: dict[str, str]) -> None:
    """What the command prints is valid under what --schema prints, for managed and unmanaged directories."""
    config_path, _managed, target = _workspace(tmp_path)
    schema = json.loads(invoke_cli(["managed", "--schema"], env=isolated_home).stdout)
    validator = jsonschema.Draft202012Validator(schema)

    with daemon_running(config_path, isolated_home):
        for directory in (target, tmp_path):
            result = invoke_cli(["--config", str(config_path), "managed", str(directory)], env=isolated_home)
            validator.validate(json.loads(result.stdout))


def test_help_lists_managed_under_run_anywhere_and_names_the_schema_flag(isolated_home: dict[str, str]) -> None:
    """Root help places managed with the run-anywhere commands, and its own help names --schema."""
    root_help = invoke_cli(["--help"], env=isolated_home).stdout
    anywhere = root_help.split("Run anywhere")[1].split("Run inside a target project")[0]
    assert "managed" in anywhere

    assert "--schema" in invoke_cli(["managed", "--help"], env=isolated_home).stdout


def test_schema_with_a_path_is_a_usage_error(tmp_path: Path, isolated_home: dict[str, str]) -> None:
    """--schema describes the output format, so a PATH next to it has no meaning."""
    result = invoke_cli(["managed", "--schema", str(tmp_path)], env=isolated_home)

    assert result.exit_code == USAGE_ERROR
    assert result.stdout == ""
    assert "--schema" in result.stderr


def test_a_symlink_to_a_target_is_not_followed(tmp_path: Path, isolated_home: dict[str, str]) -> None:
    """The path is normalized, not resolved: a symlinked route to a target is not that target."""
    config_path, _managed, target = _workspace(tmp_path)
    link = tmp_path / "link-to-target"
    link.symlink_to(target, target_is_directory=True)

    with daemon_running(config_path, isolated_home):
        result = invoke_cli(["--config", str(config_path), "managed", str(link)], env=isolated_home)

    assert result.exit_code == 0, result.output
    answer = json.loads(result.stdout)
    assert answer["path"] == str(link)
    assert answer["managed"] is False


def test_answers_from_the_daemon_not_from_the_mapping_files(tmp_path: Path, isolated_home: dict[str, str]) -> None:
    """With the snapshot file gone and the yaml rewritten, the daemon still answers from what it holds."""
    config_path, _managed, target = _workspace(tmp_path)

    with daemon_running(config_path, isolated_home):
        config_path.write_text(f"proj-0: {tmp_path / 'somewhere-else'}\n")
        for snapshot in (ConfigurationSet(config_path).run_directory).glob("mapping-snapshot.yml"):
            snapshot.unlink()
        result = invoke_cli(["--config", str(config_path), "managed", str(target)], env=isolated_home)

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["managed"] is True
