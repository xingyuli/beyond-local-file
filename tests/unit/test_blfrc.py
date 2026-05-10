"""Tests for .blfrc configuration file support."""

from pathlib import Path

import pytest

from beyond_local_file.blfrc import (
    BlfrcError,
    get_home_directory,
    resolve_config_from_blfrc,
)


@pytest.fixture
def temp_home(tmp_path, monkeypatch):
    """Create a temporary home directory for testing.

    Args:
        tmp_path: Pytest temporary directory fixture.
        monkeypatch: Pytest monkeypatch fixture.

    Yields:
        Path to temporary home directory.
    """
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("BLF_HOME", str(home_dir))
    yield home_dir


@pytest.fixture
def config_file(tmp_path):
    """Create a temporary config file.

    Args:
        tmp_path: Pytest temporary directory fixture.

    Returns:
        Path to temporary config file.
    """
    config = tmp_path / "test-config.yml"
    config.write_text("test-project: /tmp/target\n")
    return config


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


class TestResolveConfigFromBlfrc:
    """Tests for resolve_config_from_blfrc function."""

    def test_returns_none_when_blfrc_not_exists(self, temp_home):
        """Test that None is returned when .blfrc doesn't exist."""
        result = resolve_config_from_blfrc()

        assert result is None

    def test_returns_none_when_config_file_field_missing(self, temp_home):
        """Test that None is returned when config_file field is missing."""
        blfrc = temp_home / ".blfrc"
        blfrc.write_text("other_field: value\n")

        result = resolve_config_from_blfrc()

        assert result is None

    def test_returns_none_when_blfrc_is_empty(self, temp_home):
        """Test that None is returned when .blfrc is empty."""
        blfrc = temp_home / ".blfrc"
        blfrc.write_text("")

        result = resolve_config_from_blfrc()

        assert result is None

    def test_single_absolute_path(self, temp_home, config_file):
        """Test resolving single absolute path."""
        blfrc = temp_home / ".blfrc"
        blfrc.write_text(f"config_file: {config_file}\n")

        result = resolve_config_from_blfrc()

        assert result == [config_file]

    def test_single_relative_path(self, temp_home, tmp_path):
        """Test resolving single relative path (relative to home)."""
        config = temp_home / "configs" / "test.yml"
        config.parent.mkdir()
        config.write_text("test: /tmp/target\n")

        blfrc = temp_home / ".blfrc"
        blfrc.write_text("config_file: configs/test.yml\n")

        result = resolve_config_from_blfrc()

        assert result == [config]

    def test_single_tilde_path(self, temp_home):
        """Test resolving single tilde-expanded path."""
        config = temp_home / "test.yml"
        config.write_text("test: /tmp/target\n")

        blfrc = temp_home / ".blfrc"
        blfrc.write_text("config_file: ~/test.yml\n")

        result = resolve_config_from_blfrc()

        assert result == [config]

    def test_multiple_config_files(self, temp_home):
        """Test resolving multiple config files."""
        config1 = temp_home / "config1.yml"
        config2 = temp_home / "config2.yml"
        config1.write_text("project1: /tmp/target1\n")
        config2.write_text("project2: /tmp/target2\n")

        blfrc = temp_home / ".blfrc"
        blfrc.write_text(f"config_file:\n  - {config1}\n  - {config2}\n")

        result = resolve_config_from_blfrc()

        assert result == [config1, config2]

    def test_error_on_permission_denied(self, temp_home):
        """Test that BlfrcError is raised when .blfrc is not readable."""
        blfrc = temp_home / ".blfrc"
        blfrc.write_text("config_file: test.yml\n")
        blfrc.chmod(0o000)

        with pytest.raises(BlfrcError, match=r"Cannot read.*Permission denied"):
            resolve_config_from_blfrc()

        # Cleanup
        blfrc.chmod(0o644)

    def test_error_on_invalid_yaml(self, temp_home):
        """Test that BlfrcError is raised on invalid YAML syntax."""
        blfrc = temp_home / ".blfrc"
        blfrc.write_text("config_file: [\n")  # Invalid YAML

        with pytest.raises(BlfrcError, match="Invalid YAML"):
            resolve_config_from_blfrc()

    def test_error_on_empty_string(self, temp_home):
        """Test that BlfrcError is raised when config_file is empty string."""
        blfrc = temp_home / ".blfrc"
        blfrc.write_text('config_file: ""\n')

        with pytest.raises(BlfrcError, match="cannot be empty"):
            resolve_config_from_blfrc()

    def test_error_on_whitespace_only(self, temp_home):
        """Test that BlfrcError is raised when config_file is whitespace only."""
        blfrc = temp_home / ".blfrc"
        blfrc.write_text('config_file: "   "\n')

        with pytest.raises(BlfrcError, match="cannot be empty"):
            resolve_config_from_blfrc()

    def test_error_on_empty_list(self, temp_home):
        """Test that BlfrcError is raised when config_file is empty list."""
        blfrc = temp_home / ".blfrc"
        blfrc.write_text("config_file: []\n")

        with pytest.raises(BlfrcError, match="cannot be an empty list"):
            resolve_config_from_blfrc()

    def test_error_on_wrong_type_number(self, temp_home):
        """Test that BlfrcError is raised when config_file is a number."""
        blfrc = temp_home / ".blfrc"
        blfrc.write_text("config_file: 123\n")

        with pytest.raises(BlfrcError, match="must be a string or list of strings"):
            resolve_config_from_blfrc()

    def test_error_on_wrong_type_dict(self, temp_home):
        """Test that BlfrcError is raised when config_file is a dict."""
        blfrc = temp_home / ".blfrc"
        blfrc.write_text("config_file:\n  key: value\n")

        with pytest.raises(BlfrcError, match="must be a string or list of strings"):
            resolve_config_from_blfrc()

    def test_error_on_list_with_non_string(self, temp_home):
        """Test that BlfrcError is raised when list contains non-string."""
        blfrc = temp_home / ".blfrc"
        blfrc.write_text("config_file:\n  - test.yml\n  - 123\n")

        with pytest.raises(BlfrcError, match="must be strings"):
            resolve_config_from_blfrc()

    def test_error_on_config_file_not_found(self, temp_home):
        """Test that BlfrcError is raised when config file doesn't exist."""
        blfrc = temp_home / ".blfrc"
        blfrc.write_text("config_file: nonexistent.yml\n")

        with pytest.raises(BlfrcError, match="Config file not found"):
            resolve_config_from_blfrc()

    def test_error_on_config_file_is_directory(self, temp_home):
        """Test that BlfrcError is raised when config file is a directory."""
        config_dir = temp_home / "configs"
        config_dir.mkdir()

        blfrc = temp_home / ".blfrc"
        blfrc.write_text(f"config_file: {config_dir}\n")

        with pytest.raises(BlfrcError, match="is a directory"):
            resolve_config_from_blfrc()

    def test_error_on_config_file_not_readable(self, temp_home):
        """Test that BlfrcError is raised when config file is not readable."""
        config = temp_home / "test.yml"
        config.write_text("test: /tmp/target\n")
        config.chmod(0o000)

        blfrc = temp_home / ".blfrc"
        blfrc.write_text(f"config_file: {config}\n")

        with pytest.raises(BlfrcError, match=r"Cannot read config file.*Permission denied"):
            resolve_config_from_blfrc()

        # Cleanup
        config.chmod(0o644)

    def test_error_message_includes_file_number_for_multiple_files(self, temp_home):
        """Test that error message includes file number when multiple files specified."""
        config1 = temp_home / "config1.yml"
        config1.write_text("test: /tmp/target\n")

        blfrc = temp_home / ".blfrc"
        blfrc.write_text(f"config_file:\n  - {config1}\n  - nonexistent.yml\n")

        with pytest.raises(BlfrcError, match="file 2 of 2"):
            resolve_config_from_blfrc()

    def test_strips_whitespace_from_paths(self, temp_home):
        """Test that whitespace is stripped from config file paths."""
        config = temp_home / "test.yml"
        config.write_text("test: /tmp/target\n")

        blfrc = temp_home / ".blfrc"
        blfrc.write_text(f"config_file: '  {config}  '\n")

        result = resolve_config_from_blfrc()

        assert result == [config]
