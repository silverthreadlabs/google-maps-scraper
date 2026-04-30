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

**Output:** a sidecar at
`outreach/pipelines/<pipeline>/enrichment/pain_classifications/<today>.json`,
keyed by `place_id`, append-only (never replaces prior runs).

### Procedure

1. **Locate the source.** Default: latest `outputs/<date>/master.json`.
   If only raw scrapes exist (no master yet), fall back to
   `pipelines/<pipeline>/raw/*.json` and dedupe by `place_id`.
2. **Pick the subset to classify.** Ask the user:
   *"How many leads to classify? (default proposal: top-N by quality_score
   if a master exists, otherwise all leads in the raw scrape)"*
   Confirm the lead count before dispatching anything.
3. **Build per-lead review batches.** For each selected lead:
   - Merge `user_reviews` + `user_reviews_extended`, dedupe per CLAUDE.md
     rule 3.
   - Filter to ≤3★ reviews (pain signal is concentrated there).
   - Build a JSON row: `{id: <place_id>, reviews: [<review-text>, ...]}`.
   Group rows into batches of **20–40 reviews per batch** (not per lead —
   reviews. A 40-review-per-lead practice = 1 lead per batch).
4. **Dispatch.** For each batch, invoke the subagent via the Agent tool:
   - `subagent_type: "pain-classifier"`
   - `prompt:` instructs the subagent to read
     `outreach/silverthread/pain_categories.md`, then classify each
     review per the schema in its agent definition. Pass the batch JSON
     verbatim.
   - **Parallelize independent batches** in a single message with
     multiple Agent tool calls (per the dispatching-parallel-agents
     skill). 4–8 in flight is reasonable.
5. **Merge results.** Write to
   `enrichment/pain_classifications/<today>.json`. Schema:
   ```json
   {
     "<place_id>": [
       {"main": "calls_unanswered", "sub": "missed_calls_during_business_hours",
        "confidence": 0.88, "quote": "I called five times...", "reasoning": "..."}
     ]
   }
   ```
   If the file exists from an earlier run today, append (preserve the
   prior runs as historical record per the never-drop rule).
6. **Spot-check quality.** Print 3 random `(quote, main/sub)` pairs from
   the sidecar to the user. If anything looks like a category mismatch,
   stop and surface it. The current baseline is main F1 0.784 / strict
   F1 0.683 — large quality regressions are the failure mode to catch.
7. **Echo summary:**
   `classified <n> leads (<m> hits across <k> categories) → <sidecar-path>`

---

## Stage: enrich

Delegates to `outreach/scripts/enrich.py`.

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
agent-classified pain quotes (TODO.md). Sequence:

1. `/outreach dental_sunbelt classify` — emits a fresh sidecar.
2. **Build new master** (inline or via the future analyze script):
   read the existing `outputs/2026-04-25/master.json`, merge sidecar
   classifications by adding an `agent_pain_hits` field per lead
   (KEEP the old `pain_hits` untouched — provenance), write to
   `outputs/<today>/master.json`.
3. `/outreach dental_sunbelt validate` — annotates the new master.
4. `/outreach dental_sunbelt handoff` with explicit `--master` and
   `--out` pointing at `outputs/<today>/`.
5. Compare lead counts and tier distribution to the prior delivery
   before declaring done.

---

## Final hand-off (always end with this)

After the stage completes, write a 3-line summary the user can paste
into status updates:

- **what ran** — stage + pipeline + key counts
- **what it produced** — file paths and row counts
- **what's next** — the natural follow-up command (e.g.
  "validate next, then handoff")
