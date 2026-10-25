"""Optional LLM suggestions via any OpenAI-compatible endpoint.

Defaults to a local Ollama server (http://localhost:11434/v1). No API key is
ever requested, stored, or sent: the tool only ever talks to a local endpoint.
Only file *names* are sent, never file contents.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

DEFAULT_API_BASE_ENV = "TIDYFOLDER_API_BASE"
DEFAULT_API_BASE = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.2"

SYSTEM_PROMPT = (
    "You organize files by proposing folder names. Reply with ONLY a JSON object "
    "mapping each filename to a short kebab-case subfolder path (max 2 levels). "
    "Never use absolute paths or '..'."
)

from .rules import sanitize_relpath


def default_api_base() -> str:
    import os

    return os.environ.get(DEFAULT_API_BASE_ENV, DEFAULT_API_BASE)


def chat_suggest(api_base: str, model: str, filenames: list[str], timeout: float = 60.0,
                 post=None) -> dict[str, str]:
    """Ask the model for a folder suggestion per file. Returns name -> folder."""
    if not filenames:
        return {}
    post = post or _post
    content = post(api_base, model, filenames, timeout)
    return parse_suggestions(content, set(filenames))


def _post(api_base: str, model: str, filenames: list[str], timeout: float) -> str:
    url = api_base.rstrip("/").removesuffix("/chat/completions") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Propose a subfolder for each file. Files: "
                    f"{json.dumps(filenames)}\n"
                    'Respond with JSON like {"file.pdf": "projects/book-drafts"}.'
                ),
            },
        ],
        "temperature": 0,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


def parse_suggestions(content: str, valid_names: set[str]) -> dict[str, str]:
    """Parse model output into a safe name -> folder map. Invalid entries are dropped."""
    raw = _strip_code_fence(content)
    try:
        mapping = json.loads(_extract_json(raw))
    except (json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(mapping, dict):
        return {}
    result: dict[str, str] = {}
    for name, folder in mapping.items():
        if not isinstance(name, str) or not isinstance(folder, str):
            continue
        if name not in valid_names:
            continue
        try:
            result[name] = sanitize_relpath(folder) if folder else _reject(folder)
        except ValueError:
            continue
    return result


def _reject(folder):
    raise ValueError(folder)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _extract_json(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found")
    return text[start : end + 1]


def limit_filenames(names: list[str], limit: int) -> list[str]:
    return sorted(names)[: max(limit, 0)]
