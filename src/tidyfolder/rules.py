"""Rules: how files are matched and where they land inside the archive."""

from __future__ import annotations

import fnmatch
import re
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


class RuleError(ValueError):
    """Raised when a rules file is invalid."""


DEFAULT_RULES_TOML = """\
# tidyfolder rules. The FIRST matching rule wins.
# Matchers (both optional; a rule with no matcher is a catch-all):
#   name = "*.pdf"          glob pattern on the file name (case-insensitive)
#   ext  = ["pdf", "docx"]  file extension(s), without the dot
# Destination (template) is a folder inside your archive path. Variables:
#   {ext}  {year}  {month}  {day}  {year_month}  (date/time from the file's mtime)
# Everything ends up inside your archive path. tidyfolder never deletes.

[[rule]]
name = ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp", "*.svg", "*.heic"]
dest = "images"

[[rule]]
name = ["*.pdf", "*.doc", "*.docx", "*.txt", "*.md", "*.rtf", "*.odt"]
dest = "documents"

[[rule]]
name = ["*.xls", "*.xlsx", "*.csv", "*.tsv"]
dest = "spreadsheets"

[[rule]]
name = ["*.mp3", "*.wav", "*.m4a", "*.flac", "*.ogg"]
dest = "audio"

[[rule]]
name = ["*.mp4", "*.mov", "*.mkv", "*.avi", "*.webm"]
dest = "video"

[[rule]]
name = ["*.zip", "*.7z", "*.tar", "*.gz", "*.rar"]
dest = "archives"

[[rule]]
name = ["*.py", "*.js", "*.ts", "*.sh", "*.json", "*.toml", "*.yaml", "*.yml", "*.html", "*.css"]
dest = "code"

[[rule]]
name = "*.*"
dest = "{ext}-files"

[[rule]]
dest = "misc/{year}/{year_month}"
"""


@dataclass
class Rule:
    name_patterns: list[str] = field(default_factory=list)
    exts: list[str] = field(default_factory=list)
    dest: str = "misc"
    description: str = ""

    def matches(self, filename: str) -> bool:
        if not self.name_patterns and not self.exts:
            return True
        low = filename.lower()
        if self.name_patterns and not any(
            fnmatch.fnmatch(low, pat.lower()) for pat in self.name_patterns
        ):
            return False
        if self.exts:
            ext = Path(low).suffix.lstrip(".")
            if ext not in {e.lower().lstrip(".") for e in self.exts}:
                return False
        return True


def _parse_rule_table(raw: dict) -> Rule:
    name = raw.get("name")
    ext = raw.get("ext")
    dest = raw.get("dest", "misc")
    if not isinstance(dest, str) or not dest.strip():
        raise RuleError("rule 'dest' must be a non-empty string")
    if name is None and ext is None:
        pass
    else:
        if name is not None and not isinstance(name, (str, list)):
            raise RuleError("rule 'name' must be a string or list of strings")
        if ext is not None and not isinstance(ext, (str, list)):
            raise RuleError("rule 'ext' must be a string or list of strings")
    description = raw.get("description")
    if description is not None and not isinstance(description, str):
        raise RuleError("rule 'description' must be a string")
    return Rule(
        name_patterns=_as_list(name),
        exts=_as_list(ext),
        dest=dest.strip(),
        description=description or "",
    )


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def parse_rules(text: str) -> list[Rule]:
    data = tomllib.loads(text)
    raw_rules = data.get("rule", [])
    if not isinstance(raw_rules, list):
        raise RuleError("rules file must contain a [[rule]] array")
    return [_parse_rule_table(raw) for raw in raw_rules]


def load_rules(path: Path | None) -> list[Rule]:
    """Load a rules TOML file, or the built-in defaults when path is None."""
    if path is None:
        return parse_rules(DEFAULT_RULES_TOML)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuleError(f"cannot read rules file {path}: {exc}") from exc
    return parse_rules(raw);


def parse_dest_template(template: str, filename: str, mtime: float) -> str:
    folder = Path(filename)
    stamp = datetime.fromtimestamp(mtime)
    subs = {
        "ext": folder.suffix.lstrip(".").lower() or "noext",
        "year": f"{stamp:%Y}",
        "month": f"{stamp:%m}",
        "day": f"{stamp:%d}",
        "year_month": f"{stamp:%Y-%m}",
    }
    result = template
    for key, value in subs.items():
        result = result.replace("{" + key + "}", value)
    return result


_UNSAFE_COMPONENT_RE = re.compile(r"[^A-Za-z0-9 _.\-]")


def sanitize_relpath(rel: str) -> str:
    """Sanitize a relative folder path; raises ValueError if it is unusable."""
    if not rel or not rel.strip():
        raise ValueError("empty path")
    cleaned = rel.strip().replace("\\", "/")
    if cleaned.startswith("/") or re.match(r"^[A-Za-z]:", cleaned):
        raise ValueError(f"absolute path not allowed: {rel!r}")
    parts = []
    for raw_part in cleaned.split("/"):
        part = raw_part.strip()
        if not part:
            continue
        if part in {".", ".."}:
            raise ValueError(f"path traversal not allowed: {rel!r}")
        part = _UNSAFE_COMPONENT_RE.sub("-", part)
        parts.append(part)
    if not parts:
        raise ValueError(f"path has no usable components: {rel!r}")
    out = "/".join(parts)
    return out


def first_matching_rule(rules: list[Rule], filename: str) -> Rule:
    for rule in rules:
        if rule.matches(filename):
            return rule
    fallback = Rule(dest="misc")
    return fallback
