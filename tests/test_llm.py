from __future__ import annotations

import unittest.mock as mock

import pytest

from tidyfolder import llm
from tidyfolder.rules import sanitize_relpath


def test_default_api_base_is_local_ollama():
    with mock.patch.dict("os.environ", {}, clear=True):
        assert llm.default_api_base() == "http://localhost:11434/v1"


def test_env_var_can_override_api_base():
    with mock.patch.dict(
        "os.environ", {"TIDYFOLDER_API_BASE": "http://127.0.0.1:9999/v1"}
    ):
        assert llm.default_api_base() == "http://127.0.0.1:9999/v1"


def test_parses_plain_json_and_keeps_known_names():
    content = '{"report.pdf": "projects", "IMG_1.jpg": "photos"}'
    result = llm.parse_suggestions(content, {"report.pdf", "IMG_1.jpg", "other.pdf"})
    assert result == {"report.pdf": "projects", "IMG_1.jpg": "photos"}


def test_parses_code_fenced_json():
    content = '```json\n{"report.pdf": "docs"}\n```'
    assert llm.parse_suggestions(content, {"report.pdf"}) == {"report.pdf": "docs"}


def test_parses_json_surrounded_by_chatter():
    content = 'Sure! Here you go: {"a.pdf": "x"} hope that helps'
    assert llm.parse_suggestions(content, {"a.pdf"}) == {"a.pdf": "x"}


def test_rejects_unknown_filenames():
    assert llm.parse_suggestions('{"evil.txt": "jail"}', {"report.pdf"}) == {}


def test_drops_unsafe_paths():
    assert llm.parse_suggestions('{"a.pdf": "..", "b.pdf": "/etc"}', {"a.pdf", "b.pdf"}) == {}
    assert llm.parse_suggestions('{"a.pdf": "  Docs/2024  "}', {"a.pdf"}) == {"a.pdf": "Docs/2024"}


def test_handles_non_json_and_hd_empty_response():
    assert llm.parse_suggestions("", {"a.pdf"}) == {}
    assert llm.parse_suggestions("I cannot help with that", {"a.pdf"}) == {}
    assert llm.parse_suggestions("[1, 2]", {"a.pdf"}) == {}


def test_chat_suggest_posts_minimal_payload_without_any_key():
    captured = {}

    def fake_post(api_base, model, filenames, timeout):
        captured["base"] = api_base
        captured["model"] = model
        captured["names"] = filenames
        return '{"report.pdf": "reports"}'

    with mock.patch.object(llm, "_post", side_effect=fake_post):
        result = llm.chat_suggest("http://localhost:11434/v1", "llama3.2", ["report.pdf"])

    assert result == {"report.pdf": "reports"}
    assert captured["base"] == "http://localhost:11434/v1"
    assert captured["names"] == ["report.pdf"]


def test_chat_suggest_empty_input_makes_no_request():
    assert llm.chat_suggest("http://localhost:11434/v1", "m", []) == {}


def test_limit_filenames_caps_and_sorts(tmp_path):
    names = ["z.txt", "a.txt", "m.txt"]
    assert llm.limit_filenames(names, 2) == ["a.txt", "m.txt"]
    assert llm.limit_filenames(names, 0) == []
    paths = [tmp_path / n for n in names]
    assert [p.name for p in paths] != sorted([p.name for p in paths])


def test_sanitize_helpers_still_strict():
    with pytest.raises(ValueError):
        sanitize_relpath("")
