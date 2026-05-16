"""Tests for upgrade detection logic."""

import sys

import pytest

from beyond_local_file.operations.upgrade import InstallMethod, detect_install_method


class TestDetectInstallMethod:
    """Tests for detect_install_method — guards against path-convention changes in uv and pipx."""

    def test_uv_tool_unix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Recognises a uv tool install on Unix."""
        monkeypatch.setattr(sys, "executable", "/home/user/.local/share/uv/tools/beyond-local-file/bin/python")

        assert detect_install_method() == InstallMethod.UV_TOOL

    def test_uv_tool_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Recognises a uv tool install on Windows (forward-slash normalised path)."""
        monkeypatch.setattr(
            sys,
            "executable",
            "C:/Users/user/AppData/Roaming/uv/tools/beyond-local-file/bin/python.exe",
        )

        assert detect_install_method() == InstallMethod.UV_TOOL

    def test_pipx_unix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Recognises a pipx install on Unix."""
        monkeypatch.setattr(
            sys,
            "executable",
            "/home/user/.local/share/pipx/venvs/beyond-local-file/bin/python",
        )

        assert detect_install_method() == InstallMethod.PIPX

    def test_pipx_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Recognises a pipx install on Windows (forward-slash normalised path)."""
        monkeypatch.setattr(
            sys,
            "executable",
            "C:/Users/user/AppData/Local/pipx/venvs/beyond-local-file/bin/python.exe",
        )

        assert detect_install_method() == InstallMethod.PIPX

    def test_uv_managed_python_is_not_tool_install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A uv-managed Python interpreter is not mistaken for a uv tool install.

        uv stores managed Python runtimes under uv/python/, which does not
        contain the uv/tools/<package>/ fragment. This guards against false positives
        when the tool is run via a uv-managed Python that is not a tool venv.
        """
        monkeypatch.setattr(
            sys,
            "executable",
            "/home/user/.local/share/uv/python/cpython-3.13.0-linux-x86_64/bin/python",
        )

        assert detect_install_method() == InstallMethod.UNKNOWN

    def test_dev_venv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A local development venv returns UNKNOWN."""
        monkeypatch.setattr(sys, "executable", "/home/user/projects/beyond-local-file/.venv/bin/python")

        assert detect_install_method() == InstallMethod.UNKNOWN

    def test_system_python(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A system Python interpreter returns UNKNOWN."""
        monkeypatch.setattr(sys, "executable", "/usr/bin/python3")

        assert detect_install_method() == InstallMethod.UNKNOWN
