# Outreach pipeline — agent rules

Lead-generation pipeline. See `outreach/README.md` for architecture,
daily-driver commands, and how to add a vertical.

## Repo shape

- `lib/` — industry-agnostic. No vertical knobs, no hardcoded category names.
- `pipelines/<name>/config.py` — every vertical-specific knob: pain
  categories, regex patterns, SBERT anchors, DSO list, service catalog,
  ranking weights, metro area codes.
- `pipelines/<name>/raw/` — raw scrape NDJSONs. **Immutable.** Canonical.
- `pipelines/<name>/enrichment/` — append-only sidecars (crawl outputs).
- `pipelines/<name>/outputs/<date>/` — one folder per delivery.

To add a vertical: copy `pipelines/dental_sunbelt/`, edit `config.py`,
drop new query files in `queries/`. Do not fork `lib/`.

## Rules

### 1. Never drop rows or field values

- Keep every row even if unreachable today. Channel mix changes; deletion
  is irreversible work loss. Deduping by canonical identity (`place_id`)
  is fine — same row, not row removal.
- Add fields, never replace. Bad values get a sibling flag with reason
  (`email_invalid: true`, `email_invalid_reason: "smtp_bounce_550"`),
  never stripped. Every added field carries provenance: `<field>_source`
  and `<field>_added_at`.
- "Filter" means subset view in a new file, never mutation of the master.
- Scope: raw scrapes, hand-curated decision files, append-only sidecars.
  Re-running the analyzer over recomputable ranked files is fine.

### 2. Persist scraper output to `gmapsdata/` or `pipelines/<name>/raw/`, never `/tmp`

`/tmp` is auto-cleaned by systemd-tmpfiles. Re-scraping is expensive and
may yield different data due to listing churn. The raw JSON is the most
valuable artifact in the pipeline.

### 3. Read both review fields from the gosom scraper

Gosom output has `user_reviews` (~10% of captured reviews) and
`user_reviews_extended` (the `-extra-reviews` payload, ~90%). Reading
only `user_reviews` drops most of the pain signal — Google buries
low-rated reviews after position ~10. Merge both and dedupe by
`(reviewer_name, description[:120])`.

### 4. Crawler parallelism uses a session pool, not round-robin

Use `queue.Queue` to lease browser sessions per task — each task pops,
runs, returns. Do not assign by index: concurrent tasks then share
session state and contaminate each other's records. See
`lib/enrichers/website_crawl.py`.

### 5. Validators guard at boundaries, not downstream

`lib/validators/` rejects known false-positive classes: street-suffix
`Dr.` ("Hancock Dr"), placeholder/image/vendor emails (`user@domain.com`,
`fancybox_sprite@2x.png`, vendor domains like `gargle.com`). When you
find a new false-positive class, add a guard + test there, not downstream.

### 6. Chain detection: populate `GEOGRAPHIC_PREFIXES` per vertical

Same-metro practices share name prefixes ("Chandler Dental Arts" vs
"Chandler Dental Excellence" — different practices, not a chain).
`lib/chain_detection.py` excludes brand-prefix repeats listed in
`GEOGRAPHIC_PREFIXES` (in each vertical's `config.py`). When adding a
new vertical or metro, populate this set or auto-chain by brand-prefix
will false-positive.

## Workflow

- TDD for new logic. Project TDD rules: `outreach/TDD-RULES.md`.
- Run tests before declaring done:
  `for t in outreach/lib/validators/tests/test_*.py outreach/lib/test_*.py; do python "$t"; done`
