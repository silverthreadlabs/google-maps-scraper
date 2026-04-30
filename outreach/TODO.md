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

- Where in `outreach/orchestrator.py` to dispatch (likely a new `classify`
  stage between `enrich` and `validate`).
- How predictions persist (sidecar file under `pipelines/<name>/enrichment/`
  keyed by `place_id`, append-only per CLAUDE.md rule 1).
- How the main agent invokes the subagent in batches that fit context.

## Feedback loop

- Wire sales-team disposition codes (e.g., `bounced`, `wrong_poc`,
  `replied_interested`) back into the master once they start coming in.
  Append-only via sidecars — see CLAUDE.md rule 1.
