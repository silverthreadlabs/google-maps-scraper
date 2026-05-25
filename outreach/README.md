# Outreach pipeline

Lead-generation pipeline for Silverthread Labs outbound. Scrapes Google Maps
via the gosom Docker scraper (parent repo), mines pain points from review
language, detects chains/DSOs, enriches contacts via website crawl, and
produces sales-ready CSV handoffs.

## Layout

```
outreach/
├── verticals/<v>/               # vertical template — pain weights, services, enrich profile
│   ├── config.py                # DSO regex (vertical-wide chains), weights, OSINT templates
│   ├── query_templates.txt      # {city}/{state}/{neighborhood} placeholder templates
│   └── README.md
├── locations/<loc>.yaml         # pure location data — cities, area codes, prefixes
├── campaigns/<v>_<loc>/         # run instance — raw, enrichment, outputs, optional overrides
│   ├── campaign.yaml            # names the vertical + location
│   ├── overrides.py             # OPTIONAL — regional chains, PAIN_WEIGHTS tweaks
│   ├── queries/                 # rendered per-city query files
│   ├── raw/                     # raw scrape NDJSONs (immutable)
│   ├── enrichment/              # crawl/classify/osint sidecars (append-only)
│   └── outputs/<date>/          # final delivery artifacts
├── lib/                         # industry-agnostic
│   ├── cli/                     # CLI entry points (analyze, enrich, validate, handoff, …)
│   ├── validators/              # email / phone / POC validation
│   ├── enrichers/               # contact enrichment (website crawl, web search, ...)
│   ├── handoff/                 # CSV builder + README template
│   ├── campaign_config.py       # merging loader (verticals + locations + overrides)
│   ├── render_queries.py        # template × location → per-city query files
│   ├── chain_detection.py       # 4-signal DSO/chain detector
│   ├── ranking.py               # quality_score + tier formula
│   └── url_normalize.py         # strip tracking params before handoff
├── silverthread/                # vendored STL service catalog
│   └── pain_categories.md       # pain hierarchy consumed by the classifier subagent
├── tests/                       # cross-cutting / e2e tests
└── README.md                    # this file
```

## Principle

- `lib/` is industry-agnostic. Every module here works for any vertical.
- `verticals/<v>/config.py` holds vertical-wide knobs: pain weights, DSO
  regex for chains that apply everywhere the vertical runs, enrich profile.
- `locations/<loc>.yaml` holds pure location data: cities, area codes,
  neighborhood / geographic prefixes — re-usable across verticals.
- `campaigns/<v>_<loc>/overrides.py` (optional) holds region-specific
  chain lists and any per-campaign tuning.
- The pain taxonomy is vertical-agnostic and lives in
  `silverthread/pain_categories.md`. Classification is done by the
  `pain-classifier` Claude Code subagent.
- To start a new campaign: pick or author a location, pick a vertical,
  write `campaigns/<v>_<loc>/campaign.yaml`. See "Adding a campaign" below.

## Data lifecycle

| Folder | What lives here | Mutability |
|---|---|---|
| `campaigns/<name>/raw/` | Raw gosom NDJSON scrapes | **Immutable.** Canonical source. |
| `campaigns/<name>/enrichment/` | Crawler outputs, web-search hits, etc. | Append-only sidecars. |
| `campaigns/<name>/outputs/<date>/` | Final delivery — handoff.csv, master.json | One folder per delivery date. |
| `campaigns/<name>/outputs/<date>/audit/` | Intermediate ranked files for debugging | Optional. |

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
   (`campaigns/<name>/`), or copy `dental_sunbelt` and edit `config.py`
   per "Adding a new vertical" below.
2. **Scrape.** Use the `google-maps-scraper` skill
   (`.claude/skills/google-maps-scraper/SKILL.md`) — Docker-based gosom
   wrapper. Tell Claude *"scrape <vertical> in <city> for outreach
   pipeline <pipeline>"*. Output lands in
   `campaigns/<pipeline>/raw/<query>.json` (NDJSON; CLAUDE.md rule 2 —
   never `/tmp`).
3. **Analyze.** `python outreach/lib/cli/analyze.py <pipeline>` — dedupe
   raw by `place_id`, run chain detection
   (`lib/chain_detection.ChainDetector`), partition gosom-side emails
   through `validate_email` (image artifacts → `emails_invalid` at
   ingest), compute initial `quality_score` →
   `outputs/<today>/master.json`.
4. **Enrich contacts.** `/outreach <pipeline> enrich` — agent-browser
   crawls websites for emails + POCs. Resumable; writes
   `enrichment/website_crawl.json`. **Then run `merge_crawl_into_master.py`**
   so the next stages see crawled emails / POCs on each master lead:
   ```bash
   python outreach/lib/cli/merge_crawl_into_master.py <pipeline>
   ```
5. **Classify pain.** `/outreach <pipeline> classify` — dispatches the
   `pain-classifier` subagent against ≤3★ reviews from raw. Emits a
   sidecar at `enrichment/pain_classifications/<today>.json`.
6. **Merge sidecar into master.**
   ```bash
   python outreach/lib/cli/merge_classifications.py \
     --master  outreach/campaigns/<pipeline>/outputs/<today>/master.json \
     --sidecar outreach/campaigns/<pipeline>/enrichment/pain_classifications/<today>.json \
     --out     outreach/campaigns/<pipeline>/outputs/<today>/master.json
   ```
   Adds `agent_pain_hits` + recomputes `quality_score` / `weighted_pain`
   / `tier` from the new pain. `--master` and `--out` can be the same
   path (atomic write).
7. **Validate.** `/outreach <pipeline> validate` — annotates email/phone
   invalids via sibling flags. Required before handoff.
8. **Handoff.** `/outreach <pipeline> handoff` — produces
   `outputs/<today>/handoff.csv` for sales.
9. **(Optional) Owner lookup** for tier-A/B leads with empty `owner_name`:
   ```bash
   python outreach/lib/cli/owner_lookup.py <pipeline> --print-queue
   # fill enrichment/owner_lookups/<today>.json by hand from the printed queries
   python outreach/lib/cli/owner_lookup.py <pipeline> --apply
   ```
   Re-run handoff to pick up the owner columns.

**Re-delivery against an existing master?** See the "Re-delivery flow"
section in `.claude/commands/outreach.md`. Re-run `analyze.py
--output-date <new-date>` to write into a new dated folder; the prior
delivery stays as audit record.

## Daily driver

Each stage is a standalone CLI. Run them individually, or chain them
from a slash command / shell script. The slash-command runbook
(`.claude/commands/outreach.md`) is the planned orchestrator — it also
dispatches the `pain-classifier` subagent for the LLM-only stages.

```bash
source outreach/.venv/bin/activate

# Stages shipped as scripts (run in order for a fresh campaign):
python outreach/lib/cli/analyze.py               <pipeline> [--output-date YYYY-MM-DD] [--force]
python outreach/lib/cli/enrich.py                <pipeline> [--queue PATH] [--workers N]
python outreach/lib/cli/merge_crawl_into_master.py <pipeline> [--master PATH] [--crawl PATH]
# (classify is the only LLM stage — dispatched via /outreach <pipeline> classify)
python outreach/lib/cli/merge_classifications.py \
    --master  campaigns/<pipeline>/outputs/<today>/master.json \
    --sidecar campaigns/<pipeline>/enrichment/pain_classifications/<today>.json \
    --out     campaigns/<pipeline>/outputs/<today>/master.json
python outreach/lib/cli/validate.py              <pipeline> [--master PATH]
python outreach/lib/cli/handoff.py               <pipeline> [--master PATH] [--out PATH]
# Optional, post-handoff for tier-A/B leads:
python outreach/lib/cli/owner_lookup.py          <pipeline> --print-queue [--limit N] [--tiers A,B]
python outreach/lib/cli/owner_lookup.py          <pipeline> --apply

# Only stage still slash-command-only:
#   scrape   — wraps the gosom Docker scraper (skill at
#              .claude/skills/google-maps-scraper/SKILL.md)

# Run all unit tests
for t in $(find outreach/lib outreach/tests -name 'test_*.py' 2>/dev/null); do
    python "$t"
done

# Score the pain-classifier subagent against the gold set
# (1) Dispatch the `pain-classifier` subagent on
#     campaigns/dentist_sunbelt/eval/sample_unlabeled.json from your Claude
#     Code session and save its JSON output as predictions.json.
# (2) Run the metric script on the saved predictions:
python outreach/campaigns/dental_sunbelt/eval/eval_runner.py predictions.json
```

## Current state (2026-04-29)

- Dental campaign delivered (2026-04-25): 75 verified-email Tier A+B leads,
  173 independents in master, see
  `campaigns/dentist_sunbelt/outputs/2026-04-25/handoff.csv`.
- Sales feedback flagged two bugs:
  1. Pain quote ↔ category mismatch — solved by the `pain-classifier`
     Claude Code subagent (`.claude/agents/pain-classifier.md`) classifying
     reviews against the STL hierarchy in `silverthread/pain_categories.md`.
     Latest baseline on the 100-review gold set: main F1 0.784, strict
     (main, sub) F1 0.683, strict exact-match 0.64 — vs prior SBERT
     baseline of ~0.43. Eval harness: `campaigns/dentist_sunbelt/eval/eval_runner.py`.
  2. URLs had tracking-param noise.
     Fixed: `lib/url_normalize.py` + tests, wired through
     `lib/handoff/csv_builder.py` at output time. Cleaned URL replaces
     the raw value; the original is preserved in
     `<field>_raw` audit columns when normalization changed it.

## Tests

Unit tests live alongside their modules. Run all:

```bash
for t in $(find outreach/lib outreach/tests -name 'test_*.py' 2>/dev/null); do
    python "$t" 2>&1 | tail -2
done
```

Tests live alongside their modules under `outreach/lib/`.

## Adding a campaign

```bash
# 1. Pick / author a location
$EDITOR outreach/locations/myloc.yaml

# 2. Pick a vertical (or copy verticals/dentist/ to bootstrap a new one)

# 3. Create the campaign
mkdir -p outreach/campaigns/dentist_myloc
cat > outreach/campaigns/dentist_myloc/campaign.yaml <<EOF
vertical: dentist
location: myloc
slug: dentist_myloc
EOF

# 4. (optional) overrides.py for regional chains / tuned weights
$EDITOR outreach/campaigns/dentist_myloc/overrides.py

# 5. Generate queries
python outreach/lib/render_queries.py dentist_myloc

# 6. Drop raw NDJSONs into outreach/campaigns/dentist_myloc/raw/

# 7. Run the pipeline
python outreach/lib/cli/analyze.py dentist_myloc
```

## Adding a new vertical

1. Create `outreach/verticals/<v>/`:
   - `config.py` — pain weights, service map, enrich profile, vertical-wide
     `DSO_TITLE_REGEX` (`GEOGRAPHIC_PREFIXES_GENERIC` for category words
     like "family dental"), OSINT templates.
   - `query_templates.txt` — placeholder lines (`{vertical_keyword}`,
     `{city}`, `{state}`, `{neighborhood}`).
   - `README.md` — fit notes.
2. The pain taxonomy in `silverthread/pain_categories.md` is vertical-
   agnostic; only re-derive it when STL's service catalog changes.
3. Region-specific chain lists go in `campaigns/<v>_<loc>/overrides.py`
   as `DSO_TITLE_REGEX_EXTRA` / `DSO_EMAIL_DOMAINS_EXTRA`.
