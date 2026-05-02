---
description: Run an outreach pipeline stage for a vertical (analyze / classify / enrich / validate / handoff / owner-lookup). Dispatches the pain-classifier subagent for classify; delegates to outreach/scripts/* for every other stage.
---

The user invoked `/outreach $ARGUMENTS`.

# /outreach — pipeline runbook

## Args

`$ARGUMENTS` is `<pipeline> [stage]`.

- **pipeline** (required) — directory under `outreach/pipelines/`, e.g. `dental_sunbelt`.
- **stage** (optional) — one of:
  `analyze | classify | enrich | validate | handoff | owner-lookup`.
  If omitted, ask the user which stage to run; do not default.

## Standard pipeline order

For a fresh campaign:

```
scrape → analyze → enrich → merge-crawl → classify → validate → handoff
                                                         ↓
                                                    owner-lookup (optional)
                                                         ↓
                                                    re-run handoff
```

`scrape` uses the `google-maps-scraper` skill (not a stage of /outreach).
`merge-crawl` happens automatically after `enrich` runs successfully — it's
not a separate user-facing stage.

## Pre-flight (always do first)

1. Verify `outreach/pipelines/<pipeline>/` exists. If not, error and stop:
   `error: pipeline not found at outreach/pipelines/<pipeline>/`
2. Verify the pipeline config imports cleanly:
   `python -c "import sys; sys.path.insert(0,'outreach'); from pipelines.<pipeline> import config"`
   If it errors, surface the import error and stop.
3. Echo what you're about to do: `running /outreach <pipeline> <stage>`.

## Hard rules (apply to every stage)

These mirror `outreach/CLAUDE.md` rules — restated here in case the runbook
is invoked cold.

1. **Never drop rows or replace field values.** Add fields with
   `<field>_source` and `<field>_added_at`. Mark bad values invalid via
   sibling flags (`phone_invalid: true`, never strip the phone).
2. **Output paths.** Inputs/outputs live under
   `outreach/pipelines/<pipeline>/{raw,enrichment,outputs/<date>}/`.
   New deliveries go to a NEW ISO-dated folder under `outputs/`. Never
   overwrite an existing dated folder — if today's folder already exists
   from an earlier run, ask the user whether to use it or create a
   `<date>-2/` sibling.
3. **Pain-key contract.** `SERVICE_MAP` and `PAIN_WEIGHTS` in pipeline
   `config.py` are keyed by the STL hierarchy main names
   (`calls_unanswered`, `booking_friction`, …) — same keys the
   pain-classifier subagent emits as `hit['main']`. Look up by
   `pain_weights[hit['main']]` / `service_map[hit['main']]`. Sub-level
   weight granularity is intentionally deferred (see TODO.md) — don't
   key by `(main, sub)`.
4. **Reviews source.** When reading lead reviews, merge BOTH
   `user_reviews` (~10%) and `user_reviews_extended` (~90%); dedupe by
   `(reviewer_name, description[:120])`. Reading only `user_reviews`
   drops most of the pain signal (CLAUDE.md rule 3).

---

## Stage: analyze

Delegates to `outreach/scripts/analyze.py`. Builds the **initial**
`outputs/<date>/master.json` from raw scrape NDJSON(s) — dedupe by
`place_id`, chain detection, ingest-time email validation, initial
quality_score (pain-empty until classify runs).

**Required pipeline config:** `PAIN_WEIGHTS`, `DSO_TITLE_REGEX`,
`DSO_EMAIL_DOMAINS`, `GEOGRAPHIC_PREFIXES`. Optional:
`VENDOR_DOMAINS_EXTRA`, `METROS`.

```bash
python outreach/scripts/analyze.py <pipeline> [--output-date YYYY-MM-DD] [--force]
```

**Inputs:** every `*.json` NDJSON under `pipelines/<pipeline>/raw/`.

**Output:** `outputs/<today-UTC>/master.json` (refuses to overwrite
without `--force`; pass `--output-date <date>` to write into a different
folder when today's already has a master).

**Side effect — email-ingest hardening:** every incoming gosom-side email
is run through `lib.validators.email.validate_email`. RFC-shape-valid +
non-vendor + non-placeholder addresses go to `lead.emails`; rejects go to
`lead.emails_invalid` with a reason. Image-artifact filenames like
`shutterstock_x_1440x640@2x.png` never pollute `lead.emails`. CLAUDE.md
rule 1 preserved — nothing is dropped, just routed to the right field.

**When to use:**
- Cold start: fresh raw scrape, no master yet.
- Re-analyze: after taxonomy / chain regex changes that affect chain
  flagging or quality_score baselines (use `--output-date` to write a
  new dated folder; the prior delivery is the audit record).

**`next:`** `/outreach <pipeline> enrich` (or `classify` first if you
want pain-aware ranking before crawling).

---

## Stage: classify

The LLM-only stage. Dispatches the `pain-classifier` Claude Code subagent
against a curated lead subset.

**When to use:** classifying fresh raw scrapes for the first time, OR
re-classifying an existing master after the taxonomy/agent changes.

**Required pipeline config:** none — the classify stage reads the
taxonomy from `outreach/silverthread/pain_categories.md` directly.

**Output:** a sidecar at
`outreach/pipelines/<pipeline>/enrichment/pain_classifications/<today>.json`,
keyed by `place_id`, in the exact shape `merge_classifications.py`
expects (see step 5 below).

### Procedure

1. **Locate the sources.** Two distinct sources, do not conflate:
   - **Lead-selection source** — drives *which* leads to classify.
     Default: latest `outputs/<date>/master.json` (rich aggregate fields
     like `quality_score`, `tier`). If no master exists yet, the raw
     NDJSONs become the selection source — dedupe by `place_id`.
   - **Reviews source** — ALWAYS the raw NDJSONs at
     `pipelines/<pipeline>/raw/*.json`. Master is post-aggregation and
     may have dropped `user_reviews{,_extended}` already. Never read
     reviews from master. Index raw by `place_id`.
   - **Place_id backfill (degenerate-master fallback).** If the master
     lacks `place_id` on its leads (early scrapes did this), join
     master ↔ raw by `(title, metro)` to attach place_id onto a working
     copy in memory. Print the join stats (`matched: X / Y, ambiguous: Z,
     unmatched: W`) and refuse to proceed if more than ~5% are unmatched
     — silent unmatches mean missing classifications later. *(Long-term
     fix: regenerate master from raw with `place_id` preserved — TODO.md.)*
2. **Pick the subset to classify.** Ask the user:
   *"How many leads to classify? (default proposal: top-N by quality_score
   if a master exists, otherwise all leads in the raw scrape)"*
   Confirm the lead count before dispatching anything.
3. **Build the review index + batches.** Walk the selected leads:
   - For each `place_id`, look up the lead in raw and merge
     `user_reviews` + `user_reviews_extended` (CLAUDE.md rule 3).
   - **Normalize review-field keys.** Raw scrapes use capitalized
     keys (`Description`, `Rating`, `Name`, `When`); some downstream
     scrapes use lowercase (`description`, `rating`, `reviewer_name`).
     Read both shapes:
     ```python
     text     = rev.get('description') or rev.get('Description') or ''
     rating_s = rev.get('rating')      or rev.get('Rating')      or ''
     reviewer = rev.get('reviewer_name') or rev.get('Name')      or ''
     try:    rating = int(rating_s)
     except: rating = None
     ```
     Skip reviews where `text` is empty.
   - Dedupe by `(reviewer, text[:120])`.
   - Filter to `rating <= 3` (pain signal is concentrated there;
     `rating is None` → keep, the agent can still classify on text).
   - Assign each surviving review a globally unique integer `id`
     (sequential, 0..N-1).
   - Maintain a parallel index in memory:
     `review_index[id] = {place_id, rating, reviewer, snippet}`
     where `snippet = text` (the **FULL** review text — never truncate;
     sales reads these in the handoff CSV verbatim, and the classifier
     benefits from full context). The merge step joins on this.
   - Subagent input row shape: `{id: <int>, text: <full review text>}`.
     Do not cap input length; the agent should see the entire review.
   Group review rows into batches of **20–40 reviews per batch** (not per
   lead — reviews; a single 40-review practice fills one batch).
4. **Dispatch — all batches in ONE message, in parallel.**
   In a single assistant message, emit one Agent tool-use block per
   batch (4–8 batches per message is reasonable; the runtime parallelizes
   them). Don't await one batch before sending the next — they're
   independent. For each Agent block:
   - `subagent_type: "pain-classifier"`
   - `prompt`: tell the subagent to read
     `outreach/silverthread/pain_categories.md` first, then classify each
     review per its agent definition. Pass the batch JSON verbatim.
5. **Build the sidecar.** Concatenate the batch outputs (each is a list
   of `{id, categories: [{main, sub, confidence, quote, reasoning}]}`),
   then for each `(id, category)` join via the review_index and emit
   into the sidecar dict. Output schema (matches
   `scripts/merge_classifications.py`'s SIDECAR SCHEMA):
   ```json
   {
     "<place_id>": {
       "<main>": [
         {
           "sub":        "missed_calls_during_business_hours",
           "confidence": 0.88,
           "snippet":    "I called five times…",          // ← from review_index, NOT from `quote`
           "rating":     1,                                // ← from review_index
           "reviewer":   "Jane D",                         // ← from review_index
           "reasoning":  "direct phone-unreachable language"
         }
       ]
     }
   }
   ```
   Field-name discipline: csv_builder reads `snippet`/`rating`/`reviewer`,
   so use those names. The subagent's `quote` is the verbatim span;
   we use the review_index's `snippet` (FULL review text — see step 3) as
   the CSV-bound copy. Both can be preserved if you'd rather; minimum
   required is `snippet`.

   Write atomically (temp + rename). If the file exists from an earlier
   run today, write to `<today>-2.json` rather than overwriting — the
   prior run is the audit record (CLAUDE.md rule 1).
6. **Stratified spot-check.** Quality gate before declaring done:
   - Sample size: `max(10, round(0.10 * total_hits))`.
   - **Stratify by main**: every main category that fired contributes at
     least one sample (so the long tail isn't hidden behind the most
     populous main).
   - For each sampled hit, print: `(main, sub, confidence) — "<snippet>"`.
   - Compute mean confidence across ALL hits (not just the sample).
     If `< 0.6`, flag it loudly: the agent is hedging more than usual.
   - Then ask the user explicitly: *"these hits look right — proceed,
     retry classify, or abort?"* Don't infer "looks fine" from your
     own read.

   Current baseline (2026-04-29 gold set, 100 reviews):
   main F1 = 0.784, strict (main, sub) F1 = 0.683. Mean confidence on
   that run was ≈0.78. A new run with mean confidence noticeably below
   that, or with obvious category mismatches in the sample, is the
   failure mode the gate is meant to catch.
7. **Echo summary:** `classified <n> leads (<m> hits across <k> mains) → <sidecar-path>`
   plus `next: python outreach/scripts/merge_classifications.py --master <…> --sidecar <sidecar> --out <new-master>`.

---

## Stage: enrich

Delegates to `outreach/scripts/enrich.py`.

**Required pipeline config:** `ENRICH_PROFILE` (the dataclass shape is
documented in `outreach/lib/enrichers/website_crawl.py:EnrichProfile`).

```bash
python outreach/scripts/enrich.py <pipeline> [--queue PATH] [--workers N]
```

**Default queue:** `pipelines/<pipeline>/enrichment/crawl_queue.json`.
If the queue doesn't exist, ask the user which leads to enrich (likely
top-N from the latest master) and write the queue file before invoking
the script.

**Output:** `enrichment/website_crawl.json` (resumable: skips leads
already in the file) and `enrichment/website_crawl_retry.json`
(failures to retry with Playwright MCP).

### Auto-follow: graft crawl results into master

Once `enrich` finishes, **always run** `merge_crawl_into_master.py` so
the next stages (validate, classify, handoff) see crawled emails / POCs
on each lead. Skipping this leaves `crawled_emails` empty in the master
even though `website_crawl.json` is full of data.

```bash
python outreach/scripts/merge_crawl_into_master.py <pipeline> \
  [--master PATH] [--crawl PATH]
```

Defaults: latest `outputs/<date>/master.json` and
`enrichment/website_crawl.json`. Joins by hostname (the queue is
deduped by hostname, so a multi-listing single practice gets the same
crawl payload across all its master rows). Adds `crawled_emails` /
`crawled_emails_source` / `crawled_socials` / `pocs` / `crawl_status`
/ `crawl_pages_visited` with provenance per CLAUDE.md rule 1. Leads
whose hostname has no crawl row get `crawl_attempted: False` (so
consumers can distinguish "we crawled and got nothing" from "we
never crawled it").

Filtering note: emails returned in `website_crawl.json` are already
run through `lib.enrichers.website_crawl.filter_valid_emails`, which
drops image-artifact / vendor-domain / placeholder hits using the
canonical `validate_email`. The validate stage flags any survivors
that the crawl-time filter missed.

---

## Stage: validate

Delegates to `outreach/scripts/validate.py`.

**Required pipeline config:** `METRO_AREA_CODES` (for the metro-mismatch
phone check). `VENDOR_DOMAINS_EXTRA` is optional — extends the lib's
generic vendor reject set with vertical-specific marketing vendors.

```bash
python outreach/scripts/validate.py <pipeline> [--master PATH]
```

Defaults to the latest `outputs/<date>/master.json`. Appends sibling
flags for invalid emails (`emails_invalid: list[{email, reason}]`,
deduped by email), for the phone (`phone_invalid: bool`,
`phone_invalid_reason: str`), and for each POC (`pocs[*].invalid: bool`,
`pocs[*].invalid_reason: str` — set in-place on the POC dict; raw `name`
preserved). Atomic write-back. Never drops rows.

**Always run validate before handoff** — handoff reads the sibling
flags. Skipping validate produces a CSV with `phone_invalid: None`
(string "None" in the cell), missing email-invalid counts, and POCs
that include section-heading captures like "MEET THE" or "Our Founder"
in the `pocs` column.

---

## Stage: handoff

Delegates to `outreach/scripts/handoff.py`.

**Required pipeline config:** `PAIN_WEIGHTS`, `SERVICE_MAP`. Both are
keyed by the new STL hierarchy main names (`calls_unanswered`,
`booking_friction`, …) — same keys the classify stage and
`csv_builder._pain_hits_field` use.

```bash
python outreach/scripts/handoff.py <pipeline> [--master PATH] [--out PATH]
```

Defaults: read latest `outputs/<date>/master.json`, write
`handoff.csv` next to it.

**For a re-delivery** (regenerated master with normalized URLs / new
classifier output), use `--out` to write into a NEW dated folder so
the prior delivery is preserved:
```bash
python outreach/scripts/handoff.py <pipeline> \
  --master outreach/pipelines/<pipeline>/outputs/<new-date>/master.json \
  --out    outreach/pipelines/<pipeline>/outputs/<new-date>/handoff.csv
```

---

## Stage: owner-lookup (optional, post-handoff)

Decision-maker enrichment for tier-A/B leads where `owner_name` is empty.
Backed by `outreach/scripts/owner_lookup.py` — manual web-search provider
behind a script-shaped interface so the flow is idempotent and
provenance-clean.

**Two-step flow:**

```bash
# 1. Print the queue — eligible leads (tier A/B, no owner yet, sorted
#    by quality_score). Each entry shows a ready-to-paste search query
#    and the place_id you'll need for the sidecar.
python outreach/scripts/owner_lookup.py <pipeline> --print-queue \
  [--limit N] [--tiers A,B] [--master PATH]

# 2. Web-search each query (LinkedIn, practice "About" pages, RealSelf,
#    state board listings). Write the sidecar by hand at
#    `enrichment/owner_lookups/<today-UTC>.json`:
#    {"<place_id>": {"name": "...", "title": "...", "linkedin": "..."}}

# 3. Apply — patches master in place with owner_name / owner_title /
#    owner_linkedin + provenance (`owner_source: 'web_search_linkedin'`,
#    `owner_added_at`). Skips leads already carrying owner_name (idempotent).
python outreach/scripts/owner_lookup.py <pipeline> --apply \
  [--sidecar PATH] [--master PATH]
```

After `--apply`, **re-run handoff** so the CSV picks up the new owner
columns: `/outreach <pipeline> handoff`.

**Skip owner-lookup when:**
- Handoff is tier-D-heavy (low conversion ceiling, not worth the lift)
- The vertical's pitch works without a named POC (mass `info@` outreach)
- You're testing the pipeline, not shipping to sales

**When an automated provider lands** (LinkedIn API, paid people-search),
slot it behind `--print-queue` writing the sidecar from search results;
the `--apply` interface stays unchanged.

---

## Stages not yet supported as scripts

- **scrape** — use the `google-maps-scraper` skill
  (`.claude/skills/google-maps-scraper/SKILL.md`). Output goes to
  `outreach/pipelines/<pipeline>/raw/<query>.json`. Don't write to
  `/tmp` (CLAUDE.md rule 2). After scrape, run `analyze` to build the
  initial master.

---

## Re-delivery flow

When you need to regenerate a delivery — new classifier output, URL
normalization fixes, schema migration — write into a NEW dated folder
so the prior delivery stays intact (CLAUDE.md rule 1). Sequence:

0. **Re-build the master from raw** (one-time when the existing master
   is degenerate, e.g. lacks `place_id`):
   ```bash
   python outreach/scripts/analyze.py <pipeline> --output-date <new-date>
   ```
   This dedupes raw by `place_id`, runs chain detection, scores leads,
   and partitions gosom-side emails into `emails` vs `emails_invalid`.
   Refuses to overwrite an existing dated folder unless you pass
   `--force`.

1. `/outreach <pipeline> classify` against the new master — emits the
   sidecar at `enrichment/pain_classifications/<new-date>.json`.
   `merge_classifications.py` joins on `place_id`, so the master fed to
   merge MUST carry it (analyze guarantees this).

2. **Merge sidecar (refreshes quality_score + tier alongside breadth):**
   ```bash
   python outreach/scripts/merge_classifications.py \
     --master  outreach/pipelines/<pipeline>/outputs/<new-date>/master.json \
     --sidecar outreach/pipelines/<pipeline>/enrichment/pain_classifications/<new-date>.json \
     --out     outreach/pipelines/<pipeline>/outputs/<new-date>/master.json
   ```
   The CLI auto-derives the pipeline name from the master path and
   pulls `PAIN_WEIGHTS` from `config.py` so `quality_score`,
   `weighted_pain`, and `tier` get recomputed on agent_pain_hits.
   Inspect the orphan-place_ids stat: nonzero usually means classify
   ran against a different master than this one.

3. (If you want crawl data) `/outreach <pipeline> enrich` against the
   new master, then `merge_crawl_into_master.py` to graft.

4. `/outreach <pipeline> validate` — annotates the new master.

5. `/outreach <pipeline> handoff` (defaults to latest dated folder; pass
   `--master` / `--out` to be explicit).

6. (Optional) `/outreach <pipeline> owner-lookup` for tier-A/B leads
   with empty `owner_name`, then re-run handoff.

7. Compare lead counts and tier distribution to the prior delivery
   before declaring done. Big shifts in tier mix usually mean the
   classifier's category re-mapping changed which pains drive ranking
   — surface to the user before shipping to sales.

---

## Final hand-off (always end with this)

After the stage completes, write a 3-line summary the user can paste
into status updates:

- **what ran** — stage + pipeline + key counts
- **what it produced** — file paths and row counts
- **what's next** — the natural follow-up command (e.g.
  "validate next, then handoff")
