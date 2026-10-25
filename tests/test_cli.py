from __future__ import annotations

import json
from pathlib import Path

import pytest

from tidyfolder import cli
from tidyfolder.rules import DEFAULT_RULES_TOML


def make_mess(tmp_path: Path) -> None:
    (tmp_path / "IMG_0001.jpg").write_bytes(b"j")
    (tmp_path / "report.pdf").write_bytes(b"p")
    (tmp_path / "leftover").write_bytes(b"b")


def test_dry_run_is_the_default_and_changes_nothing(tmp_path, capsys):
    make_mess(tmp_path)
    code = cli.main(["sort", str(tmp_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Dry run only" in out
    assert "WOULD MOVE" in out
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "IMG_0001.jpg", "leftover", "report.pdf"
    ]
    assert "report.pdf  ->  archive/documents/report.pdf" in out


def test_apply_with_yes_moves_into_archive(tmp_path, capsys):
    make_mess(tmp_path)
    code = cli.main(["sort", str(tmp_path), "--apply", "--yes"])
    assert code == 0
    assert (tmp_path / "archive" / "documents" / "report.pdf").is_file()
    assert (tmp_path / "archive" / "images" / "IMG_0001.jpg").is_file()
    assert (tmp_path / "archive" / "misc").is_dir()
    backups = list((tmp_path / "archive" / ".backup").iterdir())
    assert len(backups) == 3
    undo_log = tmp_path / "tidy-undo.json"
    assert json.loads(undo_log.read_text(encoding="utf-8"))["version"] == 1
    capsys.readouterr()


def test_apply_without_yes_in_noninteractive_shell_is_refused(tmp_path, capsys):
    make_mess(tmp_path)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("sys.stdin", open("/dev/null"))
        code = cli.main(["sort", str(tmp_path), "--apply"])
    assert code == 2
    assert "not interactive" in capsys.readouterr().err
    assert (tmp_path / "report.pdf").is_file()


def test_apply_deletion_is_impossible_by_design(tmp_path):
    make_mess(tmp_path)
    cli.main(["sort", str(tmp_path), "--apply", "--yes"])
    before = len([p for p in tmp_path.rglob("*") if p.is_file()])
    cli.main(["undo", str(tmp_path / "tidy-undo.json"), "--yes"])
    after = len([p for p in tmp_path.rglob("*") if p.is_file()])
    assert (tmp_path / "report.pdf").is_file()
    assert after == before
    # Undo moves files back; it must never delete anything.
    leftovers = [p.name for p in tmp_path.iterdir()]
    assert "archive" in leftovers and "tidy-undo.json" in leftovers


def test_second_sort_after_apply_moves_nothing_new(tmp_path):
    make_mess(tmp_path)
    cli.main(["sort", str(tmp_path), "--apply", "--yes"])
    undo = tmp_path / "tidy-undo.json"
    assert undo.is_file()
    entries_after_first_apply = undo.read_text(encoding="utf-8")
    cli.main(["sort", str(tmp_path), "--apply", "--yes"])  # already clean
    assert undo.read_text(encoding="utf-8") == entries_after_first_apply


def test_custom_rules_file(tmp_path):
    make_mess(tmp_path)
    rules = tmp_path / "custom-rules.toml"
    rules.write_text('[[rule]]\nname = "*.pdf"\ndest = "contraband"\n', encoding="utf-8")
    code = cli.main(
        ["sort", str(tmp_path), "--rules", str(rules), "--apply", "--yes",
         "--undo-log", str(tmp_path / "custom-undo.json"), "--archive", str(tmp_path / "shelf")]
    )
    assert code == 0
    assert (tmp_path / "shelf" / "contraband" / "report.pdf").is_file()
    (tmp_path / "shelf" / "contraband" / "report.pdf").unlink
    assert (tmp_path / "report.pdf").exists() is False


def test_undo_command_restores(tmp_path, capsys):
    make_mess(tmp_path)
    cli.main(["sort", str(tmp_path), "--apply", "--yes"])
    code = cli.main(["undo", str(tmp_path / "tidy-undo.json"), "--yes"])
    assert code == 0
    out = capsys.readouterr().out
    assert "restored: report.pdf" in out
    assert (tmp_path / "report.pdf").is_file()
    assert (tmp_path / "IMG_0001.jpg").is_file()
    assert not any((tmp_path / "archive" / "documents").iterdir())  # undo never deletes; dir is empty


def test_init_writes_starter_rules(tmp_path):
    code = cli.main(["init", str(tmp_path / "tidy-rules.toml")])
    assert code == 0
    assert (tmp_path / "tidy-rules.toml").read_text(encoding="utf-8").startswith(
        "# tidyfolder rules"
    )
    code2 = cli.main(["init", str(tmp_path / "tidy-rules.toml")])
    assert code2 == 1


def test_init_default_rules_are_built_in_stdlib(tmp_path):
    (tmp_path / "tidy-rules.toml").write_text(DEFAULT_RULES_TOML, encoding="utf-8")


def test_sort_missing_folder_returns_error(tmp_path, capsys):
    code = cli.main(["sort", str(tmp_path / "nope")])
    assert code == 2
    assert "not a folder" in capsys.readouterr().err


def test_bad_rules_file_reported_cleanly(tmp_path):
    make_mess(tmp_path)
    rules = tmp_path / "broken.toml"
    rules.write_text('[[rule]]\ndest = 42\n', encoding="utf-8")
    code = cli.main(["sort", str(tmp_path), "--rules", str(rules)])
    assert code == 1


def test_suggest_with_no_local_server_falls_back_gracefully(tmp_path, capsys, monkeypatch):
    make_mess(tmp_path)
    monkeypatch.setattr(cli.llm, "chat_suggest", _boom)
    code = cli.main(["sort", str(tmp_path), "--suggest", "--apply", "--yes"])
    assert code == 0
    assert "LLM suggestions unavailable" in capsys.readouterr().err
    assert (tmp_path / "leftover").exists() is False


def _boom(*args, **kwargs):
    raise ConnectionError("no local model running")


def test_apply_honors_explicit_archive_backup_and_undo_paths(tmp_path):
    make_mess(tmp_path)
    code = cli.main(
        [
            "sort", str(tmp_path),
            "--archive", str(tmp_path / "tucked-away"),
            "--backup", str(tmp_path / "tucked-away" / ".backup"),
            "--undo-log", str(tmp_path / "my-undo.json"),
            "--apply", "--yes",
        ]
    )
    assert code == 0
    assert (tmp_path / "tucked-away" / "documents" / "report.pdf").is_file()
    assert (tmp_path / "my-undo.json").is_file()


def test_never_touches_files_outside_target(tmp_path):
    make_mess(tmp_path)
    neighbor = tmp_path.parent
    sentinel = neighbor / "sentinel.txt"
    sentinel.write_text("do not touch", encoding="utf-8")
    cli.main(["sort", str(tmp_path), "--apply", "--yes"])
    assert sentinel.read_text(encoding="utf-8") == "do not touch"


def _fake_terminal(monkeypatch):
    monkeypatch.setattr(cli, "_human_terminal", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(_FAKE_INPUT))


_FAKE_INPUT = iter([])


def test_suggestions_confirmed_and_applied_when_accepted(tmp_path, monkeypatch):
    (tmp_path / "mystery").write_bytes(b"x")
    monkeypatch.setattr(cli.llm, "chat_suggest",
                   lambda *a, **k: {"mystery": "projects/book-drafts"})
    _FAKE_INPUT = iter(["y", "y"])
    monkeypatch.setattr(cli, "_human_terminal", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(_FAKE_INPUT))
    assert cli.main(["sort", str(tmp_path), "--suggest", "--apply"]) == 0
    assert (tmp_path / "archive" / "projects" / "book-drafts" / "mystery").is_file()


def test_suggestions_declined_fall_back_to_rule_dest(tmp_path, monkeypatch):
    (tmp_path / "mystery").write_bytes(b"x")
    monkeypatch.setattr(cli.llm, "chat_suggest",
                   lambda *a, **k: {"mystery": "jailhouse/rock"})
    _FAKE_INPUT = iter(["n", "y"])  # decline suggestion, confirm apply
    monkeypatch.setattr(cli, "_human_terminal", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(_FAKE_INPUT))
    assert cli.main(["sort", str(tmp_path), "--suggest", "--apply"]) == 0
    assert (tmp_path / "archive" / "projects" / "jailhouse").exists() is False
    assert (tmp_path / "archive" / "misc").is_dir()
