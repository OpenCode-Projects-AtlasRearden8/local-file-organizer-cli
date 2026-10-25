# tidyfolder

**A safe, local-first CLI that tidies messy folders without ever deleting a file.**

tidyfolder sorts a cluttered folder into a clean `archive/` structure using simple
rules (file-name patterns, file extensions, or date patterns from file mtimes).
Everything is previewed first, backed up before it moves, and recorded in an undo
log — and nothing is ever deleted: files only ever **move** into your archive path.

**Credit:** built and maintained by
[**Asdale Dynamics, LLC**](https://dylanasdale.github.io) — plain-English AI
guides and practical, tested tools. Licensed under the MIT License.

---

## Why you can trust it

| Guarantee | How it works |
|---|---|
| **Dry-run preview is mandatory** | `sort` shows the full move plan by default and changes nothing. Add `--apply` to actually move. |
| **Never deletes** | Nothing is ever removed. Files only move into the archive path; the previous content stays on disk. |
| **Backup before every move** | `--apply` copies each file to a backup folder *before* the original is moved. |
| **Undo log** | Every move is recorded after the move completes, so `tidyfolder undo` can reverse it at any time. |
| **Confirm-by-default** | Applying requires `--yes` or an explicit terminal prompt; non-interactive shells are refused without `--yes`. |
| **No secrets, no uploads** | Only file *names* are ever sent to the LLM endpoint (and only if you ask); file contents never leave the folder. No API keys are requested, stored, or sent. |

## Install

```bash
pip install .
```

Requires Python 3.10+. No third-party dependencies.

## Quickstart

```bash
# 1. Preview what would happen (nothing changes yet — the default)
tidyfolder sort ~/Downloads

# 2. Apply the moves, backed up and undoable
tidyfolder sort ~/Downloads --apply --yes

# 3. (Optional) write your own rules file
tidyfolder init ~/tidy-rules.toml

# 4. Preview again with your own rules, then apply
tidyfolder sort ~/Downloads --rules ~/tidy-rules.toml
tidyfolder sort ~/Downloads --rules ~/tidy-rules.toml --apply --yes

# 5. Changed your mind?
tidyfolder undo ~/Downloads/tidy-undo.json --yes
```

Example preview output:

```
tidyfolder plan for /home/you/Downloads
  archive: /home/you/Downloads/archive
  WOULD MOVE  IMG_0001.jpg  ->  archive/images/IMG_0001.jpg  (images)
  WOULD MOVE  report.pdf    ->  archive/documents/report.pdf  (documents)
  2 file(s) to move, 5 skip(s).
Dry run only: nothing was moved. Add --apply to make these moves.
```

## How sorting works

Sorting is top-level only (nested folders are left alone). Each file is matched
against your rules **in order**; the first match wins.

- **Name patterns** — glob on the file name, case-insensitive: `name = "*.pdf"`
- **Extensions** — `ext = ["pdf", "docx"]`
- **Date patterns** — templates such as `misc/{year}/{year_month}` (from the file's mtime)
- **Catch-all** — a rule with no matcher matches everything
- **Template variables** — `{ext}` `{year}` `{month}` `{day}` `{year_month}`

The built-in default rules (used when there is no `--rules` file) put common
files into `images`, `documents`, `spreadsheets`, `audio`, `video`, `archives`,
and `code`, group anything else by `{ext}-files`, and end with a
`misc/{year}/{year_month}` catch-all.

## LLM suggestions (optional, local-first)

Add `--suggest` and tidyfolder will optionally ask a local LLM — via any
OpenAI-compatible endpoint — where the *unmatched* leftover files should go.
The default endpoint is your own machine:

```
http://localhost:11434/v1   (local Ollama, model llama3.2)
```

- Every confirmed suggestion replaces that one file's destination; you confirm each suggestion before anything is applied.
- Point at another server with `--api-base` (or the `TIDYFOLDER_API_BASE` env var) and `--model`, e.g. `--model llama3.1:8b`.
- Only **file names** are sent — never file contents, and **no API key is ever requested, stored, or sent**. The tool is designed to talk to a local endpoint.
- Use `--suggest-all` to ask for every file instead of only leftovers.

```bash
ollama pull llama3.2          # one-time setup on your own machine
tidyfolder sort ~/Downloads --suggest
tidyfolder sort ~/Downloads --suggest --apply --yes
```

## Undo

`--apply` writes `tidy-undo.json` (customizable with `--undo-log`) next to the
sorted folder. Rewriting it after every single move keeps the log usable even
after a mid-run crash.

```bash
tidyfolder undo path/to/tidy-undo.json --yes
```

Undo moves files back to their original locations and skips anything it would
otherwise overwrite. Backups stay in place — undo never deletes either.

## Commands and options

```
tidyfolder sort PATH [options]     preview (default) or apply a tidy plan
tidyfolder undo LOG [LOG ...]      reverse the moves recorded in undo logs
tidyfolder init [PATH]             write a starter rules file (tidy-rules.toml)
tidyfolder --version
```

`sort` options:

| Flag | Default | Meaning |
|---|---|---|
| `--rules FILE` | built-in rules | rules TOML file |
| `--archive PATH` | `PATH/archive` | where everything ends up |
| `--backup PATH` | `archive/.backup` | where pre-move backups go |
| `--undo-log PATH` | `PATH/tidy-undo.json` | the undo record |
| `--apply` | off | actually move (preview is the default) |
| `--yes` / `-y` | off | skip prompts (required in non-interactive shells) |
| `--suggest` | off | ask the LLM about leftover files |
| `--suggest-all` | off | with `--suggest`: ask about every file |
| `--api-base URL` | `http://localhost:11434/v1` (Ollama) | OpenAI-compatible endpoint (no API key) |
| `--model NAME` | `llama3.2` | model to request |
| `--timeout SECONDS` | `60` | LLM request timeout |
| `--limit N` | `200` | max file names sent to the LLM |

You can also run it without installing: `python -m tidyfolder sort <folder>`.

## Privacy & safety notes

- Everything runs locally; the only network call is an optional request to the
  LLM endpoint you configure (local Ollama by default).
- No API keys, secrets, telemetry, or personal data are involved anywhere: the
  tool never asks for a key, never stores one, and never sends one.
- Hidden files, directories, the archive, backup, rules file, and undo log are
  never moved.
- Destination paths are sanitized: absolute paths, `..` traversal, and odd
  characters in folder names are rejected. Name collisions are renamed
  (`file-1.ext`), never overwritten.

## Development

```bash
pip install -e .
pytest                # test suite (pytest tmp-path fixtures, no network needed)
```

Project layout:

```
src/tidyfolder/   cli, planner, rules, executor, undo log, LLM client
tests/            pytest suite (rules, planner, executor, undo, LLM, CLI)
```

## License

MIT — see [LICENSE](LICENSE). **Copyright (c) 2026 Asdale Dynamics, LLC.**
Part of the beginner-friendly AI toolkit at
[dylanasdale.github.io](https://dylanasdale.github.io) — *The Massive AI Manual*
companion tools. This is a general file-organization utility; it offers no
advice of any professional kind.
