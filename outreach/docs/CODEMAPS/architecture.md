<!-- Generated: 2026-06-15 | Files scanned: ~38 lib modules + 5 verticals + 5 locations | Token estimate: ~700 -->

# Architecture (codemap)

One-screen overview. Detail lives in the sibling codemaps; full prose in `../architecture.md`.

## What it is

Python CLI pipeline: raw Google Maps scrapes → enriched, pain-classified leads → sales CSV + push to the **stl-knights** backend. No web frontend, no relational DB — state is JSON files on disk (see `data.md`).

## Layers

```
/outreach <pipeline> <stage>        .claude/commands/outreach.md  (runbook; only orchestrator)
        │  dispatches
        ▼
PIPELINE STAGES                     lib/cli/*.py  (one script per stage) + 2 LLM subagents
analyze → enrich → classify* → osint-enrich* → validate → handoff → push
        │  reads/writes
        ▼
DATA                                campaigns/<v>_<loc>/{raw,enrichment,outputs}/  (JSON)
        │  uses
        ▼
SHARED LIB                          lib/{validators,enrichers,handoff} + ranking, chain_detection, …
        │  parameterized by
        ▼
CONFIG                              verticals/<v>/config.py + locations/<loc>.yaml + campaigns/*/overrides.py
```
`*` = LLM subagent stages (`.claude/agents/pain-classifier.md`, `osint-binder.md`), not Python scripts.

## Codemap index

| File | Covers |
|------|--------|
| `pipeline.md`     | Stage → script → output; CLI entry points + signatures |
| `lib.md`          | Industry-agnostic shared modules + function signatures |
| `data.md`         | JSON state model: master.json v0→v4, append-only sidecars, provenance |
| `config.md`       | 3-layer config merge (vertical + location + campaign override) |
| `dependencies.md` | External services (agent-browser, Docker/gosom, Claude Code, stl-knights API) + Python libs |

## Core invariants (full list: `../architecture.md` §10, `../../CLAUDE.md`)

1. **Append-only data** — add fields with `_source`/`_added_at`; never drop rows or replace values. Bad values get sibling `*_invalid` flags.
2. **`lib/` is industry-agnostic** — vertical knobs only in `verticals/`/`locations/`/`overrides.py`.
3. **Validate before handoff** — `csv_builder` reads `*_invalid` flags.
4. **Raw scrapes are immutable**, never `/tmp`.
5. **Crawler uses a session pool** (`queue.Queue` lease), not round-robin.

## Drift vs prose docs (as of this scan)

`../architecture.md` / `../README.md` predate the current tree. Reality: stages live in **`lib/cli/`** (not `scripts/`); there is **no `lib/scrapers/`**; push targets the **stl-knights backend** (not Mixmax/Instantly); additional stages exist (`translate`, `merge_translations`, `decision_makers`, `contacts`) plus helpers `lang_detect.py`, `lead_fields.py`. These codemaps reflect current code; the prose docs are not edited here.
