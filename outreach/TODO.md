# Outreach TODO

Open work that doesn't belong in CLAUDE.md (auto-loaded) — read on demand.

## Resolved

- **URL tracking params in handoff CSV** (2026-04-30) —
  `lib/url_normalize.py` wired through `lib/handoff/csv_builder.py`
  via `apply_url_normalization()`. `website`, `google_maps_link`, and
  `website_redirect_target` get cleaned at output time; original is
  preserved in `<field>_raw` audit columns when normalization changed
  the value. Tests: `lib/handoff/tests/test_csv_builder.py`.
- **Pain quote ↔ category mismatch** — solved by the
  `.claude/agents/pain-classifier.md` subagent classifying reviews
  against `outreach/silverthread/pain_categories.md`. Eval harness:
  `pipelines/dental_sunbelt/eval/eval_runner.py`. Latest baseline
  (2026-04-29) on the 100-review gold set: main F1 0.784 / strict F1
  0.683 / strict exact-match 0.64 — vs prior SBERT baseline of ~0.43.
- **Pipeline integration of the subagent** — the slash-command runbook
  (`.claude/commands/outreach.md`) is the orchestrator. Classify dispatches
  pain-classifier in parallel batches; sidecar at
  `enrichment/pain_classifications/<date>.json`; `merge_classifications.py`
  grafts into master.
- **Re-key ranking + handoff to STL main names** (2026-05-01) — done as
  part of the SBERT→agent migration. All pipeline configs (`dental_sunbelt`,
  `retail_toronto`, `cosmetic_surgeons_dallas`) ship `PAIN_WEIGHTS` keyed by
  the new main names (`calls_unanswered`, `booking_friction`, …) matching
  what the subagent emits. csv_builder reads agent_pain_hits via
  `_pain_hits_field` and aggregates at the main level. Sub-level weight
  granularity isn't justified yet — needs ground-truth conversion data
  before per-sub tuning is more than a guess.
- **`merge_classifications.py` doesn't refresh `quality_score`** (2026-05-01)
  — patched. `merge()` now takes optional `pain_weights` and recomputes
  `quality_score` / `weighted_pain` / `tier` alongside the existing
  `pain_breadth` refresh. The CLI auto-derives the pipeline name from the
  `--master` path and pulls `PAIN_WEIGHTS` from `config.py`. Without this,
  agent-only pipelines (no legacy SBERT) shipped handoff CSVs ranked by
  `log10(reviews) + rating_gap` only.
- **Handoff CSV leaked validate-flagged junk via `all_emails` /
  `email_sources`** (2026-05-01) — patched. Both functions now skip
  entries present in `emails_invalid` (case-insensitive), matching
  `trustworthy_emails` / `best_email`. Master remains immutable; the
  audit trail stays intact, but sales no longer sees `*_1440x640@2x.png`
  hits in their CSV.
- **Pain quote truncation in classify** (2026-05-01) — patched. Classify
  stage stored `text[:300]` per the runbook; this lost detail and
  forced the LLM classifier to hedge on cut-off sentences. Runbook now
  prescribes full-text snippets; existing master patched in place.
- **`phone_normalized` column dropped from handoff** (2026-05-01) —
  unused by sales; column removed from `FIELDNAMES` and `_build_row`.
- **`analyze.py` script** (2026-05-01) — chain detection + initial quality
  scoring + email-ingest validation now lives at
  `outreach/scripts/analyze.py` (was three rounds of inline code across
  dental, retail, cosmetic). Validates incoming gosom-side emails through
  `validate_email` at ingest, partitioning into `emails` /
  `emails_invalid` so the master never carries image-artifact / placeholder
  / vendor-marketing addresses. Tests: `scripts/tests/test_analyze.py`.
- **`merge_crawl_into_master.py` script** (2026-05-01) — grafts
  `enrichment/website_crawl.json` into `outputs/<date>/master.json` via
  hostname join, with provenance per CLAUDE.md rule 1. Was inline in
  retail and cosmetic. Tests:
  `scripts/tests/test_merge_crawl_into_master.py`.
- **`owner_lookup.py` script (manual provider)** (2026-05-01) — bracketing
  the manual web-search step into `--print-queue` and `--apply` makes the
  flow idempotent (skip-if-`owner_name`) and provenance-clean. When an
  automated provider lands later, slot it behind `--print-queue` writing
  the sidecar; downstream interface is unchanged. Tests:
  `scripts/tests/test_owner_lookup.py`.
- **JS REJECT regex bypass** (2026-05-01) — the brittle in-browser
  filter regex (image extensions, vendor domains, placeholders, tracking
  pixel sub-domains) is gone from `EXTRACT_JS_TEMPLATE`. Filtering moved
  to Python via `lib/enrichers/website_crawl.filter_valid_emails` →
  `validate_email`, so we have a single canonical rule set instead of two
  ad-hoc lists drifting apart. Tests added in
  `lib/enrichers/tests/test_website_crawl.py`.
- **POC validator coverage — Dallas regression** (2026-05-01) — added
  `'why' / 'what' / 'when' / 'where' / 'how' / 'in'` to
  `SECTION_HEADING_OPENERS` and `'dr'` to `SECTION_HEADING_SECOND_TOKENS`.
  Catches `Contact Dr`, `About Dr`, `Why Dr`, `Meet Dr`, `What We`,
  `In The` — heading captures the crawler's extractor truncates to two
  tokens. 30 additional POCs flagged invalid on the cosmetic_surgeons_dallas
  master. Tests: `lib/validators/tests/test_poc.py`.
- **Westlake Dermatology DSO regex** (2026-05-01) — 21 TX-location
  regional chain that the cosmetic_surgeons_dallas DSO regex didn't
  catch on first run. Title regex + email-domain blocklist updated.

## Open

### Sales feedback loop

Wire sales-team disposition codes back into the master. Schema
proposal:

```json
"<place_id>": [{
  "disposition": "bounced" | "wrong_poc" | "replied_interested" |
                 "replied_not_interested" | "no_response_after_3" | "converted",
  "channel": "email" | "phone",
  "value":   "info@drjohnburns.com",  // the actual address/number that bounced
  "rep":     "alex",
  "at":      "2026-05-15T..."
}]
```

Append-only sidecar at `enrichment/sales_dispositions/<date>.json`.
Handoff would consume the latest disposition before generating the CSV
— surface `replied_interested` as priority, exclude `converted` /
`replied_not_interested`, mark `bounced` channels with a flag.

Open questions:
- How does sales actually return data? (CSV upload? Slack webhook? CRM?)
- Do we want disposition history per lead, or just latest-wins?
- Do `bounced` results auto-feed into the validators (domain blocklist
  for repeat-offender vendor domains, phone area-code blocklist)?

Needs a conversation with sales before building.

### Sub-level pain weight granularity (deferred)

Currently all subs under a main share the same weight in `PAIN_WEIGHTS`.
There's no evidence yet that `voicemail_never_returned` converts at a
different rate than `missed_calls_during_business_hours`. Once the
sales-feedback loop has shipped a few cohorts, run an analysis: which
`(main, sub)` pairs converted? If the variance is wide, re-key
`PAIN_WEIGHTS` to a `dict[tuple[str,str], int]` and tune. Until then,
keep it simple at the main level.

### Reactive-only chain detection

Today's chain detection is reactive — chains are added to a vertical's
`DSO_TITLE_REGEX` and `DSO_EMAIL_DOMAINS` only after they show up in a
scrape. Westlake Dermatology (21 TX locations) reached the cosmetic
master before we caught it; only the manual owner-lookup step surfaced
the chain status.

A multi-vertical chain registry would be cheaper than maintaining N
parallel regexes. Sketch:
- `outreach/lib/chain_registry.json` — a flat list of
  `{name, regex, email_domains, verticals: ['dental', 'cosmetic', ...]}`
- `ChainDetector` loads the union for the active vertical
- New chains get a single PR in one place; multi-vertical entries
  (national chains like Sono Bello, Aspen Dental) stop being
  duplicated across pipeline configs.

Defer until a 4th vertical lands and the duplication actually bites.

### `extruct`-based JSON-LD email pull

The current extractor walks `<script type="application/ld+json">`
manually inside the JS template (`ldPersons` array). [`extruct`][1] is
a maintained Python lib that handles JSON-LD, microdata, RDFa, and
OpenGraph in one pass. Could replace the JS-side JSON-LD walk and pick
up structured-data emails (`schema.org/Person.email`,
`schema.org/Organization.email`) more robustly than our regex.

Defer until we see real evidence of missed emails on practice sites
that ship structured data — most don't.

  [1]: https://github.com/scrapinghub/extruct
