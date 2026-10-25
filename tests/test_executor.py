from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tidyfolder.executor import apply_plan
from tidyfolder.planner import build_plan
from tidyfolder.rules import load_rules


def _plan_for(tmp_path: Path):
    return build_plan(tmp_path, load_rules(None), tmp_path / "archive")


def test_apply_backs_up_then_moves(tmp_path):
    source = tmp_path / "report.pdf"
    source.write_bytes(b"pdf data")
    plan = _plan_for(tmp_path)
    backup_root = tmp_path / "archive" / ".backup"
    undo_log = tmp_path / "tidy-undo.json"

    entries = apply_plan(plan, backup_root, undo_log)

    assert not source.exists()
    dest = next(iter(entries))["dest"]
    assert Path(dest).read_bytes() == b"pdf data"
    backups = list(backup_root.iterdir())
    assert len(backups) == 1 and backups[0].read_bytes() == b"pdf data"


def test_apply_writes_valid_incremental_undo_log(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"a")
    (tmp_path / "b.pdf").write_bytes(b"b")
    plan = _plan_for(tmp_path)
    undo_log = tmp_path / "tidy-undo.json"

    entries = apply_plan(plan, tmp_path / "archive" / ".backup", undo_log)
    assert len(entries) == 2
    payload = json.loads(undo_log.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert [e["dest"] for e in payload["entries"]] == [e["dest"] for e in entries]


def test_nothing_is_ever_deleted(tmp_path):
    originals = ["a.pdf", "b.jpg", "c.wav", "d.bin", "e.txt"]
    for name in originals:
        (tmp_path / name).write_bytes(name.encode())
    plan = _plan_for(tmp_path)
    apply_plan(plan, tmp_path / "archive" / ".backup", tmp_path / "tidy-undo.json")

    top_level = {p.name for p in tmp_path.iterdir()}
    all_files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert "archive" in top_level and "tidy-undo.json" in top_level
    assert len(all_files) == len(originals) * 2 + 1  # moved + backups + undo log; nothing deleted
    for name in originals:
        assert list(tmp_path.rglob(name)), f"{name} must still exist somewhere"


def test_collision_gets_uniqified_not_overwritten(tmp_path):
    first = tmp_path / "dupe.txt"
    first.write_text("old", encoding="utf-8")
    (tmp_path / "archive" / "text-files").mkdir(parents=True)
    (tmp_path / "archive" / "text-files" / "dupe.txt").write_text("already there", encoding="utf-8")

    plan = _plan_for(tmp_path)
    del plan.moves[:]
    from tidyfolder.planner import Move

    plan.moves.append(Move(source=first, rel_name="dupe.txt",
                           dest_dir=tmp_path / "archive" / "text-files", reason="test"))
    entries = apply_plan(plan, None, tmp_path / "undo.json")
    moved_to = entries[0]["dest"]
    assert Path(moved_to).name == "dupe-1.txt"
    assert Path(moved_to).read_text(encoding="utf-8") == "old"
    assert (tmp_path / "archive" / "text-files" / "dupe.txt").read_text(encoding="utf-8") == "already there"


def test_backup_failure_leaves_original_untouched(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("precious", encoding="utf-8")
    plan = _plan_for(tmp_path)
    backup_root = tmp_path / "nope" / "backup"
    with pytest.raises((OSError, PermissionError)):
        with pytest.MonkeyPatch.context() as monkey:
            monkey.setattr("shutil.copy2", _raiser)
            apply_plan(plan, backup_root, tmp_path / "undo.json")
    assert f.read_text(encoding="utf-8") == "precious"


def _raiser(*args, **kwargs):
    raise PermissionError("backup device full")


def test_move_across_filesystems_falls_back_to_copy(tmp_path, monkeypatch):
    import errno

    f = tmp_path / "big.bin"
    f.write_bytes(b"data")
    plan = _plan_for(tmp_path)
    real_replace = os.replace

    def exdev(src, dst):
        if "archive" in str(dst):
            raise OSError(errno.EXDEV, "cross-device link")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", exdev)
    entries = apply_plan(plan, None, tmp_path / "undo.json")
    assert Path(entries[0]["dest"]).read_bytes() == b"data"
    assert not f.exists()


def test_plan_with_no_moves_is_a_noop(tmp_path):
    (tmp_path / "archive").mkdir()
    plan = _plan_for(tmp_path)  # only archive/ and hidden checks; nothing top-level
    entries = apply_plan(plan, None, tmp_path / "undo.json")
    assert entries == []
