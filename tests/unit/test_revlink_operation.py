"""Unit tests for CreateOperation git exclude integration and create render output.

Covers task 7.3:
- Git exclude integration: entry added, skipped when not in git repo, idempotent
- render(CreateResult): each story line, with and without [dry-run]
"""

from pathlib import Path

from beyond_local_file.model.config import Mapping
from beyond_local_file.operations.result import CreateResult, render
from beyond_local_file.operations.revlink import (
    CreateOperation,
    RestoreOperation,
    RevlinkContext,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_git_repo(base: Path) -> Path:
    """Create a minimal .git/info/ structure under *base* and return *base*.

    Args:
        base: Directory that should become a fake git repository.

    Returns:
        The same *base* path, now containing ``.git/info/``.
    """
    (base / ".git" / "info").mkdir(parents=True)
    return base


def _make_context(repo_dir: Path, config_path: Path) -> RevlinkContext:
    """Build a minimal RevlinkContext pointing at *repo_dir* as the project root.

    Args:
        repo_dir: Path to use as ``cwd`` (the project/git root).
        config_path: Path to a (possibly non-existent) config file.

    Returns:
        A :class:`RevlinkContext` with a sync-all mapping (no yaml splice).
    """
    mapping = Mapping(targets=[repo_dir], subpaths=None)
    return RevlinkContext(
        config_path=config_path,
        project_name="project",
        matched_mapping=mapping,
        cwd=repo_dir,
    )


def _make_operation(
    source: Path,
    dest_root: Path,
    *,
    dry_run: bool = False,
    force: bool = False,
    context: RevlinkContext | None = None,
) -> CreateOperation:
    """Build a CreateOperation.

    Args:
        source: Source path for the operation.
        dest_root: Destination root for the operation.
        dry_run: Whether to enable dry-run mode.
        force: Whether to enable force mode.
        context: Optional RevlinkContext; when provided the git exclude step
            uses ``context.cwd`` as the repository root.
    """
    return CreateOperation(
        source=source,
        dest_root=dest_root,
        rel_path=Path(source.name),
        dry_run=dry_run,
        force=force,
        context=context,
    )


def _create_result(**fields: object) -> CreateResult:
    """Return a CreateResult with lab-app / alpha / example stand-ins."""
    values: dict[str, object] = {
        "exit_code": 0,
        "dry_run": False,
        "errors": (),
        "already_managed": None,
        "force_overwrite": None,
        "source": "/tmp/alpha/example",
        "dest": "/tmp/lab-app/example",
        "git_exclude": None,
        "git_exclude_name": None,
        "fan_out": (),
        "config_entry": None,
        "persist_warning": None,
    }
    values.update(fields)
    return CreateResult(**values)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Git exclude integration tests (Requirements 6.1, 6.2, 6.3)
# ---------------------------------------------------------------------------


class TestGitExcludePreview:
    """CreateOperation records git exclude; LiveSync writes the exclude file."""

    def test_preview_added_when_in_git_repo(self, tmp_path: Path) -> None:
        """Preview reports an add when the entry is missing; the file is not written."""
        repo_dir = _make_git_repo(tmp_path / "repo")
        source = repo_dir / "myfile.txt"
        source.write_text("hello")

        context = _make_context(repo_dir, tmp_path / "config.yaml")
        result = _make_operation(source, tmp_path / "managed", context=context).run()

        exclude_file = repo_dir / ".git" / "info" / "exclude"
        assert not exclude_file.exists()
        assert result.git_exclude == "added"
        assert result.git_exclude_name == "myfile.txt"

    def test_skipped_when_not_in_git_repo(self, tmp_path: Path) -> None:
        """No .git/info/exclude is created when source is not inside a git repo."""
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        source = plain_dir / "myfile.txt"
        source.write_text("hello")

        context = _make_context(plain_dir, tmp_path / "config.yaml")
        result = _make_operation(source, tmp_path / "managed", context=context).run()

        assert not (plain_dir / ".git").exists(), ".git dir should not be created"
        assert result.git_exclude is None
        assert result.git_exclude_name is None

    def test_preview_exists_when_entry_already_present(self, tmp_path: Path) -> None:
        """Preview reports an existing entry without rewriting the file."""
        repo_dir = _make_git_repo(tmp_path / "repo")
        exclude_file = repo_dir / ".git" / "info" / "exclude"
        exclude_file.write_text("myfile.txt\n")

        source = repo_dir / "myfile.txt"
        source.write_text("hello")

        context = _make_context(repo_dir, tmp_path / "config.yaml")
        result = _make_operation(source, tmp_path / "managed", context=context).run()

        assert exclude_file.read_text() == "myfile.txt\n"
        assert result.git_exclude == "exists"
        assert result.git_exclude_name == "myfile.txt"


# ---------------------------------------------------------------------------
# CreateFormatter tests (Requirements 7.1-7.7)
# ---------------------------------------------------------------------------


class TestCreateFormatterNoDryRun:
    """Tests for render(CreateResult) with dry_run=False."""

    def test_copying(self) -> None:
        """copying emits the expected message without prefix.

        Requirements: 7.2
        """
        assert "Copying /tmp/alpha/example -> /tmp/lab-app/example" in render(_create_result())

    def test_target_left_in_place(self) -> None:
        """target_left_in_place emits the expected message without prefix.

        Requirements: 7.4
        """
        assert "✓ Target path left in place: /tmp/alpha/example" in render(_create_result())

    def test_git_exclude_added(self) -> None:
        """git_exclude_added emits the expected message without prefix.

        Requirements: 7.5
        """
        text = render(_create_result(git_exclude="added", git_exclude_name="example"))
        assert "Added 'example' to .git/info/exclude" in text

    def test_git_exclude_exists(self) -> None:
        """git_exclude_exists emits the expected message without prefix.

        Requirements: 7.5
        """
        text = render(_create_result(git_exclude="exists", git_exclude_name="example"))
        assert "'example' already in .git/info/exclude" in text

    def test_force_warning(self) -> None:
        """force_warning emits the expected message without prefix.

        Requirements: 7.7
        """
        text = render(_create_result(force_overwrite="/tmp/lab-app/example"))
        assert "Warning: overwriting existing managed copy at /tmp/lab-app/example" in text

    def test_error(self) -> None:
        """error emits the expected message without prefix.

        Requirements: 7.1-7.7 (error path)
        """
        assert render(_create_result(exit_code=1, errors=("some error",))) == "Error: some error\n"


class TestCreateFormatterDryRun:
    """Tests for render(CreateResult) with dry_run=True — all output prefixed with [dry-run].

    Requirements: 7.6
    """

    def test_copying_dry_run(self) -> None:
        """copying emits [dry-run] prefix when dry_run=True.

        Requirements: 7.2, 7.6
        """
        assert "[dry-run] Copying /tmp/alpha/example -> /tmp/lab-app/example" in render(_create_result(dry_run=True))

    def test_target_left_in_place_dry_run(self) -> None:
        """target_left_in_place emits [dry-run] prefix when dry_run=True.

        Requirements: 7.4, 7.6
        """
        assert "[dry-run] ✓ Target path left in place: /tmp/alpha/example" in render(_create_result(dry_run=True))

    def test_git_exclude_added_dry_run(self) -> None:
        """git_exclude_added emits [dry-run] prefix when dry_run=True.

        Requirements: 7.5, 7.6
        """
        text = render(_create_result(dry_run=True, git_exclude="added", git_exclude_name="example"))
        assert "[dry-run] Added 'example' to .git/info/exclude" in text

    def test_git_exclude_exists_dry_run(self) -> None:
        """git_exclude_exists emits [dry-run] prefix when dry_run=True.

        Requirements: 7.5, 7.6
        """
        text = render(_create_result(dry_run=True, git_exclude="exists", git_exclude_name="example"))
        assert "[dry-run] 'example' already in .git/info/exclude" in text

    def test_force_warning_dry_run(self) -> None:
        """force_warning emits [dry-run] prefix when dry_run=True.

        Requirements: 7.6, 7.7
        """
        text = render(_create_result(dry_run=True, force_overwrite="/tmp/lab-app/example"))
        assert "[dry-run] Warning: overwriting existing managed copy at /tmp/lab-app/example" in text

    def test_error_dry_run(self) -> None:
        """error emits [dry-run] prefix when dry_run=True.

        Requirements: 7.6
        """
        assert render(_create_result(exit_code=1, dry_run=True, errors=("some error",))) == (
            "[dry-run] Error: some error\n"
        )


# ---------------------------------------------------------------------------
# context is None — git exclude skipped silently (Requirement 3.4)
# ---------------------------------------------------------------------------


class TestContextNoneSkipsGitExclude:
    """context=None skips git exclude without writing or formatter calls."""

    def test_create_operation_context_none_skips_git_exclude(self, tmp_path: Path) -> None:
        """CreateOperation preview does not write exclude when context is None."""
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        source = plain_dir / "myfile.txt"
        source.write_text("hello")

        op = CreateOperation(
            source=source,
            dest_root=tmp_path / "managed",
            rel_path=Path("myfile.txt"),
            dry_run=False,
            force=False,
            context=None,
        )

        result = op.run()

        assert result.exit_code == 0
        assert not (plain_dir / ".git").exists(), ".git dir should not be created"
        assert result.git_exclude is None
        assert result.git_exclude_name is None

    def test_restore_operation_context_none_returns_zero_without_error(self, tmp_path: Path) -> None:
        """RestoreOperation git-exclude collection is empty when context is None.

        Source is placed in a plain directory (no .git) so that ``is_git_repo``
        returns ``False`` regardless of whether the ``context is None`` guard
        is present.  This exercises the observable contract: when context is
        None, the step always exits cleanly and no exclude entry is recorded.

        Requirements: 3.4
        """
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        source = plain_dir / "myfile.txt"
        source.write_text("hello")
        dest_root = tmp_path / "managed"
        dest_root.mkdir()
        (dest_root / "myfile.txt").write_text("hello")

        result = RestoreOperation(
            source=source,
            dest_root=dest_root,
            rel_path=Path("myfile.txt"),
            dry_run=False,
            context=None,  # explicitly None
        ).run()

        assert result.exit_code == 0
        assert not (plain_dir / ".git").exists(), ".git dir should not be created"
        assert result.git_excludes == ()
