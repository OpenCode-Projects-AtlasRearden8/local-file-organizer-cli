from __future__ import annotations

import os
from pathlib import Path

import pytest

from tidyfolder.planner import build_plan
from tidyfolder.rules import load_rules


def make_mess(tmp_path: Path) -> None:
    (tmp_path / "IMG_0001.jpg").write_bytes(b"j")
    (tmp_path / "report.pdf").write_bytes(b"p")
    (tmp_path / "sales.csv").write_bytes(b"c")
    (tmp_path / "randomthing.bin").write_bytes(b"b")
    (tmp_path / "tidy-undo.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".hidden").write_text("h", encoding="utf-8")
    (tmp_path / "tidy-rules.toml").write_text("", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "archive").mkdir()
    (tmp_path / "archive" / "already-here.txt").write_text("x", encoding="utf-8")


def test_plan_moves_only_top_level_files_into_archive(tmp_path):
    make_mess(tmp_path)
    plan = build_plan(tmp_path, load_rules(None), tmp_path / "archive",
                      protected=[tmp_path / "tidy-undo.json", tmp_path / "tidy-rules.toml"])
    names = {m.source.name for m in plan.moves}
    assert names == {"IMG_0001.jpg", "report.pdf", "sales.csv", "randomthing.bin"}
    skipped = {p.name: why for p, why in plan.skipped}
    assert "tidy-undo.json" in skipped
    assert ".hidden" in skipped
    assert "tidy-rules.toml" in skipped
    assert "archive" in skipped


def test_destinations_sit_under_archive_path(tmp_path):
    make_mess(tmp_path)
    archive = tmp_path / "archive"
    plan = build_plan(tmp_path, load_rules(None), archive)
    for move in plan.moves:
        rel = move.dest_dir.relative_to(archive)
        assert rel.parts, "dest must be inside the archive"
        assert ".." not in rel.parts


def test_date_pattern_catch_all_uses_mtime(tmp_path):
    f = tmp_path / "randomthing"
    f.write_bytes(b"x")
    stamp = f.stat().st_mtime
    plan = build_plan(tmp_path, load_rules(None), tmp_path / "archive")
    target = next(m for m in plan.moves if m.source == f)
    dest = target.dest_dir.relative_to(tmp_path / "archive")
    parts = dest.parts
    assert parts[0] == "misc"
    assert parts[1].startswith("20")


def test_suggestions_replace_fallback_destination(tmp_path):
    f = tmp_path / "weirdfile.xyz"
    f.write_bytes(b"x")
    plan = build_plan(
        tmp_path,
        load_rules(None),
        tmp_path / "archive",
        suggestions={"weirdfile.xyz": "projects/book-drafts"},
    )
    move = plan.moves[0]
    assert move.dest_dir == tmp_path / "archive" / "projects/book-drafts"
    assert move.is_suggestion


def test_plan_is_deterministic_and_sorted(tmp_path):
    make_mess(tmp_path)
    plan_a = build_plan(tmp_path, load_rules(None), tmp_path / "archive")
    plan_b = build_plan(tmp_path, load_rules(None), tmp_path / "archive")
    assert [m.source for m in plan_a.moves] == [m.source for m in plan_b.moves]


def test_planning_does_not_touch_filesystem(tmp_path):
    make_mess(tmp_path)
    before = {p.name: p.stat().st_mtime for p in tmp_path.rglob("*")}
    build_plan(tmp_path, load_rules(None), tmp_path / "archive")
    after = {p.name: p.stat().st_mtime for p in tmp_path.rglob("*")}
    assert before == after
