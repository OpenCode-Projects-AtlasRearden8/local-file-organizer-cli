"""Command-line interface for tidyfolder.

Safety model:
  * dry-run preview is the default; moves only happen with --apply
  * every move is backed up (copy) before it happens
  * every move is recorded in an undo log so it can be reversed
  * nothing is ever deleted; files only ever move into the archive path
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import llm, undolog
from .executor import apply_plan
from .planner import Plan, build_plan
from .rules import DEFAULT_RULES_TOML, RuleError, load_rules


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (RuleError, ValueError, OSError) as exc:
        print(f"tidyfolder: error: {exc}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tidyfolder",
        description=(
            "Tidy a messy folder safely: files are only ever MOVED into an "
            "archive path, after a backup, with a dry-run preview first "
            "and an undo log. Never deletes anything."
        ),
    )
    parser.add_argument("--version", action="version", version=f"tidyfolder {_version()}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sort = sub.add_parser("sort", help="preview and apply a tidy plan")
    _add_sort_options(p_sort)
    p_sort.set_defaults(func=_cmd_sort)

    p_undo = sub.add_parser("undo", help="reverse moves recorded in undo logs")
    p_undo.add_argument("logs", nargs="+", type=Path, help="undo log JSON file(s)")
    p_undo.add_argument("--yes", "-y", action="store_true", help="skip confirmation")
    p_undo.set_defaults(func=_cmd_undo)

    p_init = sub.add_parser("init", help="write a starter rules file")
    p_init.add_argument("path", nargs="?", type=Path, default=Path("tidy-rules.toml"))
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=_cmd_init)

    return parser


def _add_sort_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("path", type=Path, help="folder to tidy")
    p.add_argument("--rules", type=Path, default=None, help="rules TOML file (defaults: built-in)")
    p.add_argument("--archive", type=Path, default=None,
                   help="archive root (default: <path>/archive)")
    p.add_argument("--backup", type=Path, default=None,
                   help="backup root (default: <path>/archive/.backup)")
    p.add_argument("--undo-log", type=Path, default=None,
                   help="undo log file (default: <path>/tidy-undo.json)")
    p.add_argument("--apply", action="store_true",
                   help="actually move files (the default is preview only)")
    p.add_argument("--yes", "-y", action="store_true",
                   help="skip the final confirmation")
    p.add_argument("--suggest", action="store_true",
                   help="ask a local LLM for folder suggestions (unmatched files)")
    p.add_argument("--suggest-all", action="store_true",
                   help="with --suggest: ask for every file, not just unmatched ones")
    p.add_argument("--api-base", default=None,
                   help="OpenAI-compatible endpoint (default: "
                        "http://localhost:11434/v1 for local Ollama; no API key needed)")
    p.add_argument("--model", default=None, help="model name (default: llama3.2)")
    p.add_argument("--timeout", type=float, default=60.0,
                   help="LLM request timeout in seconds (default: 60)")
    p.add_argument("--limit", type=int, default=200,
                   help="max files sent to the LLM (default: 200)")


def _cmd_sort(args: argparse.Namespace) -> int:
    target = args.path.resolve()
    if not target.is_dir():
        print(f"tidyfolder: not a folder: {target}", file=sys.stderr)
        return 2
    rules = load_rules(args.rules)
    archive = (args.archive if args.archive else target / "archive").resolve()
    backup_root = (args.backup if args.backup else archive / ".backup").resolve()
    undo_log = (args.undo_log if args.undo_log else target / "tidy-undo.json").resolve()

    suggestions = _fetch_suggestions(args, target, archive)
    default_rules_file = target / "tidy-rules.toml"
    protected = [p for p in (args.rules, undo_log, default_rules_file) if p is not None]
    plan = build_plan(target, rules, archive, protected=protected, suggestions=suggestions)
    _print_plan(plan, applying=args.apply)

    if args.suggest:
        print("Suggested destinations are proposals only; you will confirm each "
              "one before it is applied.\n")

    if not args.apply:
        print("Dry run only: nothing was moved. Add --apply to make these moves.")
        return 0

    if suggestions and plan.moves:
        suggestions = _confirm_suggestions(args, plan, suggestions)
        plan = build_plan(target, rules, archive, protected=protected,
                          suggestions=suggestions)
        _print_plan(plan, applying=True)

    if not _human_terminal() and not args.yes:
        print("tidyfolder: refusing to apply without --yes because stdin is not "
              "interactive.", file=sys.stderr)
        return 2

    if not args.yes:
        answer = input(f"\nApply {len(plan.moves)} move(s) (backed up, undoable)? [y/N] ")
        if _not_yes(answer):
            print("Aborted. Nothing was moved.")
            return 0

    if plan.moves:
        apply_plan(plan, backup_root, undo_log)
        print(f"Done: {len(plan.moves)} move(s) applied.")
        print(f"Backups: {backup_root}")
        print(f"Undo: tidyfolder undo {undo_log}")
        return 0
    print("Nothing to move.")
    return 0


def _fetch_suggestions(args: argparse.Namespace, target: Path, archive: Path) -> dict[str, str]:
    if not args.suggest and not args.suggest_all:
        return {}
    if not args.suggest and args.suggest_all:
        args.suggest = True
    rules = load_rules(args.rules)
    from .planner import build_plan as _bp  # local import avoids circular cost

    probe = _bp(target, rules, archive, protected=[target / "tidy-undo.json"])
    from .rules import first_matching_rule

    if args.suggest_all:
        candidates = [m.source.name for m in probe.moves if not m.is_suggestion]
    else:
        leftover = []
        for move in probe.moves:
            rule = first_matching_rule(rules, move.source.name)
            if rule.dest.startswith("misc"):
                leftover.append(move.source.name)
        candidates = leftover
    candidates = llm.limit_filenames(candidates, args.limit)
    if not candidates:
        print("LLM suggestions: no files eligible; skipping the request.")
        return {}
    api_base = args.api_base or llm.default_api_base()
    model = args.model or llm.DEFAULT_MODEL
    print(f"Asking {model} at {api_base} for folder suggestions "
          f"({len(candidates)} filenames, contents never sent)...")
    try:
        mapping = llm.chat_suggest(api_base, model, candidates, timeout=args.timeout)
    except Exception as exc:  # noqa: BLE001 - suggestions are optional
        print(f"LLM suggestions unavailable ({exc}); using rules only.", file=sys.stderr)
        return {}
    return mapping


def _confirm_suggestions(args: argparse.Namespace, plan: Plan,
                         suggestions: dict[str, str]) -> dict[str, str]:
    planned = {m.source.name for m in plan.moves}
    if not _human_terminal():
        print("LLM suggestions will NOT be applied in a non-interactive run; "
              "rules were used instead.", file=sys.stderr)
        return {}
    if args.yes:
        print(f"Auto-accepting {len(suggestions)} LLM suggestion(s) because --yes "
              "was given.")
        return suggestions
    confirmed: dict[str, str] = {}
    for name, folder in sorted(suggestions.items()):
        if name not in planned:
            continue
        answer = input(f"Suggested home for '{name}': archive/{folder}  "
                       "[y/N/a(ll)/q(uit-suggestions)] ")
        answer = answer.strip().lower()
        if answer == "a":
            confirmed = {n: f for n, f in suggestions.items() if n in planned}
            break
        if answer == "q":
            break
        if answer in {"y", "yes"}:
            confirmed[name] = folder
    return confirmed


def _not_yes(answer: str) -> bool:
    return answer.strip().lower() not in {"y", "yes"}


def _print_plan(plan: Plan, applying: bool) -> None:
    print(f"tidyfolder plan for {plan.target}")
    print(f"  archive: {plan.archive}")
    if plan.skipped:
        print(f"  skipping {len(plan.skipped)} item(s):")
        for path, why in plan.skipped[:20]:
            print(f"    - {path.name}: {why}")
    if plan.moves:
        prefix = "MOVE" if applying else "WOULD MOVE"
        for move in plan.moves:
            rel_dest = move.dest_dir.relative_to(plan.archive)
            tag = ""
            print(f"  {prefix}  {move.rel_name}  ->  archive/{rel_dest}/{move.rel_name}"
                  f"  ({move.reason}){tag}")
        print(f"  {len(plan.moves)} file(s) to move, {len(plan.skipped)} skip(s).")
    else:
        print("  Nothing to move; the top level is already clean.")


def _cmd_undo(args: argparse.Namespace) -> int:
    for log_path in args.logs:
        if not _human_terminal() and not args.yes:
            print("tidyfolder: refusing to undo without --yes because stdin is not "
                  "interactive.", file=sys.stderr)
            return 2
        if not args.yes:
            answer = input(f"Undo {len(undolog.load(log_path))} move(s) in {log_path}? [y/N] ")
            if _not_yes(answer):
                print("Aborted. Nothing changed.")
                return 0
        for path, ok, message in undo_log_file(log_path):
            status = "restored" if ok else ("skipped" if ok is not None else "failed")
            print(f"  {status}: {path} {message}")
    return 0


def undo_log_file(log_path: Path):
    for entry in reversed(undolog.load(log_path)):
        source = Path(entry["source"])
        dest = Path(entry["dest"])
        if not dest.exists():
            yield dest.name, None, f"missing at {dest}"
            continue
        if source.exists():
            yield source.name, None, f"already exists at {source}"
            continue
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dest), str(source))
        yield source.name, True, f"moved back from {dest}"


def _cmd_init(args: argparse.Namespace) -> int:
    path = args.path
    if path.exists() and not args.force:
        print(f"{path} already exists; use --force to overwrite.")
        return 1
    path.write_text(DEFAULT_RULES_TOML, encoding="utf-8")
    print(f"Starter rules written to {path}. Edit freely, then run:")
    print(f"  tidyfolder sort <folder> --rules {path}")
    return 0


def _human_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _version() -> str:
    from . import __version__

    return __version__


if __name__ == "__main__":
    raise SystemExit(main())
