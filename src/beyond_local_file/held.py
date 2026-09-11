"""Held copies: reserved attic under the managed project."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

HELD_DIR = ".blf-held"
REASON_CREATE_OVERWRITE = "create-overwrite"
REASON_DELETE_GAP = "delete-gap"
_CONTENT_NAME = "content"
_META_NAME = "reason.yml"


@dataclass(frozen=True)
class HeldCopy:
    """One held-copy slot under ``.blf-held/``."""

    slot: Path
    reason: str
    path: str
    replica: str
    clause: str


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
    (slot / _META_NAME).write_text(yaml.safe_dump(meta, sort_keys=True, width=120), encoding="utf-8")
    return slot


def list_held_copies(managed_root: Path) -> tuple[HeldCopy, ...]:
    """Return held copies stored under ``.blf-held/`` in *managed_root*.

    Args:
        managed_root: Managed project directory.

    Returns:
        Held copies in slot-name order, each carrying the hold-reason clause.
    """
    root = managed_root / HELD_DIR
    if not root.is_dir():
        return ()
    copies: list[HeldCopy] = []
    for slot in sorted(root.iterdir(), key=lambda path: path.name):
        if not slot.is_dir():
            continue
        meta_path = slot / _META_NAME
        if not meta_path.is_file():
            continue
        try:
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(meta, dict):
            continue
        reason = str(meta.get("reason") or "")
        path = str(meta.get("path") or "")
        replica = str(meta.get("replica") or "")
        stored = str(meta.get("clause") or "")
        clause = stored or reason_clause(reason, path=path, replica=replica)
        copies.append(HeldCopy(slot=slot, reason=reason, path=path, replica=replica, clause=clause))
    return tuple(copies)
