"""Full-screen shell for a daemon request."""

from __future__ import annotations

import os
import select
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import click

from .ipc import Request, RequestSession

if os.name != "nt":
    import termios
    import tty

_HINT_ASK = "Enter: answer  Ctrl+C: cancel"
_HINT_RUNNING = "Ctrl+C: stop"
_HINT_STOP = "Enter: answer  Ctrl+C: confirm stop  Esc: continue"
_HINT_DONE = "q: close  Ctrl+C: close"
_STOP_QUESTION = "Stop this command?"
_ANSWER_LINE = "Answer y or n."
_ALT_ENTER = "\x1b[?1049h\x1b[?25l"
_ALT_LEAVE = "\x1b[?25h\x1b[?1049l"
_KEY_POLL_S = 0.05
_INPUT_LIMIT = 80
_MIN_COLUMNS = 20
_MIN_ROWS = 4
_FALLBACK_COLUMNS = 80
_FALLBACK_ROWS = 24
_KEY_READ_SIZE = 64
_CTRL_C = 3
_ESC = 27
_CR = 13
_LF = 10
_BS = 8
_DEL = 127
_PRINTABLE_MIN = 32
_PRINTABLE_MAX = 127
_CSI_FINAL_MIN = 0x40
_CSI_FINAL_MAX = 0x7E
_COMMANDS = {
    "create": "revlink create",
    "restore": "revlink restore",
    "remove": "remove",
    "check": "link check",
    "reload": "daemon reload",
    "wait": "daemon start",
    "status": "daemon status",
}
_SINGLE_ROW_OPS = frozenset({"create", "restore", "remove"})
_NO_ROW_OPS = frozenset({"status"})
_READY_MESSAGE = "Daemon started (pid {pid})"
_CHOOSE_NUMBER = "Choose a number."


@dataclass(frozen=True)
class ScreenQuestion:
    """A question shown as output lines before the request is sent."""

    lines: tuple[str, ...]
    choices: tuple[str, ...] | None = None
    invalid: str = _ANSWER_LINE


class ScreenSkip(Exception):
    """Raised when a pre-request answer means the shell should send nothing."""

    def __init__(self, stdout: str, *, exit_code: int = 1) -> None:
        super().__init__(stdout)
        self.stdout = stdout
        self.exit_code = exit_code


def isolation_ack_question(lines: Sequence[str]) -> ScreenQuestion:
    """Return the held-copy / out-of-sync ack asked on the shell screen.

    Args:
        lines: Warning lines already formatted for the screen.

    Returns:
        A yes/no question. Either answer continues; Ctrl+C cancels.
    """
    return ScreenQuestion(
        lines=(*lines, "Continue without resolving held copies and out-of-sync paths?"),
    )


def removal_confirm_question(plan: str) -> ScreenQuestion:
    """Return the yes/no mapping-removal confirm asked on the shell screen.

    Args:
        plan: Multi-line removal plan from ``format_removal_plan``.

    Returns:
        A yes/no question whose prompt is ``Apply these mapping removals?``.
    """
    return ScreenQuestion(lines=(*plan.splitlines(), "Apply these mapping removals?"))


def hub_choice_question(names: Sequence[str]) -> ScreenQuestion:
    """Return the numbered hub choice asked on the shell screen.

    Args:
        names: Managed project names in the order they are numbered.

    Returns:
        A choice question whose answers are ``1`` through ``len(names)``.
    """
    lines = (
        "More than one managed project contributes to this directory:",
        *(f"  {index}. {name}" for index, name in enumerate(names, start=1)),
        "Choose a managed project",
    )
    return ScreenQuestion(
        lines=lines,
        choices=tuple(str(index) for index in range(1, len(names) + 1)),
        invalid=_CHOOSE_NUMBER,
    )


def run_shell_screen(
    request: Request,
    session: RequestSession | None = None,
    *,
    questions: tuple[ScreenQuestion, ...] = (),
    connect: Callable[[tuple[str, ...]], RequestSession] | None = None,
    trailer: tuple[str, ...] = (),
) -> int:
    """Draw the shell screen until the user closes it, then print the transcript.

    Args:
        request: Daemon request. The header uses its operation and target.
        session: Open request channel, or None when *questions* must be answered first.
        questions: Pre-request questions. Nothing is sent until they are answered.
        connect: Opens the request channel from the answers. Used when *questions* is set.
        trailer: Extra output lines appended after the daemon transcript.

    Returns:
        The command's exit code.
    """
    op = str(request.get("op") or "")
    screen = _ShellScreen(
        _header(request),
        single=op in _SINGLE_ROW_OPS,
        fallback=_fallback_project(request),
        op=op,
        trailer=trailer,
    )
    owned: RequestSession | None = None
    try:
        with _Terminal() as terminal:
            owned = screen.run(terminal, session, questions=questions, connect=connect)
        _print_transcript(screen.stdout)
        return screen.exit_code
    finally:
        if owned is not None:
            owned.close()


def _header(request: Request) -> str:
    op = str(request.get("op") or "")
    command = _COMMANDS.get(op, op)
    if op in _SINGLE_ROW_OPS:
        return f"{command}  {request.get('path') or ''}"
    if op == "check":
        name = request.get("project_name") or ""
        target = str(name) if name else "all projects"
        return f"{command}  {target}"
    if op == "wait":
        return f"{command}  all projects"
    if op == "status":
        pid = request.get("pid") or ""
        phase = request.get("phase") or ""
        return f"{pid}  {phase}".strip()
    if op == "reload":
        target = str(request.get("screen_target") or "all projects")
        return f"{command}  {target}"
    path = str(request.get("path") or "")
    return f"{command}  {path}" if path else command


def _fallback_project(request: Request) -> str:
    op = str(request.get("op") or "")
    if op == "check":
        return str(request.get("project_name") or "")
    if op == "reload":
        target = str(request.get("screen_target") or "")
        return "" if not target or target == "all projects" else target
    return ""


def _print_transcript(stdout: str) -> None:
    if not stdout:
        return
    click.echo(stdout, nl=not stdout.endswith("\n"))


def _parse_progress(line: str) -> tuple[str, str, str] | None:
    if " · " in line:
        step, project = line.rsplit(" · ", 1)
    else:
        step, project = line, ""
    project = project.strip()
    step = step.strip()
    named = step.startswith(("Done", "Failed", "Checking", "Catching up"))
    if named and not project:
        return None
    if step.startswith("Waiting"):
        return "waiting", step, project
    if step.startswith("Done"):
        return "done", step, project
    if step.startswith("Failed"):
        return "failed", step, project
    if step.startswith(("Creating", "Restoring", "Removing", "Writing baseline", "Checking", "Catching up")):
        return "working", step, project
    return None


@dataclass
class _UnitRow:
    """One worker unit on the shell screen."""

    project: str = ""
    state: str = "waiting"
    step: str = ""
    started: float = field(default_factory=time.monotonic)
    frozen: float | None = None

    def text(self) -> str:
        """Return the painted row: project, state, step, and elapsed time."""
        end = self.frozen if self.frozen is not None else time.monotonic()
        elapsed = max(0.0, end - self.started)
        project = self.project or "-"
        step = self.step or "-"
        return f"{project}  {self.state}  {step}  {elapsed:.1f}s"


class _ShellScreen:
    """One request's header, worker-unit rows, output, and hint."""

    def __init__(
        self,
        header: str,
        *,
        single: bool,
        fallback: str,
        op: str,
        trailer: tuple[str, ...] = (),
    ) -> None:
        self._lock = threading.Lock()
        self._header = header
        self._fallback = fallback
        self._op = op
        self._trailer = trailer
        self._rows: list[_UnitRow] = [_UnitRow()] if single else []
        self._notes: list[str] = []
        self._output: list[str] = []
        self._question = False
        self._buffer = ""
        self._phase = "running"
        self._exit_code = 1
        self._stdout = ""
        self._cancel_sent = False
        self._closed = False
        self._current_question: ScreenQuestion | None = None
        self._last_answer = ""

    @property
    def stdout(self) -> str:
        """Return the transcript printed after the screen closes."""
        return self._stdout

    @property
    def exit_code(self) -> int:
        """Return the daemon exit code for this request."""
        return self._exit_code

    def run(
        self,
        terminal: _Terminal,
        session: RequestSession | None,
        *,
        questions: tuple[ScreenQuestion, ...] = (),
        connect: Callable[[tuple[str, ...]], RequestSession] | None = None,
    ) -> RequestSession | None:
        """Read keys and progress until the user closes a finished screen.

        Returns:
            The session opened after pre-request questions, when this screen owns it.
        """
        owned: RequestSession | None = None
        if questions:
            owned = self._ask_then_connect(terminal, questions, connect)
            session = owned
            if self._closed:
                return owned
        reader: threading.Thread | None = None
        if session is not None and self._phase != "finished":
            reader = threading.Thread(target=self._read, args=(session,), name="blf-screen", daemon=True)
            reader.start()
        terminal.draw(self._paint())
        while not self._closed:
            try:
                keys = terminal.read_keys(_KEY_POLL_S)
            except KeyboardInterrupt:
                keys = ["ctrl-c"]
            for key in keys:
                self._on_key(key, session)
                if self._closed:
                    break
            if self._closed:
                break
            terminal.draw(self._paint())
        if reader is not None:
            reader.join(timeout=1)
        return owned

    def apply_progress(self, line: str) -> None:
        """Update one worker-unit row from a daemon progress line."""
        parsed = _parse_progress(line)
        if parsed is None:
            return
        state, step, project = parsed
        with self._lock:
            if self._phase == "finished":
                return
            row = self._row_for(project)
            if row.state in {"done", "failed"}:
                return
            if state in {"done", "failed"}:
                row.state = state
                row.frozen = time.monotonic()
                return
            row.state = state
            row.step = step

    def finish(self, response: Request) -> None:
        """Show the plain result and switch the hint to close."""
        with self._lock:
            if self._phase == "finished":
                return
            try:
                code = int(response.get("exit_code", 1))
            except (TypeError, ValueError):
                code = 1
            text = str(response.get("stdout") or "")
            if self._op == "wait" and code == 0:
                text = f"{_READY_MESSAGE.format(pid=response.get('pid'))}\n"
            if self._op == "status":
                pid = response.get("pid")
                phase = response.get("phase")
                if pid is not None and phase is not None:
                    self._header = f"{pid}  {phase}"
            if self._trailer:
                extra = "\n".join(self._trailer)
                text = f"{text.rstrip()}\n{extra}\n" if text.strip() else f"{extra}\n"
            self._stdout = text
            self._exit_code = code
            self._output = [*self._notes, *text.splitlines()]
            if not self._rows and self._op not in _NO_ROW_OPS:
                self._rows.append(_UnitRow(project=self._fallback))
            now = time.monotonic()
            final = "done" if code == 0 else "failed"
            for row in self._rows:
                if row.state not in {"done", "failed"}:
                    row.state = final
                if row.frozen is None:
                    row.frozen = now
            self._phase = "finished"
            self._question = False
            self._buffer = ""

    def fail(self, text: str) -> None:
        """Finish the screen with *text* and a failed row."""
        if not text.endswith("\n"):
            text = f"{text}\n"
        self.finish({"exit_code": 1, "stdout": text})

    def _read(self, session: RequestSession) -> None:
        try:
            while True:
                message = session.read_message()
                if message is None:
                    self.fail(_daemon_down_text())
                    return
                progress = message.get("progress")
                if progress is not None and "exit_code" not in message:
                    self.apply_progress(str(progress))
                    continue
                self.finish(message)
                return
        except OSError:
            self.fail(_daemon_down_text())

    def _ask_then_connect(
        self,
        terminal: _Terminal,
        questions: tuple[ScreenQuestion, ...],
        connect: Callable[[tuple[str, ...]], RequestSession] | None,
    ) -> RequestSession | None:
        answers: list[str] = []
        self._phase = "asking"
        for question in questions:
            self._begin_question(question)
            terminal.draw(self._paint())
            while self._question and not self._closed:
                try:
                    keys = terminal.read_keys(_KEY_POLL_S)
                except KeyboardInterrupt:
                    keys = ["ctrl-c"]
                for key in keys:
                    self._on_ask_key(key)
                    if self._closed or not self._question:
                        break
                terminal.draw(self._paint())
            if self._closed:
                return None
            answers.append(self._last_answer)
        if connect is None:
            self._phase = "running"
            return None
        try:
            session = connect(tuple(answers))
        except OSError:
            self.fail(_daemon_down_text())
            return None
        except ScreenSkip as skipped:
            self.finish({"exit_code": skipped.exit_code, "stdout": skipped.stdout})
            return None
        self._phase = "running"
        return session

    def _begin_question(self, question: ScreenQuestion) -> None:
        with self._lock:
            self._notes.extend(question.lines)
            self._current_question = question
            self._question = True
            self._buffer = ""

    def _on_ask_key(self, key: str) -> None:
        if key == "ctrl-c":
            self._closed = True
            return
        if key == "enter":
            self._submit_ask()
            return
        if key == "backspace":
            with self._lock:
                self._buffer = self._buffer[:-1]
            return
        if len(key) == 1 and key.isprintable():
            with self._lock:
                if len(self._buffer) < _INPUT_LIMIT:
                    self._buffer += key

    def _submit_ask(self) -> None:
        with self._lock:
            answer = self._buffer.strip()
            self._buffer = ""
            question = self._current_question
            if not self._question or question is None:
                return
            accepted = _accepted_answer(question, answer)
            if accepted is None:
                self._notes.append(question.invalid)
                return
            self._last_answer = accepted
            self._question = False
            self._current_question = None

    def _on_key(self, key: str, session: RequestSession | None) -> None:
        with self._lock:
            phase = self._phase
            question = self._question
        if phase == "finished":
            if key in {"q", "ctrl-c"}:
                self._closed = True
            return
        if question:
            self._on_question_key(key, session)
            return
        if key == "ctrl-c" and session is not None:
            self._ask_stop()

    def _ask_stop(self) -> None:
        with self._lock:
            if self._phase != "running" or self._cancel_sent:
                return
            self._notes.append(_STOP_QUESTION)
            self._question = True
            self._buffer = ""

    def _on_question_key(self, key: str, session: RequestSession) -> None:
        if key == "ctrl-c":
            self._confirm_stop(session)
            return
        if key == "esc":
            self._continue()
            return
        if key == "enter":
            self._submit(session)
            return
        if key == "backspace":
            with self._lock:
                self._buffer = self._buffer[:-1]
            return
        if len(key) == 1 and key.isprintable():
            with self._lock:
                if len(self._buffer) < _INPUT_LIMIT:
                    self._buffer += key

    def _submit(self, session: RequestSession) -> None:
        with self._lock:
            answer = self._buffer.strip().lower()
            self._buffer = ""
            if not self._question or self._phase != "running":
                return
        if answer == "y":
            self._confirm_stop(session)
            return
        if answer == "n":
            self._continue()
            return
        with self._lock:
            if self._question:
                self._notes.append(_ANSWER_LINE)

    def _continue(self) -> None:
        with self._lock:
            self._question = False
            self._buffer = ""

    def _confirm_stop(self, session: RequestSession) -> None:
        send = False
        with self._lock:
            if self._phase != "running":
                return
            if not self._cancel_sent:
                self._cancel_sent = True
                send = True
            self._question = False
            self._buffer = ""
        if send:
            session.cancel()

    def _row_for(self, project: str) -> _UnitRow:
        if project:
            for row in self._rows:
                if row.project == project:
                    return row
            for row in self._rows:
                if not row.project:
                    row.project = project
                    return row
            row = _UnitRow(project=project)
            self._rows.append(row)
            return row
        if self._rows:
            return self._rows[0]
        row = _UnitRow()
        self._rows.append(row)
        return row

    def _paint(self) -> str:
        columns, rows = _terminal_size()
        with self._lock:
            header = self._header
            unit_lines = [row.text() for row in self._rows]
            hint = self._hint_text()
            output = list(self._output if self._phase == "finished" else self._notes)
            question = self._question and self._phase in {"running", "asking"}
            typed = self._buffer
        reserved = len(unit_lines) + 2 + (1 if question else 0)
        body_height = max(0, rows - reserved)
        visible = output[-body_height:] if body_height else []
        if len(visible) < body_height:
            visible.extend([""] * (body_height - len(visible)))
        lines = [header, *unit_lines, *visible]
        if question:
            lines.append(f"> {typed}")
        lines.append(hint)
        return _render(columns, lines)

    def _hint_text(self) -> str:
        if self._phase == "finished":
            return _HINT_DONE
        if self._phase == "asking":
            return _HINT_ASK
        if self._question:
            return _HINT_STOP
        return _HINT_RUNNING


class _Terminal:
    """Raw mode and the alternate screen for the shell attached to this process."""

    def __init__(self) -> None:
        self._fd = -1
        self._attrs: list[object] | None = None

    def __enter__(self) -> _Terminal:
        self._fd = sys.stdin.fileno()
        if os.name != "nt":
            self._attrs = termios.tcgetattr(self._fd)
            tty.setraw(self._fd)
        _write_stdout(_ALT_ENTER)
        return self

    def __exit__(self, *_exc: object) -> None:
        _write_stdout(_ALT_LEAVE)
        if self._attrs is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._attrs)

    def draw(self, frame: str) -> None:
        """Replace the visible screen with *frame*."""
        _write_stdout(frame)

    def read_keys(self, timeout: float) -> list[str]:
        """Return keys typed within *timeout* seconds."""
        if os.name == "nt":
            return _read_keys_windows(timeout)
        return _read_keys_posix(self._fd, timeout)


def _accepted_answer(question: ScreenQuestion, answer: str) -> str | None:
    if question.choices is not None:
        return answer if answer in question.choices else None
    lowered = answer.lower()
    if lowered in {"y", "n"}:
        return lowered
    return None


def _daemon_down_text() -> str:
    from .client import DAEMON_DOWN_HINT  # noqa: PLC0415

    return f"{DAEMON_DOWN_HINT}\n"


def _terminal_size() -> tuple[int, int]:
    try:
        size = os.get_terminal_size(sys.stdout.fileno())
    except OSError:
        return _FALLBACK_COLUMNS, _FALLBACK_ROWS
    columns = size.columns if size.columns >= _MIN_COLUMNS else _FALLBACK_COLUMNS
    rows = size.lines if size.lines >= _MIN_ROWS else _FALLBACK_ROWS
    return columns, rows


def _render(columns: int, lines: list[str]) -> str:
    parts = ["\x1b[2J"]
    for index, line in enumerate(lines, start=1):
        parts.append(f"\x1b[{index};1H\x1b[2K{_clip(line, columns)}")
    return "".join(parts)


def _clip(text: str, columns: int) -> str:
    if len(text) <= columns:
        return text
    if columns <= 1:
        return text[:columns]
    return text[: columns - 1] + "…"


def _write_stdout(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def _read_keys_posix(fd: int, timeout: float) -> list[str]:
    try:
        ready, _, _ = select.select([fd], [], [], timeout)
    except (OSError, ValueError):
        return []
    if not ready:
        return []
    try:
        data = os.read(fd, _KEY_READ_SIZE)
    except OSError:
        return []
    if not data:
        return []
    return _decode_keys(data)


_WINDOWS_KEYS = {
    "\x03": "ctrl-c",
    "\x1b": "esc",
    "\r": "enter",
    "\n": "enter",
    "\x08": "backspace",
}


def _read_keys_windows(timeout: float) -> list[str]:
    import msvcrt  # noqa: PLC0415

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not msvcrt.kbhit():
            time.sleep(_KEY_POLL_S)
            continue
        char = msvcrt.getwch()
        if char in {"\x00", "\xe0"}:
            msvcrt.getwch()
            return []
        return _windows_key(char)
    return []


def _windows_key(char: str) -> list[str]:
    named = _WINDOWS_KEYS.get(char)
    if named is not None:
        return [named]
    if len(char) == 1 and char.isprintable():
        return [char]
    return []


def _decode_keys(data: bytes) -> list[str]:
    keys: list[str] = []
    index = 0
    limit = len(data)
    while index < limit:
        byte = data[index]
        if byte == _CTRL_C:
            keys.append("ctrl-c")
            index += 1
            continue
        if byte == _ESC:
            index = _skip_or_take_esc(data, index, keys)
            continue
        if byte in {_CR, _LF}:
            keys.append("enter")
            index += 1
            continue
        if byte in {_BS, _DEL}:
            keys.append("backspace")
            index += 1
            continue
        if _PRINTABLE_MIN <= byte < _PRINTABLE_MAX:
            keys.append(chr(byte))
            index += 1
            continue
        index += 1
    return keys


def _skip_or_take_esc(data: bytes, index: int, keys: list[str]) -> int:
    if index + 1 < len(data) and data[index + 1] == ord("["):
        index += 2
        while index < len(data) and not _CSI_FINAL_MIN <= data[index] <= _CSI_FINAL_MAX:
            index += 1
        if index < len(data):
            return index + 1
        return index
    keys.append("esc")
    return index + 1
