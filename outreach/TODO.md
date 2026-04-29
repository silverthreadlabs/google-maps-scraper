# Outreach TODO

Open work that doesn't belong in CLAUDE.md (auto-loaded) — read on demand.

## Bug fixes from sales feedback (2026-04-25)

- **URL tracking params in handoff CSV.** `lib/url_normalize.py` is
  implemented and tested; needs to be wired through
  `lib/handoff/csv_builder.py` so the cleaned URL replaces the raw one
  at output time (with the original kept in an audit column).
- **Pain quote ↔ category mismatch.** Root cause is regex-only
  classification (F1=0.17). Fix in progress: `lib/pain/llm.py` (Claude
  Haiku 4.5 end-to-end agent). Validate against
  `pipelines/dental_sunbelt/eval/labels.json`; expect F1 >0.85.

## Re-deliveries

- Once both bugs above are fixed, regenerate the dental handoff CSV with
  normalized URLs and accurate pain quotes; replace
  `pipelines/dental_sunbelt/outputs/2026-04-25/handoff.csv` (or write a
  new dated folder).

## Feedback loop

- Wire sales-team disposition codes (e.g., `bounced`, `wrong_poc`,
  `replied_interested`) back into the master once they start coming in.
  Append-only via sidecars — see CLAUDE.md rule 1.
