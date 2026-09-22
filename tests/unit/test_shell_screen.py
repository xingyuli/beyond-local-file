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

from beyond_local_file.held import REASON_DELETE_GAP, store_held_copy
from tests.daemon_support import daemon_running, start_daemon, stop_daemon

_WAIT_S = 15.0
_ALT_ON = "\x1b[?1049h"
_ALT_OFF = "\x1b[?1049l"
_HINT_RUNNING = "Ctrl+C: stop"
_HINT_STOP = "Enter: answer  Ctrl+C: confirm stop  Esc: continue"
_HINT_DONE = "q: close  Ctrl+C: close"
_HINT_ASK = "Enter: answer  Ctrl+C: cancel"
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


def _two_projects(tmp_path: Path) -> tuple[Path, Path, Path]:
    alpha = tmp_path / "alpha"
    beta = tmp_path / "beta"
    target_a = tmp_path / "target-a"
    target_b = tmp_path / "target-b"
    for path in (alpha, beta, target_a, target_b):
        path.mkdir()
    (alpha / "a.txt").write_text("aaa")
    (beta / "b.txt").write_text("bbb")
    config_path = tmp_path / "config.yml"
    config_path.write_text(f"alpha: {target_a}\nbeta: {target_b}\n")
    return config_path, target_a, target_b


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _run_plain(
    args: list[str],
    env: dict[str, str],
    *,
    cwd: Path | None = None,
) -> tuple[int, str, str]:
    proc = subprocess.Popen(
        [sys.executable, "-m", "beyond_local_file", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        cwd=str(cwd) if cwd is not None else None,
        env=_full_env(env),
        text=True,
    )
    stdout, stderr = proc.communicate(timeout=_WAIT_S)
    return proc.returncode or 0, stdout, stderr


def _unit_rows(frame: str, count: int) -> list[str]:
    placed = _placed(frame)
    return [placed.get(index, "") for index in range(2, 2 + count)]


def _rows_show(names: list[str], *, header: str, hint: str = _HINT_DONE) -> FrameCheck:
    def predicate(_text: str, frame: str) -> bool:
        if _placed(frame).get(1, "") != header or _hint(frame) != hint:
            return False
        rows = _unit_rows(frame, len(names))
        return all(
            name in row and re.search(r" (waiting|working|done|failed) ", f" {row} ") and re.search(r"\d+\.\ds", row)
            for name, row in zip(names, rows, strict=True)
        )

    return predicate


def _no_screen(text: str) -> bool:
    return _ALT_ON not in text and _HINT_DONE not in text and _HINT_RUNNING not in text


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_tty_link_check_shows_one_row_per_worker_unit_then_prints_the_table(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A TTY check keeps one row per worker unit, then prints the same table as a pipe."""
    config_path, _target_a, _target_b = _two_projects(tmp_path)
    with daemon_running(config_path, isolated_home):
        code, plain, plain_err = _run_plain(["--config", str(config_path), "link", "check"], isolated_home)
        assert code == 0, plain + plain_err
        assert _no_screen(plain + plain_err)
        with _pty_cli(
            ["--config", str(config_path), "link", "check"],
            isolated_home,
            tmp_path,
        ) as (proc, master, chunks):
            text = _wait(master, chunks, proc, _rows_show(["alpha", "beta"], header="link check  all projects"))
            assert proc.poll() is None
            assert _ALT_ON in text
            assert "Ctrl+C: stop" in text or _HINT_DONE in text
            frame = _last_frame(text)
            assert "a.txt" in frame or "b.txt" in frame
            joined = "\n".join(_unit_rows(frame, 2))
            assert "alpha" in joined and "beta" in joined
            code, text = _close_and_read(master, chunks, proc, b"q")
        assert code == 0
        assert _normalize(_after_exit(text)) == _normalize(plain)


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_tty_link_check_of_one_project_shows_that_row(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A named check uses one row and the header names that project."""
    config_path, _target_a, _target_b = _two_projects(tmp_path)
    with daemon_running(config_path, isolated_home):
        code, plain, plain_err = _run_plain(
            ["--config", str(config_path), "link", "check", "alpha"],
            isolated_home,
        )
        assert code == 0, plain + plain_err
        with _pty_cli(
            ["--config", str(config_path), "link", "check", "alpha"],
            isolated_home,
            tmp_path,
        ) as (proc, master, chunks):
            text = _wait(master, chunks, proc, _rows_show(["alpha"], header="link check  alpha"))
            frame = _last_frame(text)
            assert not re.search(r"beta  (waiting|working|done|failed)", frame)
            assert proc.poll() is None
            code, text = _close_and_read(master, chunks, proc, b"q")
        assert code == 0
        assert _normalize(_after_exit(text)) == _normalize(plain)
        assert "beta" not in plain


def _wait_exit(master: int, chunks: list[bytes], proc: subprocess.Popen[bytes]) -> tuple[int, str]:
    deadline = time.monotonic() + _WAIT_S
    while time.monotonic() < deadline:
        _drain(master, chunks)
        code = proc.poll()
        if code is not None:
            time.sleep(0.1)
            return code, _drain(master, chunks)
        time.sleep(0.05)
    raise AssertionError(_drain(master, chunks)[-2000:])


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_tty_daemon_start_shows_one_row_per_worker_unit(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A TTY start shows one catch-up row per project and stays up at ready."""
    config_path, _target_a, _target_b = _two_projects(tmp_path)
    hold = tmp_path / "catchup.hold"
    hold.write_text("1", encoding="utf-8")
    env = {**isolated_home, "BLF_TEST_CATCHUP_HOLD": str(hold)}
    try:
        with _pty_cli(["--config", str(config_path), "daemon", "start"], env, tmp_path) as (proc, master, chunks):
            text = _wait(
                master,
                chunks,
                proc,
                _rows_show(["alpha", "beta"], header="daemon start  all projects", hint=_HINT_RUNNING),
            )
            assert proc.poll() is None
            assert _ALT_ON in text
            assert "a.txt" in text or "b.txt" in text
            hold.unlink()
            _wait(
                master,
                chunks,
                proc,
                lambda _text, frame: "Daemon started (pid " in frame and _hint(frame) == _HINT_DONE,
            )
            assert proc.poll() is None
            code, text = _close_and_read(master, chunks, proc, b"q")
        assert code == 0
        assert "Daemon started (pid " in _after_exit(text)
    finally:
        hold.unlink(missing_ok=True)
        stop_daemon(config_path, isolated_home)


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_tty_reload_shows_one_row_per_affected_unit(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A reload that reaches the daemon shows the affected unit, then its result."""
    plain_root = tmp_path / "plain"
    tty_root = tmp_path / "tty"
    plain_root.mkdir()
    tty_root.mkdir()
    plain_config, plain_target, plain_other = _two_projects(plain_root)
    tty_config, tty_target, tty_other = _two_projects(tty_root)
    plain_extra = plain_root / "target-a2"
    tty_extra = tty_root / "target-a2"
    plain_extra.mkdir()
    tty_extra.mkdir()
    try:
        start_daemon(plain_config, isolated_home)
        plain_config.write_text(f"alpha:\n  - {plain_target}\n  - {plain_extra}\nbeta: {plain_other}\n")
        code, plain, plain_err = _run_plain(["--config", str(plain_config), "daemon", "reload"], isolated_home)
        assert code == 0, plain + plain_err
        assert _no_screen(plain + plain_err)
        assert (plain_extra / "a.txt").is_file()

        start_daemon(tty_config, isolated_home)
        tty_config.write_text(f"alpha:\n  - {tty_target}\n  - {tty_extra}\nbeta: {tty_other}\n")
        with _pty_cli(["--config", str(tty_config), "daemon", "reload"], isolated_home, tty_root) as (
            proc,
            master,
            chunks,
        ):
            text = _wait(master, chunks, proc, _rows_show(["alpha"], header="daemon reload  alpha"))
            frame = _last_frame(text)
            assert not re.search(r"beta  (waiting|working|done|failed)", frame)
            assert proc.poll() is None
            assert _ALT_ON in text
            code, text = _close_and_read(master, chunks, proc, b"q")
        assert code == 0
        assert _normalize(_after_exit(text)) == _normalize(plain)
        assert (tty_extra / "a.txt").is_file()
    finally:
        stop_daemon(plain_config, isolated_home)
        stop_daemon(tty_config, isolated_home)


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_reload_that_does_not_send_a_request_stays_plain(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Match and daemon down print a sentence and do not open a screen."""
    config_path, _target_a, _target_b = _two_projects(tmp_path)
    with _pty_cli(["--config", str(config_path), "daemon", "reload"], isolated_home, tmp_path) as (
        proc,
        master,
        chunks,
    ):
        code, text = _wait_exit(master, chunks, proc)
    assert code == 1
    assert "daemon is not running" in text
    assert _no_screen(text)

    with daemon_running(config_path, isolated_home):
        with _pty_cli(["--config", str(config_path), "daemon", "reload"], isolated_home, tmp_path) as (
            proc,
            master,
            chunks,
        ):
            code, text = _wait_exit(master, chunks, proc)
        assert code == 0
        assert "Mappings already match the snapshot" in text
        assert _no_screen(text)


def test_non_tty_check_start_and_reload_print_the_result_only(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A shell with no terminal prints the result and does not wait for a key."""
    config_path, target_a, _target_b = _two_projects(tmp_path)
    code, stdout, stderr = _run_plain(["--config", str(config_path), "daemon", "start"], isolated_home)
    assert code == 0, stdout + stderr
    assert "Daemon started" in stdout
    assert _no_screen(stdout + stderr)
    try:
        code, stdout, stderr = _run_plain(["--config", str(config_path), "link", "check"], isolated_home)
        assert code == 0, stdout + stderr
        assert "alpha" in stdout and "beta" in stdout
        assert _no_screen(stdout + stderr)
        assert "Checking " not in stdout + stderr

        code, stdout, stderr = _run_plain(["--config", str(config_path), "daemon", "reload"], isolated_home)
        assert code == 0, stdout + stderr
        assert "Mappings already match the snapshot" in stdout
        assert _no_screen(stdout + stderr)

        extra = tmp_path / "target-a2"
        extra.mkdir()
        config_path.write_text(f"alpha:\n  - {target_a}\n  - {extra}\nbeta: {tmp_path / 'target-b'}\n")
        code, stdout, stderr = _run_plain(["--config", str(config_path), "daemon", "reload"], isolated_home)
        assert code == 0, stdout + stderr
        assert _no_screen(stdout + stderr)
        assert (extra / "a.txt").is_file()
    finally:
        stop_daemon(config_path, isolated_home)


def _two_hubs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    hub_a = tmp_path / "shared-hooks"
    hub_b = tmp_path / "shared-settings"
    target = tmp_path / "target"
    for path in (hub_a, hub_b, target):
        path.mkdir()
    (hub_a / "a-only.txt").write_text("from-a")
    (hub_b / "b-only.txt").write_text("from-b")
    (target / "a-only.txt").write_text("from-a")
    (target / "b-only.txt").write_text("from-b")
    (target / ".env").write_text("secret=1\n")
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "shared-hooks:\n"
        f"  target: {target}\n"
        "  subpath:\n"
        "    - a-only.txt\n"
        "shared-settings:\n"
        f"  target: {target}\n"
        "  subpath:\n"
        "    - b-only.txt\n"
    )
    return config_path, hub_a, hub_b, target


def _hub_create_finished(_text: str, frame: str) -> bool:
    placed = _placed(frame)
    row = placed.get(2, "")
    return (
        placed.get(1, "") == "revlink create  .env"
        and "shared-hooks" in row
        and " done " in f" {row} "
        and "Writing baseline" in row
        and _hint(frame) == _HINT_DONE
        and "Computing checksum" in _text
        and not _above_hint(frame).startswith("> ")
    )


def _hub_choice_open(_text: str, frame: str) -> bool:
    return (
        _placed(frame).get(1, "") == "revlink create  .env"
        and "More than one managed project contributes to this directory:" in frame
        and "  1. shared-hooks" in frame
        and "  2. shared-settings" in frame
        and "Choose a managed project" in frame
        and _hint(frame) == _HINT_ASK
        and _above_hint(frame).startswith("> ")
    )


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_tty_create_asks_hub_choice_on_the_shell_screen(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A TTY create asks for a hub number on the screen before the request is sent."""
    config_path, hub_a, hub_b, target = _two_hubs(tmp_path)
    with daemon_running(config_path, isolated_home):
        with _pty_cli(
            ["--config", str(config_path), "revlink", "create", ".env"],
            isolated_home,
            target,
        ) as (proc, master, chunks):
            text = _wait(master, chunks, proc, _hub_choice_open)
            assert proc.poll() is None
            assert _ALT_ON in text
            assert not (hub_a / ".env").exists()
            os.write(master, b"1\r")
            _wait(master, chunks, proc, _hub_create_finished)
            assert proc.poll() is None
            code, text = _close_and_read(master, chunks, proc, b"q")
        assert code == 0
        assert "Computing checksum" in _after_exit(text)
        assert (hub_a / ".env").read_text() == "secret=1\n"
        assert not (hub_b / ".env").exists()


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_tty_create_cancel_before_request_sends_nothing(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Ctrl+C on the hub choice closes the screen and does not create."""
    config_path, hub_a, hub_b, target = _two_hubs(tmp_path)
    with daemon_running(config_path, isolated_home):
        with _pty_cli(
            ["--config", str(config_path), "revlink", "create", ".env"],
            isolated_home,
            target,
        ) as (proc, master, chunks):
            _wait(master, chunks, proc, _hub_choice_open)
            assert proc.poll() is None
            os.write(master, b"\x03")
            code, text = _wait_exit(master, chunks, proc)
        assert code == 1
        assert "Computing checksum" not in text
        assert not (hub_a / ".env").exists()
        assert not (hub_b / ".env").exists()


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_tty_create_other_hub_answer_keeps_the_question_open(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A submission other than a listed number prints one line and leaves the question open."""
    config_path, hub_a, hub_b, target = _two_hubs(tmp_path)
    with daemon_running(config_path, isolated_home):
        with _pty_cli(
            ["--config", str(config_path), "revlink", "create", ".env"],
            isolated_home,
            target,
        ) as (proc, master, chunks):
            _wait(master, chunks, proc, _hub_choice_open)
            os.write(master, b"0\r")
            text = _wait(master, chunks, proc, _hub_invalid_shown)
            assert "Choose a number." in _last_frame(text)
            assert not (hub_a / ".env").exists()
            os.write(master, b"1\r")
            _wait(master, chunks, proc, _hub_create_finished)
            code, text = _close_and_read(master, chunks, proc, b"q")
        assert code == 0
        assert (hub_a / ".env").read_text() == "secret=1\n"
        assert not (hub_b / ".env").exists()


def _hub_invalid_shown(_text: str, frame: str) -> bool:
    return _hub_choice_open(_text, frame) and "Choose a number." in frame


def _removal_confirm_open(_text: str, frame: str) -> bool:
    return (
        "Mapping removals:" in frame
        and "project-remove: beta" in frame
        and "Apply these mapping removals?" in frame
        and _hint(frame) == _HINT_ASK
        and _above_hint(frame).startswith("> ")
    )


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_tty_reload_asks_removal_confirm_on_the_shell_screen(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A TTY reload asks mapping-removal confirm on the screen before the request is sent."""
    config_path, target_a, target_b = _two_projects(tmp_path)
    beta = tmp_path / "beta"
    with daemon_running(config_path, isolated_home):
        config_path.write_text(f"alpha: {target_a}\n")
        with _pty_cli(
            ["--config", str(config_path), "daemon", "reload"],
            isolated_home,
            tmp_path,
        ) as (proc, master, chunks):
            text = _wait(master, chunks, proc, _removal_confirm_open)
            assert proc.poll() is None
            assert _ALT_ON in text
            assert (target_b / "b.txt").is_file()
            os.write(master, b"y\r")
            _wait(
                master,
                chunks,
                proc,
                lambda _text, frame: _hint(frame) == _HINT_DONE and "project-remove: beta" in frame,
            )
            assert proc.poll() is None
            code, text = _close_and_read(master, chunks, proc, b"q")
        assert code == 0
        assert not (target_b / "b.txt").exists()
        assert (beta / "b.txt").read_text() == "bbb"


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_tty_reload_declined_removal_does_not_send(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """Answering n on the removal confirm closes without applying mapping changes."""
    config_path, target_a, target_b = _two_projects(tmp_path)
    with daemon_running(config_path, isolated_home):
        config_path.write_text(f"alpha: {target_a}\n")
        with _pty_cli(
            ["--config", str(config_path), "daemon", "reload"],
            isolated_home,
            tmp_path,
        ) as (proc, master, chunks):
            _wait(master, chunks, proc, _removal_confirm_open)
            os.write(master, b"n\r")
            _wait(
                master,
                chunks,
                proc,
                lambda _text, frame: _hint(frame) == _HINT_DONE
                and "Mapping changes were not applied" in frame,
            )
            assert proc.poll() is None
            code, text = _close_and_read(master, chunks, proc, b"q")
        assert code == 1
        assert "Mapping changes were not applied" in _after_exit(text)
        assert (target_b / "b.txt").is_file()


def _isolation_ack_open(_text: str, frame: str) -> bool:
    return (
        "WARNING:" in frame
        and "Continue without resolving held copies and out-of-sync paths?" in frame
        and _hint(frame) == _HINT_ASK
        and _above_hint(frame).startswith("> ")
    )


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_tty_reload_asks_isolation_ack_on_the_shell_screen(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A TTY reload asks the held-copy ack on the screen before it would send a request."""
    config_path, target_a, _target_b = _two_projects(tmp_path)
    sidecar = tmp_path / "hub-bytes.txt"
    sidecar.write_text("kept-hub-bytes")
    with daemon_running(config_path, isolated_home):
        store_held_copy(
            tmp_path / "alpha",
            rel_path=Path("a.txt"),
            source=sidecar,
            replica=target_a,
            reason=REASON_DELETE_GAP,
        )
        with _pty_cli(
            ["--config", str(config_path), "daemon", "reload"],
            isolated_home,
            tmp_path,
        ) as (proc, master, chunks):
            text = _wait(master, chunks, proc, _isolation_ack_open)
            assert proc.poll() is None
            assert _ALT_ON in text
            os.write(master, b"y\r")
            _wait(
                master,
                chunks,
                proc,
                lambda _text, frame: _hint(frame) == _HINT_DONE
                and "Mappings already match the snapshot" in frame,
            )
            code, text = _close_and_read(master, chunks, proc, b"q")
        assert code == 0
        assert "Mappings already match the snapshot" in _after_exit(text)


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_tty_start_asks_isolation_ack_on_the_shell_screen(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A TTY start asks the held-copy ack on the screen before the daemon is spawned."""
    config_path, target_a, _target_b = _two_projects(tmp_path)
    sidecar = tmp_path / "hub-bytes.txt"
    sidecar.write_text("kept-hub-bytes")
    store_held_copy(
        tmp_path / "alpha",
        rel_path=Path("a.txt"),
        source=sidecar,
        replica=target_a,
        reason=REASON_DELETE_GAP,
    )
    try:
        with _pty_cli(
            ["--config", str(config_path), "daemon", "start"],
            isolated_home,
            tmp_path,
        ) as (proc, master, chunks):
            text = _wait(master, chunks, proc, _isolation_ack_open)
            assert proc.poll() is None
            assert _placed(_last_frame(text)).get(1, "") == "daemon start  all projects"
            assert _ALT_ON in text
            os.write(master, b"y\r")
            _wait(
                master,
                chunks,
                proc,
                lambda _text, frame: "Daemon started (pid " in frame and _hint(frame) == _HINT_DONE,
            )
            code, text = _close_and_read(master, chunks, proc, b"q")
        assert code == 0
        assert "Daemon started (pid " in _after_exit(text)
    finally:
        stop_daemon(config_path, isolated_home)


@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_tty_start_asks_removal_confirm_on_the_shell_screen(
    tmp_path: Path,
    isolated_home: dict[str, str],
) -> None:
    """A TTY start asks mapping-removal confirm on the screen before the daemon is spawned."""
    config_path, target_a, target_b = _two_projects(tmp_path)
    beta = tmp_path / "beta"
    start_daemon(config_path, isolated_home)
    stop_daemon(config_path, isolated_home)
    config_path.write_text(f"alpha: {target_a}\n")
    try:
        with _pty_cli(
            ["--config", str(config_path), "daemon", "start"],
            isolated_home,
            tmp_path,
        ) as (proc, master, chunks):
            text = _wait(master, chunks, proc, _removal_confirm_open)
            assert proc.poll() is None
            assert _placed(_last_frame(text)).get(1, "") == "daemon start  all projects"
            assert (target_b / "b.txt").is_file()
            os.write(master, b"y\r")
            _wait(
                master,
                chunks,
                proc,
                lambda _text, frame: "Daemon started (pid " in frame and _hint(frame) == _HINT_DONE,
            )
            code, text = _close_and_read(master, chunks, proc, b"q")
        assert code == 0
        assert "Daemon started (pid " in _after_exit(text)
        assert not (target_b / "b.txt").exists()
        assert (beta / "b.txt").read_text() == "bbb"
    finally:
        stop_daemon(config_path, isolated_home)
