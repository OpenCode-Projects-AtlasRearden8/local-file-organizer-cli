"""Undo log: records every applied move so it can be reversed."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

LOG_VERSION = 1


def new_entry(source: Path, dest: Path, backup: Path | None) -> dict:
    return {
        "source": str(source.resolve()),
        "dest": str(dest.resolve()),
        "backup": str(backup.resolve()) if backup else None,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def save(log_path: Path, entries: list[dict]) -> None:
    payload = {"version": LOG_VERSION, "entries": entries}
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load(log_path: Path) -> list[dict]:
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != LOG_VERSION:
        raise ValueError(f"unrecognized undo log format in {log_path}")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError(f"undo log has no entries: {log_path}")
    return entries
