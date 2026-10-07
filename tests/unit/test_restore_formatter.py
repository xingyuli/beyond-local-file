"""Unit tests for restore render output.

Covers task 8.3:
- Each restore story line produces the expected string
- All methods produce [dry-run] prefix when dry_run=True
"""

from beyond_local_file.operations.result import RestoreResult, render


def _restore_result(**fields: object) -> RestoreResult:
    """Return a RestoreResult with lab-app / alpha / example stand-ins."""
    values: dict[str, object] = {
        "exit_code": 0,
        "dry_run": False,
        "errors": (),
        "leftover_symlink": False,
        "source": "/tmp/alpha/example",
        "managed": "/tmp/lab-app/example",
        "replica_deletes": (),
        "git_excludes": (),
        "config_removed": None,
        "persist_warning": None,
    }
    values.update(fields)
    return RestoreResult(**values)  # type: ignore[arg-type]


class TestRestoreFormatterNoDryRun:
    """Tests for render(RestoreResult) with dry_run=False.

    Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9
    """

    def test_removing_symlink(self) -> None:
        """removing_symlink emits the expected message without prefix.

        Requirements: 7.1
        """
        text = render(_restore_result(leftover_symlink=True))
        assert "Removing symlink at /tmp/alpha/example" in text

    def test_copying_back(self) -> None:
        """copying_back emits the expected message without prefix.

        Requirements: 7.2
        """
        text = render(_restore_result(leftover_symlink=True))
        assert "Copying /tmp/lab-app/example -> /tmp/alpha/example" in text

    def test_leaving_target_file(self) -> None:
        """leaving_target_file emits the expected message without prefix."""
        assert "Leaving target file in place: /tmp/alpha/example" in render(_restore_result())

    def test_managed_copy_deleted(self) -> None:
        """managed_copy_deleted emits the expected message without prefix.

        Requirements: 7.5
        """
        assert "✓ Managed copy deleted: /tmp/lab-app/example" in render(_restore_result())

    def test_replica_copy_deleted(self) -> None:
        """replica_copy_deleted emits the expected message without prefix."""
        text = render(_restore_result(replica_deletes=("/tmp/example/example",)))
        assert "Deleted replica copy: /tmp/example/example" in text

    def test_git_exclude_removed(self) -> None:
        """git_exclude_removed emits the expected message without prefix.

        Requirements: 7.7
        """
        text = render(_restore_result(git_excludes=(("example", "removed"),)))
        assert "Removed 'example' from .git/info/exclude" in text

    def test_git_exclude_not_found(self) -> None:
        """git_exclude_not_found emits the expected message without prefix.

        Requirements: 7.8
        """
        text = render(_restore_result(git_excludes=(("example", "not_found"),)))
        assert "'example' not in .git/info/exclude" in text

    def test_config_entry_removed(self) -> None:
        """config_entry_removed emits the expected message without prefix.

        Requirements: 7.9
        """
        text = render(_restore_result(config_removed="example"))
        assert "Removed 'example' from config subpath list" in text

    def test_error(self) -> None:
        """error emits the expected message without prefix.

        Requirements: 7.1-7.9 (error path)
        """
        assert render(_restore_result(exit_code=1, errors=("something went wrong",))) == (
            "Error: something went wrong\n"
        )


class TestRestoreFormatterDryRun:
    """Tests for render(RestoreResult) with dry_run=True — all output prefixed with [dry-run].

    Requirements: 7.10
    """

    def test_removing_symlink_dry_run(self) -> None:
        """removing_symlink emits [dry-run] prefix when dry_run=True.

        Requirements: 7.1, 7.10
        """
        text = render(_restore_result(dry_run=True, leftover_symlink=True))
        assert "[dry-run] Removing symlink at /tmp/alpha/example" in text

    def test_copying_back_dry_run(self) -> None:
        """copying_back emits [dry-run] prefix when dry_run=True.

        Requirements: 7.2, 7.10
        """
        text = render(_restore_result(dry_run=True, leftover_symlink=True))
        assert "[dry-run] Copying /tmp/lab-app/example -> /tmp/alpha/example" in text

    def test_managed_copy_deleted_dry_run(self) -> None:
        """managed_copy_deleted emits [dry-run] prefix when dry_run=True.

        Requirements: 7.5, 7.10
        """
        text = render(_restore_result(dry_run=True))
        assert "[dry-run] ✓ Managed copy deleted: /tmp/lab-app/example" in text

    def test_replica_copy_deleted_dry_run(self) -> None:
        """replica_copy_deleted emits [dry-run] prefix when dry_run=True."""
        text = render(_restore_result(dry_run=True, replica_deletes=("/tmp/example/example",)))
        assert "[dry-run] Deleted replica copy: /tmp/example/example" in text

    def test_git_exclude_removed_dry_run(self) -> None:
        """git_exclude_removed emits [dry-run] prefix when dry_run=True.

        Requirements: 7.7, 7.10
        """
        text = render(_restore_result(dry_run=True, git_excludes=(("example", "removed"),)))
        assert "[dry-run] Removed 'example' from .git/info/exclude" in text

    def test_git_exclude_not_found_dry_run(self) -> None:
        """git_exclude_not_found emits [dry-run] prefix when dry_run=True.

        Requirements: 7.8, 7.10
        """
        text = render(_restore_result(dry_run=True, git_excludes=(("example", "not_found"),)))
        assert "[dry-run] 'example' not in .git/info/exclude" in text

    def test_config_entry_removed_dry_run(self) -> None:
        """config_entry_removed emits [dry-run] prefix when dry_run=True.

        Requirements: 7.9, 7.10
        """
        text = render(_restore_result(dry_run=True, config_removed="example"))
        assert "[dry-run] Removed 'example' from config subpath list" in text

    def test_error_dry_run(self) -> None:
        """error emits [dry-run] prefix when dry_run=True.

        Requirements: 7.10
        """
        assert render(_restore_result(exit_code=1, dry_run=True, errors=("something went wrong",))) == (
            "[dry-run] Error: something went wrong\n"
        )
