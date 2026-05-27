"""Unit tests for RestoreFormatter output.

Covers task 8.3:
- Each RestoreFormatter method produces the expected string
- All methods produce [dry-run] prefix when dry_run=True
"""

from pathlib import Path
from unittest.mock import patch

from beyond_local_file.operations.revlink import RestoreFormatter

# ---------------------------------------------------------------------------
# RestoreFormatter tests (Requirements 7.1-7.10)
# ---------------------------------------------------------------------------


class TestRestoreFormatterNoDryRun:
    """Tests for RestoreFormatter with dry_run=False.

    Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9
    """

    def setup_method(self) -> None:
        """Create a formatter with dry_run=False for each test."""
        self.formatter = RestoreFormatter(dry_run=False)

    def test_removing_symlink(self) -> None:
        """removing_symlink emits the expected message without prefix.

        Requirements: 7.1
        """
        with patch("click.echo") as mock_echo:
            self.formatter.removing_symlink(Path("/some/path"))
        mock_echo.assert_called_once_with("Removing symlink at /some/path")

    def test_copying_back(self) -> None:
        """copying_back emits the expected message without prefix.

        Requirements: 7.2
        """
        with patch("click.echo") as mock_echo:
            self.formatter.copying_back(Path("/managed/file.txt"), Path("/cwd/file.txt"))
        mock_echo.assert_called_once_with("Copying /managed/file.txt -> /cwd/file.txt")

    def test_computing_checksum(self) -> None:
        """computing_checksum emits the expected message without prefix.

        Requirements: 7.3
        """
        with patch("click.echo") as mock_echo:
            self.formatter.computing_checksum(Path("/managed/file.txt"))
        mock_echo.assert_called_once_with("Computing checksum of /managed/file.txt")

    def test_checksum_ok(self) -> None:
        """checksum_ok emits the expected message without prefix.

        Requirements: 7.4
        """
        with patch("click.echo") as mock_echo:
            self.formatter.checksum_ok()
        mock_echo.assert_called_once_with("✓ MD5 checksum verified")

    def test_managed_copy_deleted(self) -> None:
        """managed_copy_deleted emits the expected message without prefix.

        Requirements: 7.5
        """
        with patch("click.echo") as mock_echo:
            self.formatter.managed_copy_deleted(Path("/managed/file.txt"))
        mock_echo.assert_called_once_with("✓ Managed copy deleted: /managed/file.txt")

    def test_managed_copy_delete_failed(self) -> None:
        """managed_copy_delete_failed emits the expected warning message without prefix.

        Requirements: 7.6
        """
        with patch("click.echo") as mock_echo:
            self.formatter.managed_copy_delete_failed(Path("/managed/file.txt"))
        mock_echo.assert_called_once_with("Warning: could not delete managed copy at /managed/file.txt")

    def test_git_exclude_removed(self) -> None:
        """git_exclude_removed emits the expected message without prefix.

        Requirements: 7.7
        """
        with patch("click.echo") as mock_echo:
            self.formatter.git_exclude_removed("myfile.txt")
        mock_echo.assert_called_once_with("Removed 'myfile.txt' from .git/info/exclude")

    def test_git_exclude_not_found(self) -> None:
        """git_exclude_not_found emits the expected message without prefix.

        Requirements: 7.8
        """
        with patch("click.echo") as mock_echo:
            self.formatter.git_exclude_not_found("myfile.txt")
        mock_echo.assert_called_once_with("'myfile.txt' not in .git/info/exclude")

    def test_config_entry_removed(self) -> None:
        """config_entry_removed emits the expected message without prefix.

        Requirements: 7.9
        """
        with patch("click.echo") as mock_echo:
            self.formatter.config_entry_removed("myfile.txt")
        mock_echo.assert_called_once_with("Removed 'myfile.txt' from config subpath list")

    def test_error(self) -> None:
        """error emits the expected message without prefix.

        Requirements: 7.1-7.9 (error path)
        """
        with patch("click.echo") as mock_echo:
            self.formatter.error("something went wrong")
        mock_echo.assert_called_once_with("Error: something went wrong")


class TestRestoreFormatterDryRun:
    """Tests for RestoreFormatter with dry_run=True — all output prefixed with [dry-run].

    Requirements: 7.10
    """

    def setup_method(self) -> None:
        """Create a formatter with dry_run=True for each test."""
        self.formatter = RestoreFormatter(dry_run=True)

    def test_removing_symlink_dry_run(self) -> None:
        """removing_symlink emits [dry-run] prefix when dry_run=True.

        Requirements: 7.1, 7.10
        """
        with patch("click.echo") as mock_echo:
            self.formatter.removing_symlink(Path("/some/path"))
        mock_echo.assert_called_once_with("[dry-run] Removing symlink at /some/path")

    def test_copying_back_dry_run(self) -> None:
        """copying_back emits [dry-run] prefix when dry_run=True.

        Requirements: 7.2, 7.10
        """
        with patch("click.echo") as mock_echo:
            self.formatter.copying_back(Path("/managed/file.txt"), Path("/cwd/file.txt"))
        mock_echo.assert_called_once_with("[dry-run] Copying /managed/file.txt -> /cwd/file.txt")

    def test_computing_checksum_dry_run(self) -> None:
        """computing_checksum emits [dry-run] prefix when dry_run=True.

        Requirements: 7.3, 7.10
        """
        with patch("click.echo") as mock_echo:
            self.formatter.computing_checksum(Path("/managed/file.txt"))
        mock_echo.assert_called_once_with("[dry-run] Computing checksum of /managed/file.txt")

    def test_checksum_ok_dry_run(self) -> None:
        """checksum_ok emits [dry-run] prefix when dry_run=True.

        Requirements: 7.4, 7.10
        """
        with patch("click.echo") as mock_echo:
            self.formatter.checksum_ok()
        mock_echo.assert_called_once_with("[dry-run] ✓ MD5 checksum verified")

    def test_managed_copy_deleted_dry_run(self) -> None:
        """managed_copy_deleted emits [dry-run] prefix when dry_run=True.

        Requirements: 7.5, 7.10
        """
        with patch("click.echo") as mock_echo:
            self.formatter.managed_copy_deleted(Path("/managed/file.txt"))
        mock_echo.assert_called_once_with("[dry-run] ✓ Managed copy deleted: /managed/file.txt")

    def test_managed_copy_delete_failed_dry_run(self) -> None:
        """managed_copy_delete_failed emits [dry-run] prefix when dry_run=True.

        Requirements: 7.6, 7.10
        """
        with patch("click.echo") as mock_echo:
            self.formatter.managed_copy_delete_failed(Path("/managed/file.txt"))
        mock_echo.assert_called_once_with("[dry-run] Warning: could not delete managed copy at /managed/file.txt")

    def test_git_exclude_removed_dry_run(self) -> None:
        """git_exclude_removed emits [dry-run] prefix when dry_run=True.

        Requirements: 7.7, 7.10
        """
        with patch("click.echo") as mock_echo:
            self.formatter.git_exclude_removed("myfile.txt")
        mock_echo.assert_called_once_with("[dry-run] Removed 'myfile.txt' from .git/info/exclude")

    def test_git_exclude_not_found_dry_run(self) -> None:
        """git_exclude_not_found emits [dry-run] prefix when dry_run=True.

        Requirements: 7.8, 7.10
        """
        with patch("click.echo") as mock_echo:
            self.formatter.git_exclude_not_found("myfile.txt")
        mock_echo.assert_called_once_with("[dry-run] 'myfile.txt' not in .git/info/exclude")

    def test_config_entry_removed_dry_run(self) -> None:
        """config_entry_removed emits [dry-run] prefix when dry_run=True.

        Requirements: 7.9, 7.10
        """
        with patch("click.echo") as mock_echo:
            self.formatter.config_entry_removed("myfile.txt")
        mock_echo.assert_called_once_with("[dry-run] Removed 'myfile.txt' from config subpath list")

    def test_error_dry_run(self) -> None:
        """error emits [dry-run] prefix when dry_run=True.

        Requirements: 7.10
        """
        with patch("click.echo") as mock_echo:
            self.formatter.error("something went wrong")
        mock_echo.assert_called_once_with("[dry-run] Error: something went wrong")
