# Outreach TODO

Open work that doesn't belong in CLAUDE.md (auto-loaded) — read on demand.

## Bug fixes from sales feedback (2026-04-25)

- **URL tracking params in handoff CSV.** Resolved (2026-04-30):
  `lib/url_normalize.py` wired through `lib/handoff/csv_builder.py`
  via `apply_url_normalization()`. `website`, `google_maps_link`, and
  `website_redirect_target` get cleaned at output time; original is
  preserved in `<field>_raw` audit columns when normalization changed
  the value. Tests: `lib/handoff/tests/test_csv_builder.py`.
- **Pain quote ↔ category mismatch.** Solved by a Claude Code subagent
  (`.claude/agents/pain-classifier.md`) that classifies reviews against
  the STL-derived hierarchy in `outreach/silverthread/pain_categories.md`.
  Eval harness: `pipelines/dental_sunbelt/eval/eval_runner.py`. Latest
  baseline (2026-04-29) on the 100-review gold set: main F1 0.784 / strict
  F1 0.683 / strict exact-match 0.64 — vs prior SBERT baseline of ~0.43.

## Re-keying ranking + handoff to (main, sub) tuples

`PAIN_WEIGHTS` in `pipelines/dental_sunbelt/config.py` and the local
`SERVICE_MAP` in `lib/handoff/csv_builder.py` are still keyed by the
legacy flat category names. The pain-classifier subagent emits
`(main, sub)` tuples. Re-key both when wiring the subagent's output
through ranking and the handoff CSV — see "Pipeline integration" below.

## Re-deliveries

- Once URL tracking is wired into the handoff and the subagent has been
  run on a real delivery, regenerate the dental handoff CSV with
  normalized URLs and agent-classified pain quotes; replace
  `pipelines/dental_sunbelt/outputs/2026-04-25/handoff.csv` (or write a
  new dated folder).

## Pipeline integration (after D)

The subagent currently runs ad-hoc against an eval set. It needs to be
wired into the pipeline at the right stage. Per planning convo
(2026-04-29): scrape → enrich → **prioritize most promising leads** →
dispatch agent on the prioritized subset → merge predictions back into
the lead stream → handoff. Decide:

- Where in the slash-command runbook (`.claude/commands/outreach.md`,
  pending) to dispatch — likely a new `classify` step between `enrich`
  and `validate`. Earlier `outreach/orchestrator.py` Python stub was
  deleted; the runbook is the orchestrator now.
- How predictions persist (sidecar file under `pipelines/<name>/enrichment/`
  keyed by `place_id`, append-only per CLAUDE.md rule 1).
- How the main agent invokes the subagent in batches that fit context.

## owner-lookup-script

Decision-maker enrichment is currently a manual web-search step (the
2026-04-25 dental master has 4 leads with `owner_source: 'web_search_linkedin'`
populated by hand). No script yet. Runbook (`.claude/commands/outreach.md`)
documents the manual flow and `scripts/handoff.py` surfaces the gap as an
optional `next:` hint when tier-A/B leads have empty `owner_name`.

When implementing as `outreach/scripts/owner_lookup.py`:
- Input: a master.json + a tier filter (default `{A, B}`) + `--limit N`.
- Output: sidecar `enrichment/owner_lookups/<today>.json` keyed by
  `place_id` + an in-place patch onto master with `owner_name`,
  `owner_title`, `owner_linkedin`, `owner_source`, `owner_added_at`.
- Provider: agent-browser web search → LinkedIn (or a paid people-search
  API if scraping LinkedIn becomes unworkable). Single configurable
  provider behind a small interface; provenance stays consistent regardless.
- Idempotency: skip leads already carrying `owner_name`.

## poc-validator coverage

`lib/validators/poc.py` covers section-heading captures and template
phrases the heading-extractor truncates to two tokens. As more verticals
land, expand `STANDALONE_HEADING_WORDS` / `TEMPLATE_PHRASES` from real
crawl output rather than guessing — every new false-positive class adds
a test case in `tests/test_poc.py`.

## Feedback loop

- Wire sales-team disposition codes (e.g., `bounced`, `wrong_poc`,
  `replied_interested`) back into the master once they start coming in.
  Append-only via sidecars — see CLAUDE.md rule 1.
