"""Tests for home relocation and runtime_home."""

from pathlib import Path

from beyond_local_file.blfrc import get_home_directory, runtime_home


class TestGetHomeDirectory:
    """Tests for get_home_directory function."""

    def test_respects_blf_home_env_var(self, tmp_path, monkeypatch):
        """Test that BLF_HOME environment variable overrides home directory."""
        test_home = tmp_path / "test_home"
        test_home.mkdir()
        monkeypatch.setenv("BLF_HOME", str(test_home))

        result = get_home_directory()

        assert result == test_home

    def test_uses_system_home_when_no_env_var(self, monkeypatch):
        """Test that system home directory is used when BLF_HOME is not set."""
        monkeypatch.delenv("BLF_HOME", raising=False)

        result = get_home_directory()

        assert result == Path.home()


class TestRuntimeHome:
    """Tests for runtime_home."""

    def test_runtime_home_is_dot_blf_under_relocated_home(self, tmp_path, monkeypatch):
        """BLF_HOME relocates ``~/.blf``."""
        test_home = tmp_path / "test_home"
        test_home.mkdir()
        monkeypatch.setenv("BLF_HOME", str(test_home))

        assert runtime_home() == test_home / ".blf"

    def test_runtime_home_uses_system_home_when_no_env_var(self, monkeypatch):
        """System home is used when BLF_HOME is not set."""
        monkeypatch.delenv("BLF_HOME", raising=False)

        assert runtime_home() == Path.home() / ".blf"
