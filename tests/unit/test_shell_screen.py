"""Shell screen for revlink create, revlink restore, and remove."""

from __future__ import annotations

import fcntl
import os
import pty
import re
import select
import struct
import subprocess
import sys
import termios
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.daemon_support import daemon_running, start_daemon, stop_daemon

_WAIT_S = 15.0
_ALT_ON = "\x1b[?1049h"
_ALT_OFF = "\x1b[?1049l"
_HINT_RUNNING = "Ctrl+C: stop"
_HINT_STOP = "Enter: answer  Ctrl+C: confirm stop  Esc: continue"
_HINT_DONE = "q: close  Ctrl+C: close"
_STOP_QUESTION = "Stop this command?"
_ANSWER_LINE = "Answer y or n."
_ROW_MARK = re.compile(r"\x1b\[(\d+);1H\x1b\[2K")

type FrameCheck = Callable[[str, str], bool]


def _workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    managed = tmp_path / "alpha"
    target = tmp_path / "lab-app"
    managed.mkdir()
    target.mkdir()
    (managed / "shared.txt").write_text("hello")
    (target / "item.txt").write_text("adopt me")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"alpha: {target}\n")
    return config_path, managed, target


def _full_env(env: dict[str, str]) -> dict[str, str]:
    return {**os.environ, **env}


def _set_winsize(fd: int) -> None:
    winsize = struct.pack("HHHH", 24, 80, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


def _drain(master: int, chunks: list[bytes]) -> str:
    while True:
        ready, _, _ = select.select([master], [], [], 0)
        if not ready:
            break
        try:
            data = os.read(master, 8192)
        except OSError:
            break
        if not data:
            break
        chunks.append(data)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _placed(frame: str) -> dict[int, str]:
    matches = list(_ROW_MARK.finditer(frame))
    placed: dict[int, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(frame)
        placed[int(match.group(1))] = frame[start:end]
    return placed


def _last_frame(text: str) -> str:
    screen = text.split(_ALT_OFF, 1)[0]
    return screen.split("\x1b[2J")[-1]


def _hint(frame: str) -> str:
    placed = _placed(frame)
    if not placed:
        return ""
    return placed[max(placed)]


def _above_hint(frame: str) -> str:
    placed = _placed(frame)
    if not placed:
        return ""
    return placed.get(max(placed) - 1, "")


def _wait(master: int, chunks: list[bytes], proc: subprocess.Popen[bytes], predicate: FrameCheck) -> str:
    deadline = time.monotonic() + _WAIT_S
    text = ""
    while time.monotonic() < deadline:
        text = _drain(master, chunks)
        if predicate(text, _last_frame(text)):
            return text
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    text = _drain(master, chunks)
    raise AssertionError(text[-4000:])


def _after_exit(text: str) -> str:
    if _ALT_OFF not in text:
        return ""
    return text.rsplit(_ALT_OFF, 1)[1]


@contextmanager
def _pty_cli(
    args: list[str],
    env: dict[str, str],
    cwd: Path,
) -> Iterator[tuple[subprocess.Popen[bytes], int, list[bytes]]]:
    master, slave = pty.openpty()
    _set_winsize(slave)
    proc: subprocess.Popen[bytes] | None = None
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "beyond_local_file", *args],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=str(cwd),
            env=_full_env(env),
            close_fds=True,
        )
        os.close(slave)
        slave = -1
        yield proc, master, []
    finally:
        if slave != -1:
            os.close(slave)
        os.close(master)
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def _close_and_read(master: int, chunks: list[bytes], proc: subprocess.Popen[bytes], key: bytes) -> tuple[int, str]:
    os.write(master, key)
    deadline = time.monotonic() + _WAIT_S
    while time.monotonic() < deadline:
        _drain(master, chunks)
        code = proc.poll()
        if code is not None:
            time.sleep(0.1)
            return code, _drain(master, chunks)
        time.sleep(0.05)
    raise AssertionError(_drain(master, chunks)[-2000:])


def _finished(header: str, transcript: str) -> FrameCheck:
    def predicate(text: str, frame: str) -> bool:
        placed = _placed(frame)
        row = placed.get(2, "")
        return (
            placed.get(1, "") == header
            and "alpha" in row
            and " done " in f" {row} "
            and "Writing baseline" in row
            and re.search(r"\d+\.\ds", row) is not None
            and _hint(frame) == _HINT_DONE
            and transcript in text
            and not _above_hint(frame).startswith("> ")
        )

    return predicate


def _hold_until_entered(hold: Path) -> None:
    entered = Path(str(hold) + ".entered")
    deadline = time.monotonic() + _WAIT_S
    while time.monotonic() < deadline and not entered.exists():
        time.sleep(0.05)
    assert entered.exists(), "idle observe never entered the test hold"


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
@pytest.mark.parametrize(
    ("args", "header", "transcript"),
    [
        (["revlink", "create", "item.txt"], "revlink create  item.txt", "Computing checksum"),
        (["revlink", "restore", "shared.txt"], "revlink restore  shared.txt", "Leaving target file in place"),
        (["remove", "shared.txt"], "remove  shared.txt", "Deleted managed copy"),
    ],
)
def test_tty_command_shows_shell_screen_then_prints_transcript(
    tmp_path: Path,
    isolated_home: dict[str, str],
    args: list[str],
    header: str,
    transcript: str,
) -> None:
    """A TTY create, restore, or remove keeps the screen up, then prints the transcript."""
    config_path, _managed, target = _workspace(tmp_path)
    with (
        daemon_running(config_path, isolated_home),
        _pty_cli(
            ["--config", str(config_path), *args],
            isolated_home,
            target,
        ) as (proc, master, chunks),
    ):
        text = _wait(master, chunks, proc, _finished(header, transcript))
        assert proc.poll() is None
        assert _ALT_ON in text
        code, text = _close_and_read(master, chunks, proc, b"q")
    assert code == 0
    assert transcript in text.split(_ALT_OFF, 1)[0]
    assert transcript in _after_exit(text)
    assert _STOP_QUESTION not in text


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_q_is_not_required_when_ctrl_c_closes_finished_screen(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """After the work finishes, Ctrl+C closes with no stop question."""
    config_path, managed, target = _workspace(tmp_path)
    with (
        daemon_running(config_path, isolated_home),
        _pty_cli(
            ["--config", str(config_path), "revlink", "create", "item.txt"],
            isolated_home,
            target,
        ) as (proc, master, chunks),
    ):
        _wait(master, chunks, proc, _finished("revlink create  item.txt", "Computing checksum"))
        assert proc.poll() is None
        code, text = _close_and_read(master, chunks, proc, b"\x03")
    assert code == 0
    assert _STOP_QUESTION not in text
    assert "Computing checksum" in _after_exit(text)
    assert (managed / "item.txt").read_text() == "adopt me"


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
@pytest.mark.parametrize("confirm", [b"y\r", b"\x03"])
def test_confirming_stop_cancels_the_running_command(
    tmp_path: Path,
    isolated_home: dict[str, str],
    confirm: bytes,
) -> None:
    """Ctrl+C asks to stop; y or a second Ctrl+C cancels before the op runs."""
    config_path, managed, target = _workspace(tmp_path)
    hold = tmp_path / "idle-hold"
    hold.write_text("1")
    env = {**isolated_home, "BLF_TEST_IDLE_HOLD": str(hold)}
    start_daemon(config_path, env)
    try:
        _hold_until_entered(hold)
        with _pty_cli(
            ["--config", str(config_path), "revlink", "create", "item.txt"],
            isolated_home,
            target,
        ) as (proc, master, chunks):
            _wait(master, chunks, proc, _row_is("waiting"))

            os.write(master, b"\x03")
            _wait(master, chunks, proc, _stop_question_open)

            os.write(master, confirm)
            _wait(master, chunks, proc, _running_again)
            time.sleep(0.2)
            hold.unlink(missing_ok=True)
            text = _wait(master, chunks, proc, _failed_stopped)
            assert proc.poll() is None
            assert _STOP_QUESTION in text
            code, text = _close_and_read(master, chunks, proc, b"q")
        assert code == 1
        assert "Stopped" in _after_exit(text)
        assert not (managed / "item.txt").exists()
    finally:
        hold.unlink(missing_ok=True)
        stop_daemon(config_path, env)


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_esc_continues_a_running_command(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Esc dismisses the stop question and the command still finishes."""
    config_path, managed, target = _workspace(tmp_path)
    hold = tmp_path / "idle-hold"
    hold.write_text("1")
    env = {**isolated_home, "BLF_TEST_IDLE_HOLD": str(hold)}
    start_daemon(config_path, env)
    try:
        _hold_until_entered(hold)
        with _pty_cli(
            ["--config", str(config_path), "revlink", "create", "item.txt"],
            isolated_home,
            target,
        ) as (proc, master, chunks):
            _wait(master, chunks, proc, _row_is("waiting"))
            os.write(master, b"\x03")
            _wait(master, chunks, proc, _stop_question_open)
            os.write(master, b"\x1b")
            _wait(master, chunks, proc, _running_again)
            hold.unlink(missing_ok=True)
            _wait(master, chunks, proc, _finished("revlink create  item.txt", "Computing checksum"))
            code, text = _close_and_read(master, chunks, proc, b"q")
        assert code == 0
        assert "Computing checksum" in _after_exit(text)
        assert (managed / "item.txt").read_text() == "adopt me"
    finally:
        hold.unlink(missing_ok=True)
        stop_daemon(config_path, env)


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_other_answer_keeps_the_stop_question_open(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A submission other than y or n prints one line and leaves the question open."""
    config_path, managed, target = _workspace(tmp_path)
    hold = tmp_path / "idle-hold"
    hold.write_text("1")
    env = {**isolated_home, "BLF_TEST_IDLE_HOLD": str(hold)}
    start_daemon(config_path, env)
    try:
        _hold_until_entered(hold)
        with _pty_cli(
            ["--config", str(config_path), "revlink", "create", "item.txt"],
            isolated_home,
            target,
        ) as (proc, master, chunks):
            _wait(master, chunks, proc, _row_is("waiting"))
            os.write(master, b"\x03")
            _wait(master, chunks, proc, _stop_question_open)
            os.write(master, b"no\r")
            text = _wait(master, chunks, proc, _invalid_answer_shown)
            assert _ANSWER_LINE in _last_frame(text)
            os.write(master, b"n\r")
            _wait(master, chunks, proc, _running_again)
            hold.unlink(missing_ok=True)
            _wait(master, chunks, proc, _finished("revlink create  item.txt", "Computing checksum"))
            code, _text = _close_and_read(master, chunks, proc, b"q")
        assert code == 0
        assert (managed / "item.txt").read_text() == "adopt me"
    finally:
        hold.unlink(missing_ok=True)
        stop_daemon(config_path, env)


@pytest.mark.parametrize(
    ("args", "transcript"),
    [
        (["revlink", "create", "item.txt"], "Computing checksum"),
        (["revlink", "restore", "shared.txt"], "Leaving target file in place"),
        (["remove", "shared.txt"], "Deleted managed copy"),
    ],
)
def test_non_tty_prints_transcript_without_waiting(
    tmp_path: Path,
    isolated_home: dict[str, str],
    args: list[str],
    transcript: str,
) -> None:
    """A shell with no terminal prints the transcript and does not wait for a key."""
    config_path, _managed, target = _workspace(tmp_path)
    with daemon_running(config_path, isolated_home):
        proc = subprocess.Popen(
            [sys.executable, "-m", "beyond_local_file", "--config", str(config_path), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            cwd=str(target),
            env=_full_env(isolated_home),
            text=True,
        )
        stdout, stderr = proc.communicate(timeout=_WAIT_S)
    assert proc.returncode == 0
    assert transcript in stdout
    combined = stdout + stderr
    assert _HINT_DONE not in combined
    assert _HINT_RUNNING not in combined
    assert _ALT_ON not in combined
    assert "Waiting" not in stderr
    assert "Creating" not in stderr
    assert "Restoring" not in stderr
    assert "Removing" not in stderr


def _row_is(state: str) -> FrameCheck:
    def predicate(_text: str, frame: str) -> bool:
        row = _placed(frame).get(2, "")
        return "alpha" in row and f" {state} " in f" {row} " and _hint(frame) == _HINT_RUNNING

    return predicate


def _invalid_answer_shown(_text: str, frame: str) -> bool:
    return _stop_question_open(_text, frame) and _ANSWER_LINE in frame


def _stop_question_open(_text: str, frame: str) -> bool:
    return _hint(frame) == _HINT_STOP and _above_hint(frame).startswith("> ") and _STOP_QUESTION in frame


def _running_again(_text: str, frame: str) -> bool:
    return _hint(frame) == _HINT_RUNNING and not _above_hint(frame).startswith("> ")


def _failed_stopped(_text: str, frame: str) -> bool:
    placed = _placed(frame)
    row = placed.get(2, "")
    return " failed " in f" {row} " and "Stopped" in frame and _hint(frame) == _HINT_DONE
