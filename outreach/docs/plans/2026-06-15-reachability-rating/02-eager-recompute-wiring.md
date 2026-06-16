---
node: 02-eager-recompute-wiring
feature: reachability-rating
depends_on: [01-reachability-engine-and-handoff]
owns:
  - lib/cli/**
spec: docs/specs/2026-06-15-reachability-rating.md
adrs: [DDD-0001]
---

# Eager recompute wiring — SKETCH (detail next align cycle)

> **Not yet detailed.** Rolling-wave: detail this against the code Node 01 ships, not against assumptions now. Do not implement from this sketch — re-run `align` on it once Node 01 is merged.

**Goal:** Propagate the blended grade (`score_lead`) into `master.json` at every stage that adds or removes a usable contact or changes pain, so the stored `quality_score`/`tier` are always current — which the `push_leads` (stl-knights backend) and audit paths depend on. Then collapse the two tier functions into one.

**Why it exists (the transient Node 01 leaves):** after Node 01 the sales `handoff.csv` is correct (computed authoritatively at output), but `master.json` still carries the legacy open-ended `quality_score` until a stage recomputes it.

**Scope to detail next cycle (each gets real test + impl code then):**

- Call `lead.update(score_lead(lead, pain_weights=...))` at the end of each stage's merge loop: `analyze.py`, `merge_crawl_into_master.py`, `merge_classifications.py` (replace its existing inline recompute), `merge_osint_into_master.py`, `validate.py` (after invalid flags are set — they change the usable set), and `owner_lookup.py --apply`.
- Collapse `blended_tier` → `tier`: rename to `tier` (0–100), remove the legacy 60/30/15 `tier`, and update `handoff.py:_owner_lookup_candidates` plus `csv_builder` to use the single function.
- Update the stage tests whose expected values move to the new scale: `lib/cli/tests/test_analyze.py`, `test_merge_classifications.py`, `test_osint_enrich.py`, `test_decision_makers.py`, `test_push_leads.py`. Recompute each fixture's expected blended value (`service_fit_norm(raw) + reachability_score(...)`) — do this against the shipped Node 01 code, not by hand here.

**Open questions to resolve when detailing:**
- Does `push_leads.py` send `quality_score` as an absolute value the backend thresholds on, or as opaque ordering? Confirm before the scale reaches the backend (DDD-0001 Consequences).
- Which stages obtain `pain_weights` cheaply (config already loaded) vs. need it threaded in?
- `analyze.py` runs before pain/most POCs exist — confirm `score_lead` there produces a sensible early grade (fit-only, reach from any crawl POCs) and isn't surprising in the v0 master.
