"""Executor: backup-then-move each planned file. Never deletes anything."""

from __future__ import annotations

import errno
import os
import shutil
from pathlib import Path

from .planner import Plan
from .undolog import new_entry, save


def apply_plan(plan: Plan, backup_root: Path | None, undo_log: Path) -> list[dict]:
    """Apply every move in the plan. Back up (copy) first, then move.

    Returns the undo-log entries. The log is rewritten after each completed
    move so a crash mid-run still leaves a usable record.
    """
    entries: list[dict] = []
    if backup_root is not None:
        backup_root.mkdir(parents=True, exist_ok=True)
    for move in plan.moves:
        move.dest_dir.mkdir(parents=True, exist_ok=True)
        dest = _unique_destination(move.dest_dir / move.source.name)
        backup: Path | None = None
        if backup_root is not None:
            backup = backup_root / f"{len(entries) + 1:04d}__{move.source.name}"
            shutil.copy2(move.source, backup)  # backup BEFORE touching the original
        _move_file(move.source, dest)  # never deletes; the source reappears at |dest|
        entries.append(new_entry(move.source, dest, backup))
        save(undo_log, entries)
    return entries


def _move_file(source: Path, dest: Path) -> None:
    try:
        os.replace(source, dest)
    except OSError as exc:
        if exc.errno == errno.EXDEV:  # archive on a different filesystem
            shutil.copy2(source, dest)
            os.unlink(source)
        else:
            raise


def _unique_destination(candidate: Path) -> Path:
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    for n in range(1, 10_000):
        alt = candidate.with_name(f"{stem}-{n}{suffix}")
        if not alt.exists():
            return alt
    raise OSError(f"could not find a free name near {candidate}")
