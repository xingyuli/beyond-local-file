"""Held copies: reserved attic under the managed project."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import yaml

HELD_DIR = ".blf-held"
REASON_CREATE_OVERWRITE = "create-overwrite"
REASON_DELETE_GAP = "delete-gap"
_CONTENT_NAME = "content"
_META_NAME = "reason.yml"


def is_held_item_name(name: str) -> bool:
    """Return whether *name* is the reserved held-copy directory.

    Args:
        name: A top-level item name in a managed project.

    Returns:
        ``True`` if the name must not be projected.
    """
    return name == HELD_DIR


def reason_clause(reason: str, *, path: str, replica: str) -> str:
    """Return the human clause for a hold reason.

    Args:
        reason: Stable hold-reason id.
        path: Relative path of the item.
        replica: Target project that owned the held bytes.

    Returns:
        Text for WARNINGs and the later resolve UI.
    """
    if reason == REASON_CREATE_OVERWRITE:
        return f"revlink create replaced different bytes at {path} in {replica} (reason: {reason})"
    if reason == REASON_DELETE_GAP:
        return f"delete applied past the generation window; kept hub bytes of {path} (reason: {reason})"
    return f"{reason}: {path} from {replica}"


def store_held_copy(
    managed_root: Path,
    *,
    rel_path: Path,
    source: Path,
    replica: Path,
    reason: str,
) -> Path:
    """Move *source* into ``.blf-held/`` and write reason metadata.

    Args:
        managed_root: Managed project directory.
        rel_path: Item path relative to the replica root.
        source: File or directory to hold (usually on the replica).
        replica: Replica that owned *source*.
        reason: Hold-reason id.

    Returns:
        Path to the held slot directory.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    safe = rel_path.as_posix().replace("/", "--")
    slot = managed_root / HELD_DIR / f"{stamp}_{safe}"
    slot.mkdir(parents=True)
    content = slot / _CONTENT_NAME
    shutil.move(str(source), str(content))
    meta = {
        "reason": reason,
        "path": rel_path.as_posix(),
        "replica": replica.as_posix(),
        "clause": reason_clause(reason, path=rel_path.as_posix(), replica=replica.as_posix()),
    }
    (slot / _META_NAME).write_text(yaml.safe_dump(meta, sort_keys=True), encoding="utf-8")
    return slot
