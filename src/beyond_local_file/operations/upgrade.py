"""Self-upgrade logic for the beyond-local-file CLI.

Detects the active installation method by inspecting the Python interpreter
path, then delegates to the appropriate package manager to perform the upgrade.

Supported installation methods:
- ``uv tool install`` — detected via the uv tools directory in sys.executable
- ``pipx install`` — detected via the pipx venvs directory in sys.executable
"""

import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from rich.console import Console

# Package name as registered on PyPI
_PACKAGE_NAME = "beyond-local-file"


class InstallMethod(StrEnum):
    """Detected installation method for the upgrade command.

    Attributes:
        UV_TOOL: Installed via ``uv tool install``.
        PIPX: Installed via ``pipx install``.
        UNKNOWN: Installation method could not be determined.
    """

    UV_TOOL = "uv_tool"
    PIPX = "pipx"
    UNKNOWN = "unknown"


# Path fragments that identify each install method.
# as_posix() normalises Windows backslashes before comparison, so these
# forward-slash fragments match on both Unix and Windows.
_UV_TOOL_MARKER = f"uv/tools/{_PACKAGE_NAME}/"
_PIPX_MARKER = f"pipx/venvs/{_PACKAGE_NAME}/"

_METHOD_LABEL: dict[InstallMethod, str] = {
    InstallMethod.UV_TOOL: "uv tool",
    InstallMethod.PIPX: "pipx",
}


@dataclass(frozen=True)
class UpgradeResolution:
    """Pure result of resolving the upgrade strategy for the current installation.

    Attributes:
        method: The detected installation method.
        command: Upgrade command tokens ready for ``subprocess.run``, or ``None``
            when the method is ``InstallMethod.UNKNOWN``.
        label: Human-readable label for the detected method, or ``None`` when unknown.
    """

    method: InstallMethod
    command: list[str] | None
    label: str | None


def detect_install_method() -> InstallMethod:
    """Infer how the tool was installed from the active Python interpreter path.

    Inspects ``sys.executable`` for path fragments that are characteristic of
    each supported package manager's virtual environment layout.

    Returns:
        The detected ``InstallMethod``. Returns ``InstallMethod.UNKNOWN`` when
        the path does not match any known layout.
    """
    executable = str(Path(sys.executable).as_posix())
    if _UV_TOOL_MARKER in executable:
        return InstallMethod.UV_TOOL
    if _PIPX_MARKER in executable:
        return InstallMethod.PIPX
    return InstallMethod.UNKNOWN


def build_upgrade_command(method: InstallMethod) -> list[str] | None:
    """Return the shell command that upgrades the tool for the given install method.

    Args:
        method: The detected installation method.

    Returns:
        A list of command tokens suitable for ``subprocess.run``, or ``None``
        when the method is ``InstallMethod.UNKNOWN``.
    """
    if method == InstallMethod.UV_TOOL:
        return ["uv", "tool", "install", "--upgrade", _PACKAGE_NAME]
    if method == InstallMethod.PIPX:
        return ["pipx", "upgrade", _PACKAGE_NAME]
    return None


def resolve_upgrade() -> UpgradeResolution:
    """Resolve the upgrade strategy for the current installation.

    Combines detection and command-building into a single pure result with no
    side effects. Callers can inspect the result and decide how to present it
    before executing anything.

    Returns:
        An ``UpgradeResolution`` describing the detected method, the command to
        run, and a human-readable label. ``command`` and ``label`` are ``None``
        when the install method cannot be determined.
    """
    method = detect_install_method()
    command = build_upgrade_command(method)
    label = _METHOD_LABEL.get(method)
    return UpgradeResolution(method=method, command=command, label=label)


def run_upgrade(*, dry_run: bool = False) -> int:
    """Detect the install method and run the appropriate upgrade command.

    Prints the detected method and the command that will be (or would be, in
    dry-run mode) executed. Returns a non-zero exit code when the install
    method cannot be determined or when the upgrade command fails.

    Args:
        dry_run: When ``True``, print the command without executing it.

    Returns:
        Exit code: ``0`` on success, ``1`` on detection failure or upgrade error.
    """
    console = Console()
    resolution = resolve_upgrade()

    if resolution.command is None:
        console.print(
            "[bold red]Cannot determine install method.[/bold red]\n"
            f"[dim]sys.executable:[/dim] {sys.executable}\n\n"
            "Upgrade manually using the command that matches how you installed the tool:\n\n"
            f"  [bold]uv tool install --upgrade {_PACKAGE_NAME}[/bold]\n"
            f"  [bold]pipx upgrade {_PACKAGE_NAME}[/bold]\n"
            f"  [bold]uv tool install --upgrade git+https://github.com/xingyuli/{_PACKAGE_NAME}.git[/bold]"
        )
        return 1

    console.print(f"Detected install method: [bold]{resolution.label}[/bold]")
    console.print(f"Running: [bold]{' '.join(resolution.command)}[/bold]")

    if dry_run:
        console.print("[dim](dry run — skipping execution)[/dim]")
        return 0

    result = subprocess.run(resolution.command, check=False)
    return result.returncode
