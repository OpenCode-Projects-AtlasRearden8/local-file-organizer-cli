from __future__ import annotations

from pathlib import Path

import pytest

from tidyfolder.rules import (
    DEFAULT_RULES_TOML,
    Rule,
    RuleError,
    first_matching_rule,
    load_rules,
    parse_dest_template,
    parse_rules,
    sanitize_relpath,
)


def test_default_rules_load_and_first_match_wins():
    rules = load_rules(None)
    assert rules, "built-in defaults must exist"
    assert first_matching_rule(rules, "IMG_0001.jpg").dest == "images"
    assert first_matching_rule(rules, "report.PDF").dest == "documents"
    assert first_matching_rule(rules, "notes.txt").dest == "documents"


def test_catch_all_rule_matches_anything():
    rules = parse_rules(DEFAULT_RULES_TOML)
    catch_all = rules[-1]
    assert catch_all.matches("anything")


def test_extension_rule_and_template_vars():
    rules = parse_rules(
        """
[[rule]]
ext = "csv"
dest = "data"

[[rule]]
dest = "misc/{ext}"
"""
    )
    rule = first_matching_rule(rules, "sales.CSV")
    assert rule.dest == "data"
    fallback = Rule(dest="misc/{ext}")
    assert parse_dest_template(fallback.dest, "notes.MD", 0.0) == "misc/md"


def test_fallbackmisc_template_with_date_vars(tmp_path):
    import os

    f = tmp_path / "mystery.bin"
    f.write_bytes(b"x")
    mtime = os.path.getmtime(f)
    out = parse_dest_template("misc/{year}/{year_month}", f.name, mtime)
    assert out.startswith("misc/20") and out.count("/") == 2


def test_case_insensitive_glob_matching():
    rule = Rule(name_patterns=["*.JPG"], dest="images")
    assert rule.matches("photo.jpg")
    assert not rule.matches("photo.png")


def test_ext_rule_is_case_insensitive():
    rule = Rule(exts=["PDF"], dest="documents")
    assert rule.matches("thing.pdf")


def test_rule_with_neither_matcher_is_catch_all():
    assert Rule(dest="misc").matches("random.bin")


def test_parse_rejects_bad_dest():
    with pytest.raises(RuleError):
        parse_rules('[[rule]]\ndest = ""\n')
    with pytest.raises(RuleError):
        parse_rules('[[rule]]\ndest = 42\n')
    with pytest.raises(RuleError):
        parse_rules('rule = "nope"\n')


def test_load_rules_from_file(tmp_path):
    f = tmp_path / "rules.toml"
    f.write_text('[[rule]]\nname = "*.kdbx"\ndest = "passwords"\n', encoding="utf-8")
    rules = load_rules(f)
    assert first_matching_rule(rules, "vault.kdbx").dest == "passwords"


def test_load_rules_missing_file_raises(tmp_path):
    with pytest.raises(RuleError):
        load_rules(tmp_path / "nope.toml")


def test_sanitize_relpath_allows_and_blocks():
    assert sanitize_relpath("  docs / 2024  ") == "docs/2024"
    assert sanitize_relpath("projects\\book-drafts") == "projects/book-drafts"
    with pytest.raises(ValueError):
        sanitize_relpath("/absolute")
    with pytest.raises(ValueError):
        sanitize_relpath("../escape")
    with pytest.raises(ValueError):
        sanitize_relpath("a/../../b")
    with pytest.raises(ValueError):
        sanitize_relpath("C:\\evil")
    with pytest.raises(ValueError):
        sanitize_relpath("   ")
