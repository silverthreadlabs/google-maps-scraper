---
name: outreach-pipeline
description: "Run or guide an outreach pipeline stage for a vertical: analyze, classify, enrich, validate, handoff, or owner-lookup. Use when the user asks for /outreach, outreach pipeline execution, campaign delivery, pain classification sidecars, crawl enrichment, validation, handoff CSVs, or owner lookup."
---

# Outreach Pipeline

This is the Codex port of `.claude/commands/outreach.md`.

Original Claude command description: run an outreach pipeline stage for a vertical (`analyze` / `classify` / `enrich` / `validate` / `handoff` / `owner-lookup`). Dispatches the `pain-classifier` subagent for `classify`; delegates to `outreach/scripts/*` for every other stage.

Use this skill for the Silverthread Labs outreach pipeline under `outreach/`. The old Claude slash command was `/outreach <pipeline> [stage]`; in Codex, treat the same wording as a request to use this skill.

The Claude runbook starts with: `The user invoked /outreach $ARGUMENTS`.

## Arguments

`$ARGUMENTS` is:

```text
<pipeline> [stage]
```

- `pipeline`: directory under `outreach/pipelines/`, for example `dental_sunbelt`.
- `stage`: one of `analyze`, `classify`, `enrich`, `validate`, `handoff`, `owner-lookup`.

If `stage` is omitted, ask which stage to run. Do not default.

## Standard Order

```text
scrape -> analyze -> enrich -> merge-crawl -> classify -> validate -> handoff
                                                        |
                                                        v
                                                  owner-lookup
                                                        |
                                                        v
                                                   re-run handoff
```

`scrape` uses the `google-maps-scraper` skill and is not an outreach stage. `merge-crawl` runs automatically after a successful `enrich`.

## Preflight

Always do these checks first:

1. Verify `outreach/pipelines/<pipeline>/` exists. If not, stop with `error: pipeline not found at outreach/pipelines/<pipeline>/`.
2. Verify the pipeline config imports cleanly:

   ```bash
   python -c "import sys; sys.path.insert(0,'outreach'); from pipelines.<pipeline> import config"
   ```

3. Echo what you are about to do: `running /outreach <pipeline> <stage>`.

## Hard Rules

- These mirror `outreach/CLAUDE.md` rules and are restated here in case the runbook is invoked cold.
- Never drop rows or replace field values. Add new fields with `<field>_source` and `<field>_added_at`. Mark invalid values with sibling flags such as `phone_invalid: true`; never strip the phone.
- Inputs and outputs live under `outreach/pipelines/<pipeline>/{raw,enrichment,outputs/<date>}/`.
- New deliveries go to a new ISO-dated folder under `outputs/`. Do not overwrite an existing dated folder. If today's folder already exists, ask whether to use it or create a `<date>-2/` sibling.
- Pain-key contract. `SERVICE_MAP` and `PAIN_WEIGHTS` in pipeline `config.py` are keyed by STL hierarchy main names such as `calls_unanswered` and `booking_friction`; these are the same keys the `pain-classifier` subagent emits as `hit['main']`. Look up by `pain_weights[hit['main']]` / `service_map[hit['main']]`. Sub-level weight granularity is intentionally deferred; see `TODO.md`. Do not key by `(main, sub)`.
- Reviews source. When reading lead reviews, merge both `user_reviews` and `user_reviews_extended`, then dedupe by `(reviewer_name, description[:120])`. Reading only `user_reviews` drops most of the pain signal; see `CLAUDE.md rule 3`.

## Stage: analyze

Delegates to `outreach/scripts/analyze.py`. Builds the initial `outputs/<date>/master.json` from raw scrape NDJSON files: dedupe by `place_id`, chain detection, ingest-time email validation, initial `quality_score` with pain empty until classify runs.

Required pipeline config: `PAIN_WEIGHTS`, `DSO_TITLE_REGEX`, `DSO_EMAIL_DOMAINS`, `GEOGRAPHIC_PREFIXES`. Optional: `VENDOR_DOMAINS_EXTRA`, `METROS`.

```bash
python outreach/scripts/analyze.py <pipeline> [--output-date YYYY-MM-DD] [--force]
```

Inputs are every `*.json` NDJSON under `pipelines/<pipeline>/raw/`.

Output is `outputs/<today-UTC>/master.json`; the script refuses to overwrite without `--force`. Pass `--output-date <date>` to write into a different folder when today's folder already has a master.

Side effect - email-ingest hardening: every incoming gosom-side email is run through `lib.validators.email.validate_email`. RFC-shape-valid, non-vendor, non-placeholder addresses go to `lead.emails`; rejects go to `lead.emails_invalid` with a reason. Image-artifact filenames like `shutterstock_x_1440x640@2x.png` never pollute `lead.emails`. `CLAUDE.md rule 1` is preserved: nothing is dropped, just routed to the right field.

Use this for fresh raw scrapes or when taxonomy, chain regex, or scoring changes require rebuilding the master.

`next:` `/outreach <pipeline> enrich` or `classify` first if you want pain-aware ranking before crawling.

## Stage: classify

The LLM-only stage. Dispatches the `pain-classifier` Claude Code subagent against a curated lead subset in the original Claude workflow.

Codex note: preserve the original runbook's `pain-classifier` subagent contract exactly. In this Codex environment, only spawn subagents when the user explicitly asks for subagents, delegation, or parallel agent work. Otherwise use the `pain-classifier` skill locally with the same batch schema.

When to use: classifying fresh raw scrapes for the first time, or re-classifying an existing master after taxonomy or agent changes.

Required pipeline config: none. The classify stage reads the taxonomy from `outreach/silverthread/pain_categories.md` directly.

Output: a sidecar at:

```text
outreach/pipelines/<pipeline>/enrichment/pain_classifications/<today>.json
```

The sidecar is keyed by `place_id`, in the exact shape `merge_classifications.py` expects.

Procedure:

1. Locate the sources. There are two distinct sources; do not conflate them:
   - Lead-selection source: drives which leads to classify. Default is latest `outputs/<date>/master.json` with rich aggregate fields like `quality_score` and `tier`. If no master exists yet, the raw NDJSONs become the selection source, deduped by `place_id`.
   - Reviews source: always the raw NDJSONs at `pipelines/<pipeline>/raw/*.json`. Master is post-aggregation and may have dropped `user_reviews{,_extended}` already. Never read reviews from master. Index raw by `place_id`.
   - Place_id backfill, degenerate-master fallback: if the master lacks `place_id` on its leads, join master to raw by `(title, metro)` to attach `place_id` onto a working copy in memory. Print join stats: `matched: X / Y, ambiguous: Z, unmatched: W`. Refuse to proceed if more than about 5 percent are unmatched. Long-term fix: regenerate master from raw with `place_id` preserved; see `TODO.md`.
4. Ask how many leads to classify. Default proposal: top-N by `quality_score` if a master exists, otherwise all raw leads. Confirm the count before classifying.
5. For each selected lead, merge `user_reviews` and `user_reviews_extended`. Read both lowercase and capitalized review keys: `description`/`Description`, `rating`/`Rating`, `reviewer_name`/`Name`.
6. Skip empty review text. Dedupe by `(reviewer, text[:120])`. Keep `rating <= 3`; if rating is missing, keep it.
7. Assign globally unique integer ids, sequential `0..N-1`. Maintain `review_index[id] = {place_id, rating, reviewer, snippet}` where `snippet = text`. The snippet is the full review text; never truncate. Sales reads these in the handoff CSV verbatim, and the classifier benefits from full context.
8. Subagent input row shape: `{id: <int>, text: <full review text>}`. Do not cap input length; the agent should see the entire review. Group review rows into batches of 20-40 reviews per batch, not per lead.
9. Dispatch all batches in one message, in parallel, in the original Claude workflow. In a single assistant message, emit one Agent tool-use block per batch; 4-8 batches per message is reasonable. Do not await one batch before sending the next. For each Agent block:
   - `subagent_type: "pain-classifier"`
   - `prompt`: tell the subagent to read `outreach/silverthread/pain_categories.md` first, then classify each review per its agent definition. Pass the batch JSON verbatim.
10. Build the sidecar. Concatenate batch outputs, each a list of `{id, categories: [{main, sub, confidence, quote, reasoning}]}`, then for each `(id, category)` join via `review_index` and emit into the sidecar dict. Output schema matches `scripts/merge_classifications.py`'s SIDECAR SCHEMA:

   ```json
   {
     "<place_id>": {
       "<main>": [
         {
           "sub": "missed_calls_during_business_hours",
           "confidence": 0.88,
           "snippet": "I called five times...",
           "rating": 1,
           "reviewer": "Jane D",
           "reasoning": "direct phone-unreachable language"
         }
       ]
     }
   }
   ```

Field-name discipline: `csv_builder` reads `snippet`/`rating`/`reviewer`, so use those names. The subagent's `quote` is the verbatim span; use the `review_index` `snippet` field as the CSV-bound full review text. Both can be preserved if desired; minimum required is `snippet`.

11. Write atomically with temp plus rename. If today's file exists, write `<today>-2.json` rather than overwriting. The prior run is the audit record; see `CLAUDE.md rule 1`.
12. Stratified spot-check before declaring done. Sample `max(10, round(0.10 * total_hits))`, stratified by main category with at least one sample per main. Print `(main, sub, confidence) - "<snippet>"`. Compute mean confidence across all hits, not just the sample. If below `0.6`, flag it loudly because the agent is hedging more than usual.
13. Ask the user explicitly: `these hits look right - proceed, retry classify, or abort?` Do not infer approval from your own read.

Baseline from the Claude runbook: 2026-04-29 gold set main F1 `0.784`, strict `(main, sub)` F1 `0.683`, mean confidence about `0.78`.

Summary format:

```text
classified <n> leads (<m> hits across <k> mains) -> <sidecar-path>
next: python outreach/scripts/merge_classifications.py --master <...> --sidecar <sidecar> --out <new-master>
```

## Stage: enrich

Delegates to:

```bash
python outreach/scripts/enrich.py <pipeline> [--queue PATH] [--workers N]
```

Required pipeline config: `ENRICH_PROFILE`. The dataclass shape is documented in `outreach/lib/enrichers/website_crawl.py:EnrichProfile`.

Default queue: `pipelines/<pipeline>/enrichment/crawl_queue.json`. If the queue does not exist, ask which leads to enrich, likely top-N from the latest master, and write the queue file before invoking the script.

Output: `enrichment/website_crawl.json`, resumable and skipping leads already in the file, and `enrichment/website_crawl_retry.json` for failures to retry with `Playwright MCP`.

Auto-follow: graft crawl results into master. Once `enrich` finishes, always run `merge_crawl_into_master.py` so the next stages (`validate`, `classify`, `handoff`) see crawled emails and POCs on each lead. Skipping this leaves `crawled_emails` empty in the master even though `website_crawl.json` is full of data.

```bash
python outreach/scripts/merge_crawl_into_master.py <pipeline> [--master PATH] [--crawl PATH]
```

Defaults are latest `outputs/<date>/master.json` and `enrichment/website_crawl.json`. The merge joins by hostname; the queue is deduped by hostname, so a multi-listing single practice gets the same crawl payload across all its master rows. It adds `crawled_emails`, `crawled_emails_source`, `crawled_socials`, `pocs`, `crawl_status`, and `crawl_pages_visited` with provenance per `CLAUDE.md rule 1`. Leads whose hostname has no crawl row get `crawl_attempted: False`.

Filtering note: emails returned in `website_crawl.json` are already run through `lib.enrichers.website_crawl.filter_valid_emails`, which drops image-artifact, vendor-domain, and placeholder hits using canonical `validate_email`. The validate stage flags any survivors that the crawl-time filter missed.

## Stage: validate

Delegates to:

```bash
python outreach/scripts/validate.py <pipeline> [--master PATH]
```

Required pipeline config: `METRO_AREA_CODES` for the metro-mismatch phone check. `VENDOR_DOMAINS_EXTRA` is optional; it extends the lib's generic vendor reject set with vertical-specific marketing vendors.

Defaults to latest `outputs/<date>/master.json`. Appends sibling flags for invalid emails (`emails_invalid: list[{email, reason}]`, deduped by email), for the phone (`phone_invalid: bool`, `phone_invalid_reason: str`), and for each POC (`pocs[*].invalid: bool`, `pocs[*].invalid_reason: str`). POC invalid flags are set in place on the POC dict, while raw `name` is preserved. Atomic write-back. Never drops rows.

Always run validate before handoff because handoff reads the sibling flags. Skipping validate produces a CSV with `phone_invalid: None`, missing email-invalid counts, and POCs that include section-heading captures like `MEET THE` or `Our Founder` in the `pocs` column.

## Stage: handoff

Delegates to:

```bash
python outreach/scripts/handoff.py <pipeline> [--master PATH] [--out PATH]
```

Required pipeline config: `PAIN_WEIGHTS`, `SERVICE_MAP`. Both are keyed by the new STL hierarchy main names (`calls_unanswered`, `booking_friction`, and so on), the same keys the classify stage and `csv_builder._pain_hits_field` use.

Defaults: read latest `outputs/<date>/master.json`, write `handoff.csv` next to it.

For a re-delivery, such as regenerated master with normalized URLs or new classifier output, use `--out` to write into a new dated folder so the prior delivery is preserved:

```bash
python outreach/scripts/handoff.py <pipeline> \
  --master outreach/pipelines/<pipeline>/outputs/<new-date>/master.json \
  --out outreach/pipelines/<pipeline>/outputs/<new-date>/handoff.csv
```

## Stage: owner-lookup

Optional post-handoff decision-maker enrichment for tier A/B leads where `owner_name` is empty. Backed by `outreach/scripts/owner_lookup.py`, a manual web-search provider behind a script-shaped interface so the flow is idempotent and provenance-clean.

Print the queue:

```bash
python outreach/scripts/owner_lookup.py <pipeline> --print-queue [--limit N] [--tiers A,B] [--master PATH]
```

Then manually web-search each query: LinkedIn, practice About pages, RealSelf, and state board listings. Write the sidecar by hand at:

```text
outreach/pipelines/<pipeline>/enrichment/owner_lookups/<today-UTC>.json
```

Shape:

```json
{
  "<place_id>": {
    "name": "...",
    "title": "...",
    "linkedin": "..."
  }
}
```

Apply the sidecar:

```bash
python outreach/scripts/owner_lookup.py <pipeline> --apply [--sidecar PATH] [--master PATH]
```

After apply, re-run handoff so the CSV picks up the new owner columns: `/outreach <pipeline> handoff`.

Skip owner-lookup when:

- Handoff is tier-D-heavy, low conversion ceiling.
- The vertical's pitch works without a named POC, such as mass `info@` outreach.
- You are testing the pipeline, not shipping to sales.

When an automated provider lands, such as LinkedIn API or paid people-search, slot it behind `--print-queue` writing the sidecar from search results. The `--apply` interface stays unchanged.

## Stages Not Yet Supported As Scripts

- `scrape`: use the `google-maps-scraper` skill (`.claude/skills/google-maps-scraper/SKILL.md` in the Claude source, `.agents/skills/google-maps-scraper/SKILL.md` in this Codex repo). Output goes to `outreach/pipelines/<pipeline>/raw/<query>.json`. Do not write to `/tmp`; see `CLAUDE.md rule 2`. After scrape, run `analyze` to build the initial master.

## Re-Delivery Flow

Write every re-delivery into a new dated folder:

1. Rebuild master if needed:

   ```bash
   python outreach/scripts/analyze.py <pipeline> --output-date <new-date>
   ```

2. `/outreach <pipeline> classify` against the new master. This emits the sidecar at `enrichment/pain_classifications/<new-date>.json`. `merge_classifications.py` joins on `place_id`, so the master fed to merge must carry it; `analyze` guarantees this.
3. Merge classifications:

   ```bash
   python outreach/scripts/merge_classifications.py \
     --master outreach/pipelines/<pipeline>/outputs/<new-date>/master.json \
     --sidecar outreach/pipelines/<pipeline>/enrichment/pain_classifications/<new-date>.json \
     --out outreach/pipelines/<pipeline>/outputs/<new-date>/master.json
   ```

   The CLI auto-derives the pipeline name from the master path and pulls `PAIN_WEIGHTS` from `config.py` so `quality_score`, `weighted_pain`, and `tier` get recomputed on `agent_pain_hits`. Inspect the orphan-place_ids stat; nonzero usually means classify ran against a different master than this one.

4. If you want crawl data, `/outreach <pipeline> enrich` against the new master, then run `merge_crawl_into_master.py` to graft.
5. `/outreach <pipeline> validate` to annotate the new master.
6. `/outreach <pipeline> handoff`; defaults to latest dated folder, or pass `--master` / `--out` explicitly.
7. Optionally `/outreach <pipeline> owner-lookup` for tier-A/B leads with empty `owner_name`, then re-run handoff.
8. Compare lead counts and tier distribution to the prior delivery before declaring done. Big shifts in tier mix usually mean the classifier's category remapping changed which pains drive ranking; surface this before shipping to sales.

## Final Response

End every completed stage with three lines:

```text
what ran: <stage> for <pipeline> with key counts
what it produced: <file paths and row counts>
what's next: <natural follow-up command>
```
