# STATUS.md — tidyfolder

**Project:** tidyfolder — a safe, local-first CLI that tidies messy folders
**Owner:** Asdale Dynamics, LLC
**Date:** 2026-10-25
**License:** MIT (see `LICENSE`)

## What was built

`tidyfolder` is a Python 3.10+ command-line tool (pure stdlib; pytest only for
tests) that tidies a messy folder by **moving** (never deleting) files into a
clean archive structure.

Core commands and guarantees:

- `tidyfolder sort PATH` — plans a tidy-up. **Dry-run preview is mandatory**: by
  default it only prints `WOULD MOVE` lines and changes nothing.
- `--apply` performs the moves only after previewing and an explicit `--yes` (or
  an interactive confirmation prompt). Non-interactive shells without `--yes`
  are refused.
- `--rules FILE` — user rules (TOML): sort by **name patterns** (globs),
  **extensions**, and **date patterns** (`{year}`, `{month}`, `{year_month}`
  from file mtime). First match wins; a matcher-less rule is a catch-all.
  `tidyfolder init` writes a documented starter rules file.
- `--suggest` — optional folder-name suggestions from any OpenAI-compatible
  endpoint (default `http://localhost:11434/v1`, local Ollama, model
  `llama3.2`). Only **file names** are sent, never contents, and **no API key
  is ever requested/stored/sent**. Every suggestion is confirmed before
  applying (per-file `y/N/a/q` prompt; non-interactive runs never apply
  suggestions).
- `--backup DIR` (default `archive/.backup`) — every file is **copied to a
  backup before** the original is touched (backup-then-move).
- `tidy-undo.json` — an **undo log** rewritten after every completed move
  (crash-safe). `tidyfolder undo LOG --yes` reverses moves; undo never
  overwrites or deletes either.
- **Never deletes:** everything moves into the archive path; name collisions are
  renamed (`file-1.ext`), never overwritten; destination paths are sanitized
  (no `..`, no absolute paths); `_escapes_archive` guarantees destinations stay
  inside the archive; hidden files, directories, the archive, backups, rules
  file, and undo log are never moved.

## Layout

```
pyproject.toml          install metadata (zero dependencies)
LICENSE                 MIT, Copyright (c) 2026 Asdale Dynamics, LLC
README.md               full user documentation, credits Asdale Dynamics, LLC
src/tidyfolder/         cli, planner, rules, executor (backup+move), undolog, llm
tests/                  56 pytest tests using tmp-path fixtures (no network)
```

## How to run it

```bash
pip install .                    # or: python -m venv .venv && .venv/bin/pip install -e .
tidyfolder sort ~/Downloads      # dry-run preview (default)
tidyfolder sort ~/Downloads --apply --yes
tidyfolder undo ~/Downloads/tidy-undo.json --yes
tidyfolder init ~/tidy-rules.toml
tidyfolder sort ~/Downloads --suggest   # optional local-LLM suggestions
python -m tidyfolder --version          # also runnable without installing
```

## Verification performed

- `pytest -q` → **56 passed** (rules, planner, executor, undo log, LLM parsing,
  CLI behaviors, non-deletion invariants — all on pytest `tmp_path` fixtures).
- End-to-end smoke test in a real scratch folder: `sort` (dry run) left the
  folder untouched; `--apply --yes` moved 11 files into
  `archive/{images,documents,spreadsheets,audio,video,archives,code,misc/...}`
  with 12 backups in `archive/.backup`; `undo --yes` restored all files.
- Live HTTP check against a local mock OpenAI-compatible server: request
  reached `/v1/chat/completions`, suggestion parsed and shown in the preview,
  unconfirmed suggestions safely fell back to rule destinations in a
  non-interactive run.
- Unavailable-server check: `--suggest` without a running Ollama degrades to
  rules-only with a warning (exit code 0).

## Known gaps / limitations

- Top-level only: nested directories are left untouched by `sort`.
- Undo does not remove leftover empty directories under the archive (undo never
  deletes, by design).
- Backups are cumulative; there is no `--prune` (which would delete, so it is
  out of scope on purpose).
- LLM suggestions are untested against real local model output (mocked tests);
  prompts are basic — no conversational refinement or multi-pass organization.
- If two `sort` runs use different `--undo-log` files, undo them in reverse
  chronological order to stay consistent.
- No Windows testing (only POSIX `os.replace`/EXDEV path is exercised on
  Linux); drive-letter-absolute paths are rejected by the sanitizer.
- `--limit` caps how many names are sent to the LLM; there is no batching for
  very large folders.
