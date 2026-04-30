---
description: Run an outreach pipeline stage for a vertical (classify / enrich / validate / handoff). Dispatches the pain-classifier subagent for classify; delegates to outreach/scripts/* for the deterministic stages.
---

The user invoked `/outreach $ARGUMENTS`.

# /outreach — pipeline runbook

## Args

`$ARGUMENTS` is `<pipeline> [stage]`.

- **pipeline** (required) — directory under `outreach/pipelines/`, e.g. `dental_sunbelt`.
- **stage** (optional) — one of: `classify | enrich | validate | handoff`.
  If omitted, ask the user which stage to run; do not default.

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
3. **Pain-key gotcha.** `SERVICE_MAP` and `PAIN_WEIGHTS` in pipeline
   `config.py` are still keyed by the legacy flat category names
   (`missed_calls_unreachable`, `surprise_billing`, etc.). The
   `pain-classifier` subagent emits `(main, sub)` tuples against the STL
   hierarchy. Until the re-key lands (TODO.md), look up by
   `pain_weights[hit['main']]` / `service_map[hit['main']]`. **Never
   key by `(main, sub)` against the current dicts — KeyError.**
4. **Reviews source.** When reading lead reviews, merge BOTH
   `user_reviews` (~10%) and `user_reviews_extended` (~90%); dedupe by
   `(reviewer_name, description[:120])`. Reading only `user_reviews`
   drops most of the pain signal (CLAUDE.md rule 3).

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
     where `snippet = text[:300]`. The merge step joins on this.
   - Subagent input row shape: `{id: <int>, text: <review text>}`.
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
   we use the review_index's `snippet` (full ≤300-char excerpt) as
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
deduped by email) and for the phone (`phone_invalid: bool`,
`phone_invalid_reason: str`). Atomic write-back. Never drops rows.

**Always run validate before handoff** — handoff reads the sibling
flags. Skipping validate produces a CSV with `phone_invalid: None`
(string "None" in the cell) and missing email-invalid counts.

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

## Stages not yet supported as scripts

- **scrape** — use the `google-maps-scraper` skill (`.claude/skills/google-maps-scraper/SKILL.md`).
  Output goes to `outreach/pipelines/<pipeline>/raw/<query>.json`. Don't
  write to `/tmp` (CLAUDE.md rule 2).
- **analyze (chain detection + quality scoring)** — currently inline.
  After classify produces a sidecar, walk
  `lib/chain_detection.ChainDetector` over the leads (using the
  pipeline's `DSO_TITLE_REGEX`, `DSO_EMAIL_DOMAINS`,
  `GEOGRAPHIC_PREFIXES`), compute `quality_score` via
  `lib/ranking.quality_score(pain_hits, review_count, rating, pain_weights=...)`,
  and write `outputs/<date>/master.json`. Will become a script when a
  second vertical lands.

---

## Re-delivery flow (the dental case)

The 2026-04-25 dental delivery needs URL normalization fixes and
agent-classified pain quotes (TODO.md). The 2026-04-25 master is also
*degenerate* — it lacks `place_id` on its leads — so a place_id-backfill
step is required before classify. Sequence:

0. **Backfill place_id onto a working master** (one-time, while master
   regeneration from raw is still TODO). Build a new working master at
   `outputs/<today>/master.json` whose leads carry `place_id` (joined
   from raw NDJSON by `(title, metro)`). Print join stats and refuse if
   unmatched > 5%. `merge_classifications.py` joins on `place_id`, so
   the master fed to merge MUST carry it.
1. `/outreach dental_sunbelt classify` against the working master — emits
   the sidecar at `enrichment/pain_classifications/<today>.json`.
2. **Merge sidecar into the working master:**
   ```bash
   python outreach/scripts/merge_classifications.py \
     --master  outreach/pipelines/dental_sunbelt/outputs/<today>/master.json \
     --sidecar outreach/pipelines/dental_sunbelt/enrichment/pain_classifications/<today>.json \
     --out     outreach/pipelines/dental_sunbelt/outputs/<today>/master.json
   ```
   Adds `agent_pain_hits` + provenance to every lead. Existing
   `pain_hits` (legacy SBERT) stays untouched — the audit trail.
   Inspect the orphan-place_ids stat: nonzero usually means classify
   ran against a different master than this one. (`--master` and `--out`
   can be the same path; `merge_classifications.py` writes atomically.)
3. `/outreach dental_sunbelt validate` — annotates the new master.
4. `/outreach dental_sunbelt handoff` with explicit `--master` and
   `--out` pointing at `outputs/<today>/`.
5. Compare lead counts and tier distribution to the prior delivery
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
