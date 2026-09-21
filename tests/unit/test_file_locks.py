"""Concurrent splices of a shared mapping yaml or git exclude stay valid."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
import yaml

from beyond_local_file.config import ConfigUpdater
from beyond_local_file.git_manager import GitExcludeManager


def test_concurrent_subpath_splices_keep_both_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two worker units splicing the same mapping yaml must not drop an entry."""
    alpha_target = tmp_path / "lab-app"
    beta_target = tmp_path / "lab-notes"
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        f"alpha:\n  target: {alpha_target}\n  subpath: []\n"
        f"beta:\n  target: {beta_target}\n  subpath: []\n"
    )
    original_write = Path.write_text

    def delayed_write(self: Path, data: str, **kwargs: object) -> int:
        if self.resolve() == config_path.resolve():
            time.sleep(0.05)
        return original_write(self, data, **kwargs)

    monkeypatch.setattr(Path, "write_text", delayed_write)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def add(project: str, target: Path, entry: str) -> None:
        try:
            barrier.wait()
            ConfigUpdater(config_path).add_subpath_entry(project, target, entry)
        except BaseException as error:
            errors.append(error)

    threads = [
        threading.Thread(target=add, args=("alpha", alpha_target, "one.txt")),
        threading.Thread(target=add, args=("beta", beta_target, "two.txt")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "one.txt" in (data["alpha"]["subpath"] or [])
    assert "two.txt" in (data["beta"]["subpath"] or [])


def test_concurrent_exclude_removes_keep_a_valid_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two worker units splicing the same git exclude must not restore a removed line."""
    repo = tmp_path / "lab-app"
    exclude = repo / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True)
    exclude.write_text("one.txt\ntwo.txt\n")
    original_write = Path.write_text

    def delayed_write(self: Path, data: str, **kwargs: object) -> int:
        if self.resolve() == exclude.resolve():
            time.sleep(0.05)
        return original_write(self, data, **kwargs)

    monkeypatch.setattr(Path, "write_text", delayed_write)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def remove(entry: str) -> None:
        try:
            barrier.wait()
            GitExcludeManager(repo).remove_entries({entry})
        except BaseException as error:
            errors.append(error)

    threads = [
        threading.Thread(target=remove, args=("one.txt",)),
        threading.Thread(target=remove, args=("two.txt",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    remaining = {line for line in exclude.read_text().splitlines() if line.strip()}
    assert remaining == set()
