# Outreach TODO

Open work that doesn't belong in CLAUDE.md (auto-loaded) — read on demand.

## Bug fixes from sales feedback (2026-04-25)

- **URL tracking params in handoff CSV.** `lib/url_normalize.py` is
  implemented and tested; needs to be wired through
  `lib/handoff/csv_builder.py` so the cleaned URL replaces the raw one
  at output time (with the original kept in an audit column).
- **Pain quote ↔ category mismatch.** Solved by a Claude Code subagent
  (`.claude/agents/pain-classifier.md`) that classifies reviews against
  the STL-derived hierarchy in `outreach/silverthread/pain_categories.md`.
  Eval harness: `pipelines/dental_sunbelt/eval/eval_runner.py`. Latest
  baseline (2026-04-29) on the 100-review gold set: main F1 0.784 / strict
  F1 0.683 / strict exact-match 0.64 — vs prior SBERT baseline of ~0.43.

## Cleanup phase (D) — next

Now that the subagent works, delete the legacy Python pain classifiers
and prune their references:

- **Delete** `outreach/lib/pain/regex.py`, `outreach/lib/pain/sbert.py`,
  `outreach/lib/pain/__init__.py`, `outreach/lib/pain/__pycache__/`,
  and the `outreach/lib/pain/` directory itself.
- **Delete** `outreach/pipelines/dental_sunbelt/eval/eval_classifier.py`
  (replaced by `eval_runner.py`, which doesn't import sbert/regex).
- **From `outreach/pipelines/dental_sunbelt/config.py`, drop:**
  `PAIN_REGEX_PATTERNS`, `SBERT_ANCHORS`, `SBERT_PER_CATEGORY_THRESHOLD`,
  `SBERT_TITLE_DENY_RULES`, `SERVICE_MAP`, the flat `PAIN_CATEGORIES`.
  **Keep:** `DSO_TITLE_REGEX`, `DSO_EMAIL_DOMAINS`, `GEOGRAPHIC_PREFIXES`,
  `METRO_AREA_CODES`. **`PAIN_WEIGHTS`** stays for now but will need
  re-keying to `(main, sub)` tuples when ranking comes back into play.
- **`outreach/CLAUDE.md`**: line 10 mentions "SBERT anchors" as a config
  knob — update or drop.
- **`outreach/README.md`**: drop `regex.py`/`sbert.py`/`llm.py` from
  the lib/ tree, drop the SBERT mentions from the principle section,
  drop SBERT from the "adding a vertical" steps, update the "current
  state" section to mention the subagent + eval_runner.
- **`outreach/.venv/`**: `sentence-transformers` is no longer needed.
  Either drop the package, or remove the venv entirely if no other
  tooling depends on it.

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
