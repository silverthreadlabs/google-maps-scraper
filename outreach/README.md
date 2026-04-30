# Outreach pipeline

Lead-generation pipeline for Silverthread Labs outbound. Scrapes Google Maps
via the gosom Docker scraper (parent repo), mines pain points from review
language, detects chains/DSOs, enriches contacts via website crawl, and
produces sales-ready CSV handoffs.

## Layout

```
outreach/
├── lib/                         # industry-agnostic, reusable across all verticals
│   ├── validators/              # email / phone / POC validation (with tests)
│   │   └── tests/
│   ├── enrichers/               # contact enrichment (website crawl, web search, ...)
│   ├── scrapers/                # gosom Docker wrapper
│   ├── handoff/                 # CSV builder + README template
│   ├── chain_detection.py       # 4-signal DSO/chain detector (industry-agnostic)
│   ├── ranking.py               # quality_score + tier formula
│   ├── url_normalize.py         # strip tracking params before handoff
│   └── data_model.py            # Lead schema, provenance helpers
│
├── pipelines/                   # one folder per industry × geo campaign
│   ├── dental_sunbelt/          # current campaign: dental in Phoenix/Austin/Tampa
│   │   ├── config.py            # ALL dental-specific knobs (single source of truth)
│   │   ├── queries/             # gosom query files per metro
│   │   ├── eval/                # hand-labeled eval set + harness
│   │   ├── raw/                 # raw scrape NDJSONs (immutable)
│   │   ├── enrichment/          # crawl outputs (sidecars, append-only)
│   │   └── outputs/<date>/      # final delivery artifacts
│   └── insurance_sf/            # earlier campaign (preserved)
│
├── silverthread/                # vendored STL service catalog
│   ├── llms.txt                 # short STL service summary
│   ├── llms-full.txt            # full STL service detail
│   └── pain_categories.md       # pain hierarchy consumed by the classifier subagent
├── scripts/                     # deterministic stage CLIs (one per stage)
│   ├── _common.py               # pipeline config loader + path helpers
│   ├── enrich.py                # website-crawl enrichment
│   ├── validate.py              # email/phone validators → sibling flags
│   └── handoff.py               # build handoff CSV
├── tests/                       # cross-cutting / e2e tests
├── .venv/                       # Python venv
└── README.md                    # this file
```

## Principle

- `lib/` is industry-agnostic. Every module here works for any vertical.
- `pipelines/<name>/config.py` holds every industry-specific knob: DSO
  chain list, ranking weights, metro area codes, geographic prefixes.
- The pain taxonomy is **vertical-agnostic** and lives in
  `silverthread/pain_categories.md`. Classification is done by the
  `pain-classifier` Claude Code subagent (`.claude/agents/pain-classifier.md`),
  not by code in this repo.
- To start a new vertical: copy a pipeline folder, edit `config.py`, drop new
  query files in `queries/`. The shared `lib/` code does the rest.

## Data lifecycle

| Folder | What lives here | Mutability |
|---|---|---|
| `pipelines/<name>/raw/` | Raw gosom NDJSON scrapes | **Immutable.** Canonical source. |
| `pipelines/<name>/enrichment/` | Crawler outputs, web-search hits, etc. | Append-only sidecars. |
| `pipelines/<name>/outputs/<date>/` | Final delivery — handoff.csv, master.json | One folder per delivery date. |
| `pipelines/<name>/outputs/<date>/audit/` | Intermediate ranked files for debugging | Optional. |

**Rules** (codified in memory; do not violate):
- Never drop rows. Filtering = subset view in a new file.
- Never replace field values. Add new fields with `<field>_source` and `<field>_added_at`.
- Mark bad values invalid via sibling flags (`email_invalid: true`); do not delete.
- See `feedback_lead_data_never_drop_rows.md` in `~/.claude/projects/.../memory/`.

## Starting a new campaign (cold start)

The full lead-gen sequence for a fresh campaign — new vertical, new geo,
or fresh rescrape of an existing vertical. The `/outreach` slash command
(`.claude/commands/outreach.md`) is the orchestrator; it knows the
per-stage details, hard rules (never drop rows, etc.), and the
pain-classifier subagent dispatch shape. Each stage prints its own
`next:` hint so you can chain by reading the previous output.

1. **Pick / create the pipeline.** Use an existing vertical
   (`pipelines/<name>/`), or copy `dental_sunbelt` and edit `config.py`
   per "Adding a new vertical" below.
2. **Scrape.** Use the `google-maps-scraper` skill
   (`.claude/skills/google-maps-scraper/SKILL.md`) — Docker-based gosom
   wrapper. Tell Claude *"scrape <vertical> in <city> for outreach
   pipeline <pipeline>"*. Output lands in
   `pipelines/<pipeline>/raw/<query>.json` (NDJSON; CLAUDE.md rule 2 —
   never `/tmp`).
3. **Analyze (currently inline).** Build the first master from raw:
   chain detection (`lib/chain_detection.ChainDetector`) + quality
   scoring (`lib/ranking.quality_score`) → `outputs/<today>/master.json`.
   This stage is not yet a script (TODO.md `analyze-as-script`); follow
   the runbook's "Stages not yet supported as scripts" section.
4. **Enrich contacts.** `/outreach <pipeline> enrich` — agent-browser
   crawls websites for emails + POCs. Resumable; writes
   `enrichment/website_crawl.json`.
5. **Classify pain.** `/outreach <pipeline> classify` — dispatches the
   `pain-classifier` subagent against ≤3★ reviews from raw. Emits a
   sidecar at `enrichment/pain_classifications/<today>.json`.
6. **Merge sidecar into master.**
   ```bash
   python outreach/scripts/merge_classifications.py \
     --master  outreach/pipelines/<pipeline>/outputs/<today>/master.json \
     --sidecar outreach/pipelines/<pipeline>/enrichment/pain_classifications/<today>.json \
     --out     outreach/pipelines/<pipeline>/outputs/<today>/master.json
   ```
   Adds `agent_pain_hits` + provenance to every lead. `--master` and
   `--out` can be the same path (atomic write).
7. **Validate.** `/outreach <pipeline> validate` — annotates email/phone
   invalids via sibling flags. Required before handoff.
8. **Handoff.** `/outreach <pipeline> handoff` — produces
   `outputs/<today>/handoff.csv` for sales.

**Re-delivery against an existing master?** See the "Re-delivery flow"
section in `.claude/commands/outreach.md`. Skips scrape and the first
analyze; degenerate masters (no `place_id`) get backfilled from raw.

## Daily driver

Each stage is a standalone CLI. Run them individually, or chain them
from a slash command / shell script. The slash-command runbook
(`.claude/commands/outreach.md`) is the planned orchestrator — it also
dispatches the `pain-classifier` subagent for the LLM-only stages.

```bash
source outreach/.venv/bin/activate

# Stages currently shipped as scripts:
python outreach/scripts/enrich.py   dental_sunbelt [--queue PATH] [--workers N]
python outreach/scripts/validate.py dental_sunbelt [--master PATH]
python outreach/scripts/handoff.py  dental_sunbelt [--master PATH] [--out PATH]

# Bridge classify → handoff: graft sidecar into master with provenance.
python outreach/scripts/merge_classifications.py \
    --master  pipelines/<pipeline>/outputs/<old-date>/master.json \
    --sidecar pipelines/<pipeline>/enrichment/pain_classifications/<today>.json \
    --out     pipelines/<pipeline>/outputs/<today>/master.json

# Stages still pending (slash-command-only for now):
#   scrape   — wraps the gosom Docker scraper (skill at
#              .claude/skills/google-maps-scraper/SKILL.md)
#   analyze  — pain classification (pain-classifier subagent) + chain
#              detection + quality scoring → master.json

# Run all unit tests
for t in $(find outreach/lib outreach/scripts outreach/tests -name 'test_*.py' 2>/dev/null); do
    python "$t"
done

# Score the pain-classifier subagent against the gold set
# (1) Dispatch the `pain-classifier` subagent on
#     pipelines/dental_sunbelt/eval/sample_unlabeled.json from your Claude
#     Code session and save its JSON output as predictions.json.
# (2) Run the metric script on the saved predictions:
python outreach/pipelines/dental_sunbelt/eval/eval_runner.py predictions.json
```

## Current state (2026-04-29)

- Dental campaign delivered (2026-04-25): 75 verified-email Tier A+B leads,
  173 independents in master, see
  `pipelines/dental_sunbelt/outputs/2026-04-25/handoff.csv`.
- Sales feedback flagged two bugs:
  1. Pain quote ↔ category mismatch — solved by the `pain-classifier`
     Claude Code subagent (`.claude/agents/pain-classifier.md`) classifying
     reviews against the STL hierarchy in `silverthread/pain_categories.md`.
     Latest baseline on the 100-review gold set: main F1 0.784, strict
     (main, sub) F1 0.683, strict exact-match 0.64 — vs prior SBERT
     baseline of ~0.43. Eval harness: `pipelines/dental_sunbelt/eval/eval_runner.py`.
  2. URLs had tracking-param noise.
     Fixed: `lib/url_normalize.py` + tests, wired through
     `lib/handoff/csv_builder.py` at output time. Cleaned URL replaces
     the raw value; the original is preserved in
     `<field>_raw` audit columns when normalization changed it.

## Tests

Unit tests live alongside their modules. Run all:

```bash
for t in $(find outreach/lib outreach/scripts outreach/tests -name 'test_*.py' 2>/dev/null); do
    python "$t" 2>&1 | tail -2
done
```

Current count: 71 tests across 7 modules (email, phone, url_normalize,
handoff/csv_builder, enrichers/website_crawl, scripts/merge_classifications,
scripts/_common pipeline_lock).

## Adding a new vertical

1. `cp -r outreach/pipelines/dental_sunbelt outreach/pipelines/<new_vertical>`
2. Edit `pipelines/<new_vertical>/config.py`:
   - Update `DSO_TITLE_REGEX` and `DSO_EMAIL_DOMAINS` with new vertical's chains
   - Update `GEOGRAPHIC_PREFIXES` so chain detection doesn't false-positive
     on shared metro prefixes (see `outreach/CLAUDE.md` rule 6)
   - Update `METRO_AREA_CODES` if targeting different geos
   - Update `PAIN_WEIGHTS` and `SERVICE_MAP` (re-key both when ranking
     moves to (main, sub) tuples)
   - Update `VENDOR_DOMAINS_EXTRA` with vendor domains specific to that
     vertical (e.g. dental marketing services); generic web-builder/SaaS
     domains are already in `lib/validators/email.py:VENDOR_DOMAINS`
   - Update `ENRICH_PROFILE` (POC title markers, JSON-LD types,
     subpage link patterns) — see `lib/enrichers/website_crawl.py`
3. Drop new query files in `pipelines/<new_vertical>/queries/`.
4. The pain taxonomy in `silverthread/pain_categories.md` is vertical-
   agnostic; only re-derive it when STL's service catalog changes.
5. Scrape into `pipelines/<new_vertical>/raw/` (see scrape stage notes
   in "Daily driver" — slash command, not yet a script), then run the
   shipped scripts in order.
