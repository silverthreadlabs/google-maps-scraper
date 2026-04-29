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
│   ├── pain/                    # pain classifiers (interchangeable)
│   │   ├── regex.py             # fast cheap baseline + corroboration signal
│   │   ├── sbert.py             # SBERT semantic classifier (better recall)
│   │   └── llm.py               # planned: Claude Haiku 4.5 classifier (in progress)
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
├── orchestrator.py              # CLI: scrape | analyze | enrich | validate | handoff
├── tests/                       # cross-cutting / e2e tests
├── .venv/                       # Python venv with sentence-transformers
└── README.md                    # this file
```

## Principle

- `lib/` is industry-agnostic. Every module here works for any vertical.
- `pipelines/<name>/config.py` holds every industry-specific knob: pain
  categories, regex patterns, SBERT anchor sentences, DSO chain list, service
  catalog, ranking weights, metro area codes.
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

## Daily driver

```bash
# Activate venv
source outreach/.venv/bin/activate

# Run full pipeline for an existing campaign
python outreach/orchestrator.py run dental_sunbelt

# Or stage by stage
python outreach/orchestrator.py scrape dental_sunbelt
python outreach/orchestrator.py analyze dental_sunbelt
python outreach/orchestrator.py enrich dental_sunbelt
python outreach/orchestrator.py validate dental_sunbelt
python outreach/orchestrator.py handoff dental_sunbelt

# Run all unit tests
for t in outreach/lib/validators/tests/test_*.py outreach/lib/test_*.py; do
    python "$t"
done

# Re-evaluate the pain classifier against the labeled set
outreach/.venv/bin/python outreach/pipelines/dental_sunbelt/eval/eval_classifier.py
```

## Current state (2026-04-29)

- Dental campaign delivered (2026-04-25): 75 verified-email Tier A+B leads,
  173 independents in master, see
  `pipelines/dental_sunbelt/outputs/2026-04-25/handoff.csv`.
- Sales feedback flagged two bugs:
  1. Pain quote ↔ category mismatch — regex is too coarse for subjective
     categories; SBERT improves precision but plateaus at moderate F1.
     Fix in progress: LLM-based classifier in `lib/pain/llm.py` (Claude
     Haiku 4.5). Run `pipelines/dental_sunbelt/eval/eval_classifier.py`
     for current baselines and to validate the new classifier against
     the hand-labeled gold set.
  2. URLs had tracking-param noise.
     Fixed: `lib/url_normalize.py` + tests; will be applied at handoff time.

## Tests

Unit tests live alongside their modules. Run all:

```bash
for t in outreach/lib/validators/tests/test_*.py outreach/lib/test_*.py; do
    python "$t" 2>&1 | tail -2
done
```

Current count: 28 tests across 4 modules (email, phone, POC, url_normalize).

## Adding a new vertical

1. `cp -r outreach/pipelines/dental_sunbelt outreach/pipelines/<new_vertical>`
2. Edit `pipelines/<new_vertical>/config.py`:
   - Update `SERVICE_MAP` with new vertical's Silverthread services
   - Update `PAIN_REGEX_PATTERNS` and `SBERT_ANCHORS` with new vocabulary
   - Update `DSO_TITLE_REGEX` and `DSO_EMAIL_DOMAINS` with new vertical's chains
   - Update `METRO_AREA_CODES` if targeting different geos
   - Update `PAIN_WEIGHTS` to reflect Silverthread service fit for that vertical
3. Drop new query files in `pipelines/<new_vertical>/queries/`.
4. Run `orchestrator.py scrape <new_vertical>` and continue from there.
