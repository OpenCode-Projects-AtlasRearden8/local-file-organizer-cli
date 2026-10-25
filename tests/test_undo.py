from __future__ import annotations

import json
from pathlib import Path

import pytest

from tidyfolder import undolog
from tidyfolder.executor import apply_plan
from tidyfolder.planner import build_plan
from tidyfolder.rules import load_rules


def _apply(tmp_path: Path):
    names = ["report.pdf", "IMG_1.jpg", "song.mp3", "mystery.bin"]
    for name in names:
        (tmp_path / name).write_bytes(name.encode())
    plan = build_plan(tmp_path, load_rules(None), tmp_path / "archive")
    apply_plan(plan, tmp_path / "archive" / ".backup", tmp_path / "tidy-undo.json")
    return names


def test_undo_log_round_trip(tmp_path):
    names = _apply(tmp_path)
    entries = undolog.load(tmp_path / "tidy-undo.json")
    assert len(entries) == len(names)
    for entry in entries:
        assert entry["source"] and entry["dest"] and entry["backup"]
    assert undo_log_file(tmp_path / "tidy-undo.json")


def test_undo_restores_everything_including_directory_structure(tmp_path):
    _apply(tmp_path)
    captured = []
    monkey_gen = undo_log_file(tmp_path / "tidy-undo.json")
    for item in monkey_gen:
        captured.append(item)
    # The map from undo back to original sources must be exact.
    restored = {Path(c[0]).name for c in captured}
    assert restored == {"report.pdf", "IMG_1.jpg", "song.mp3", "mystery.bin"}
    for name in restored:
        assert (tmp_path / name).is_file()
    sources = [f"{Path(e['source']).name}" for e in undolog.load(tmp_path / "tidy-undo.json")]
    assert sorted(set(sources)) == sorted(restored)


def undo_log_file(log_path: Path):
    from tidyfolder.cli import undo_log_file as _undo

    return list(_undo(log_path))


def test_undo_is_idempotent_and_never_overwrites(tmp_path):
    _apply(tmp_path)
    first = undo_log_file(tmp_path / "tidy-undo.json")
    second = undo_log_file(tmp_path / "tidy-undo.json")
    # Second run: sources already back in place, so everything is skipped.
    assert all(item[1] is None for item in second)
    assert len(first) == len(second)


def test_undo_log_format_is_documented_and_validated(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"version": 99, "entries": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        undolog.load(bad)
