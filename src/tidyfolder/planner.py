"""Planner: scan a messy folder and compute a move plan (dry-run safe)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .rules import Rule, first_matching_rule, parse_dest_template, sanitize_relpath


@dataclass
class Move:
    source: Path
    rel_name: str
    dest_dir: Path
    reason: str
    is_suggestion: bool = False


@dataclass
class Plan:
    target: Path
    archive: Path
    moves: list[Move] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)


def build_plan(
    target: Path,
    rules: list[Rule],
    archive: Path,
    protected: list[Path] | None = None,
    suggestions: dict[str, str] | None = None,
) -> Plan:
    """Build a top-level-only move plan. Files only ever move into `archive`."""
    target = target.resolve()
    archive = archive.resolve()
    protected = [p.resolve() for p in (protected or [])]
    suggestions = suggestions or {}
    plan = Plan(target=target, archive=archive)
    for entry in sorted(target.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_file():
            plan.skipped.append((entry, "not a plain file"))
            continue
        if entry.name.startswith("."):
            plan.skipped.append((entry, "hidden file"))
            continue
        if entry in protected:
            plan.skipped.append((entry, "protected (rules/undo log)"))
            continue
        try:
            rel = sanitize_relpath(
                parse_dest_template(
                    suggestions.get(entry.name, first_matching_rule(rules, entry.name).dest),
                    entry.name,
                    entry.stat().st_mtime,
                )
            )
        except ValueError as exc:
            plan.skipped.append((entry, f"unsafe destination ({exc})"))
            continue
        dest_dir = archive / rel
        if _escapes_archive(dest_dir, archive):
            plan.skipped.append((entry, "destination would leave the archive"))
            continue
        suggested = entry.name in suggestions
        rule = first_matching_rule(rules, entry.name)
        reason = "LLM suggestion" if suggested else (rule.description or rule.dest or "catch-all")
        plan.moves.append(
            Move(source=entry, rel_name=entry.name, dest_dir=dest_dir, reason=reason,
                 is_suggestion=suggested)
        )
    return plan


def _escapes_archive(path: Path, archive: Path) -> bool:
    """True when a destination is not safely inside the archive root."""
    return path != archive and archive not in path.parents
