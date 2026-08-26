"""Property-based tests for ChecksumVerifier.

This module contains property-based tests that verify the correctness of
``ChecksumVerifier.compute`` across a wide range of generated directory trees.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from beyond_local_file.operations.revlink import ChecksumVerifier
from tests.path_strategies import is_safe_fs_name

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate safe filename components: alphanumeric plus hyphens, underscores,
# and dots. Filter out empty strings, path separators, null bytes, "." / "..",
# and Windows reserved device names (NUL, COM1, …).
_filename = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="-_.",
    ),
    min_size=1,
    max_size=30,
).filter(is_safe_fs_name)

# A flat list of (filename, content) pairs for building a directory tree.
# unique_by on filename avoids duplicate filenames in the same directory.
_file_entries = st.lists(
    st.tuples(_filename, st.binary()),
    min_size=0,
    max_size=10,
    unique_by=lambda entry: entry[0],
)


def _write_file_tree(root: Path, entries: list[tuple[str, bytes]]) -> None:
    """Write a flat list of (filename, content) entries into *root*.

    Args:
        root: Directory to write files into. Must already exist.
        entries: List of (filename, content) pairs to create.
    """
    for filename, content in entries:
        (root / filename).write_bytes(content)


# ---------------------------------------------------------------------------
# Property 4: Checksum verifier is deterministic for directory trees
# ---------------------------------------------------------------------------


# Feature: revlink, Property 4: Checksum verifier is deterministic for directory trees
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(entries=_file_entries)
def test_checksum_verifier_is_deterministic(
    tmp_path: Path,
    entries: list[tuple[str, bytes]],
) -> None:
    """Verify that ChecksumVerifier.compute returns the same digest on two consecutive calls.

    **Validates: Requirements 4.6**

    For any directory tree, calling ``ChecksumVerifier.compute`` twice on the
    same tree must produce identical hex digests. This confirms the verifier
    is deterministic and independent of filesystem traversal order.

    The ``tmp_path`` fixture is reused across Hypothesis examples; each
    example uses a fresh subdirectory so earlier examples do not interfere
    with later ones.

    Args:
        tmp_path: Pytest-provided temporary directory (shared across examples
            within a single test run).
        entries: List of ``(filename, content)`` pairs used to populate the
            directory tree under a fresh subdirectory of ``tmp_path``.
    """
    # Use a subdirectory so each example gets an isolated tree.
    tree_root = tmp_path / "tree"
    tree_root.mkdir(exist_ok=True)
    # Clear any files from a previous example to keep the tree isolated.
    for child in list(tree_root.iterdir()):
        child.unlink()

    _write_file_tree(tree_root, entries)

    first = ChecksumVerifier.compute(tree_root)
    second = ChecksumVerifier.compute(tree_root)

    assert first == second, (
        f"ChecksumVerifier.compute returned different digests on consecutive calls: {first!r} != {second!r}"
    )


# ---------------------------------------------------------------------------
# Property 5: Checksum verifier produces matching digests for identical content
# ---------------------------------------------------------------------------


# Feature: revlink, Property 5: Checksum verifier produces matching digests for identical content
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    filename=st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters="-_.",
        ),
        min_size=1,
        max_size=30,
    ).filter(is_safe_fs_name),
    content=st.binary(),
)
def test_checksum_verifier_matches_for_copied_file(
    filename: str,
    content: bytes,
) -> None:
    """Verify that ChecksumVerifier produces identical digests for a file and its copy.

    **Validates: Requirements 4.2, 4.6**

    For any file, ``shutil.copy2`` must produce a byte-for-byte identical copy
    and ``ChecksumVerifier.compute`` must return the same digest for both.

    Args:
        filename: Name of the source file to create.
        content: Raw bytes to write into the source file.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        original = tmp_path / "original" / filename
        original.parent.mkdir(exist_ok=True)
        original.write_bytes(content)

        copy = tmp_path / "copy" / filename
        copy.parent.mkdir(exist_ok=True)
        shutil.copy2(original, copy)

        assert ChecksumVerifier.compute(original) == ChecksumVerifier.compute(copy), (
            f"Digests differ for identical file content: original={original!r}, copy={copy!r}"
        )


# Feature: revlink, Property 5: Checksum verifier produces matching digests for identical content
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(entries=_file_entries)
def test_checksum_verifier_matches_for_copied_directory(
    entries: list[tuple[str, bytes]],
) -> None:
    """Verify that ChecksumVerifier produces identical digests for a directory and its copy.

    **Validates: Requirements 4.2, 4.6**

    For any directory tree, ``shutil.copytree`` must produce a structurally
    identical copy and ``ChecksumVerifier.compute`` must return the same digest
    for both.

    Args:
        entries: List of ``(filename, content)`` pairs used to populate the
            source directory tree.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        original = tmp_path / "original"
        original.mkdir()
        _write_file_tree(original, entries)

        copy = tmp_path / "copy"
        shutil.copytree(original, copy)

        assert ChecksumVerifier.compute(original) == ChecksumVerifier.compute(copy), (
            f"Digests differ for identical directory trees: original={original!r}, copy={copy!r}"
        )
