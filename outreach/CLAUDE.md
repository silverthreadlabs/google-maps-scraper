# Outreach pipeline — agent rules

Lead-generation pipeline. See `outreach/README.md` for architecture,
daily-driver commands, and how to add a campaign.

## Repo shape

- `lib/` — industry-agnostic code. No vertical knobs, no hardcoded
  category names. Includes `lib/cli/` (CLI entry points for every
  pipeline stage) and `lib/campaign_config.py` (the merging loader).
- `verticals/<v>/config.py` — vertical template: pain weights,
  service map, DSO regex for vertical-wide chains, enrich profile,
  OSINT templates. Identical across every campaign in that vertical.
- `verticals/<v>/query_templates.txt` — placeholder query lines
  expanded by `lib/render_queries.py`.
- `locations/<loc>.yaml` — pure location data: cities, area codes,
  geographic prefixes (city/neighborhood names), country, locale.
- `campaigns/<v>_<loc>/campaign.yaml` — names the vertical + location.
- `campaigns/<v>_<loc>/overrides.py` — OPTIONAL per-campaign tweaks:
  PAIN_WEIGHTS override, DSO_TITLE_REGEX_EXTRA for regional chains,
  etc.
- `campaigns/<v>_<loc>/raw/` — raw scrape NDJSONs. **Immutable.**
- `campaigns/<v>_<loc>/enrichment/` — append-only sidecars (crawl,
  pain_classifications, osint, owner_lookups).
- `campaigns/<v>_<loc>/outputs/<date>/` — one folder per delivery.
- `silverthread/pain_categories.md` — STL-derived pain hierarchy
  (vertical-agnostic) consumed by the pain-classifier subagent.

To add a campaign:

1. Pick or author a location: `outreach/locations/<loc>.yaml`.
2. Pick a vertical (or copy `verticals/dentist/` to create a new one).
3. Create `outreach/campaigns/<v>_<loc>/campaign.yaml`:
   ```yaml
   vertical: <v>
   location: <loc>
   slug: <v>_<loc>
   ```
4. Generate queries: `python outreach/lib/render_queries.py <v>_<loc>`
5. Drop raw scrape NDJSONs into `campaigns/<v>_<loc>/raw/`.
6. Run the pipeline:
   `python outreach/lib/cli/analyze.py <v>_<loc>` etc.

If the campaign needs a regional chain list or tweaked PAIN_WEIGHTS,
create `campaigns/<v>_<loc>/overrides.py` with the appropriate
`DSO_TITLE_REGEX_EXTRA` / `DSO_EMAIL_DOMAINS_EXTRA` / `PAIN_WEIGHTS`
attributes — the loader merges them on top of the vertical defaults.

## Rules

### 1. Never drop rows or field values

- Keep every row even if unreachable today. Channel mix changes;
  deletion is irreversible work loss. Deduping by canonical identity
  (`place_id`) is fine — same row, not row removal.
- Add fields, never replace. Bad values get a sibling flag with reason
  (`email_invalid: true`, `email_invalid_reason: "smtp_bounce_550"`),
  never stripped. Every added field carries provenance: `<field>_source`
  and `<field>_added_at`.
- "Filter" means subset view in a new file, never mutation of the
  master.
- Scope: raw scrapes, hand-curated decision files, append-only
  sidecars. Re-running the analyzer over recomputable ranked files is
  fine.

### 2. Persist scraper output to `gmapsdata/` or `campaigns/<name>/raw/`, never `/tmp`

`/tmp` is auto-cleaned by systemd-tmpfiles. Re-scraping is expensive
and may yield different data due to listing churn. The raw JSON is
the most valuable artifact in the pipeline.

### 3. Read both review fields from the gosom scraper

Gosom output has `user_reviews` (~10% of captured reviews) and
`user_reviews_extended` (the `-extra-reviews` payload, ~90%). Reading
only `user_reviews` drops most of the pain signal. Merge both and
dedupe by `(reviewer_name, description[:120])`.

### 4. Crawler parallelism uses a session pool, not round-robin

Use `queue.Queue` to lease browser sessions per task. See
`lib/enrichers/website_crawl.py`.

### 5. Validators guard at boundaries, not downstream

`lib/validators/` rejects known false-positive classes. New
false-positive class? Add a guard + test there, not downstream.

### 6. Chain detection: split vertical-wide vs region-specific

- Vertical-wide brands → `verticals/<v>/config.py:DSO_TITLE_REGEX`.
- Region-specific brands → `campaigns/<c>/overrides.py:DSO_TITLE_REGEX_EXTRA`.
- Vertical-generic descriptors ("family dental") →
  `verticals/<v>/config.py:GEOGRAPHIC_PREFIXES_GENERIC`.
- City/neighborhood names → `locations/<loc>.yaml`.

The loader unions all of the above; tests live in
`lib/campaign_config_tests.py`.

## Workflow

- TDD for new logic. Project TDD rules: `outreach/TDD-RULES.md`.
- Run tests before declaring done:
  ```bash
  for t in $(find outreach/lib outreach/tests -name 'test_*.py' -o -name '*_tests.py' 2>/dev/null); do python "$t"; done
  ```
