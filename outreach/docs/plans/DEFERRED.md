# Deferred Backlog

Single canonical backlog of deferred work. Open items at the top; closed items move to `## Archive`. `align` reads the open items every cycle.

> Note: workflow/skill issues do **not** live here. Feature-shaped engineering deferrals only. Sales-feedback-loop and sub-pain-weight items are tracked separately in `outreach/TODO.md`.

## DEF-001 — Per-vertical reachability weights
- Surfaced:     2026-06-15, during align grilling for blended reachability rating (Q10)
- Why deferred: Reachability rules are universal day-one; no evidence yet that a vertical needs different channel weights (e.g. local trades valuing personal Instagram over LinkedIn). The per-campaign override mechanism already supports splitting later, so this is reversible.
- Size:         small
- Relates to:   docs/specs/2026-06-15-reachability-rating.md, DDD-0001
- Status:       deferred

## DEF-002 — Learn reachability + pain weights from conversions
- Surfaced:     2026-06-15, during align grilling (consequence of hand-set constants)
- Why deferred: Blocked on the sales-feedback loop (disposition codes → master), which is itself an open item in `outreach/TODO.md` and needs a conversation with sales first. Once a few cohorts of conversion data exist, re-tune channel weights / pain weights / tier cutoffs from evidence instead of by hand.
- Size:         big
- Relates to:   docs/specs/2026-06-15-reachability-rating.md, DDD-0001, outreach/TODO.md ("Sales feedback loop")
- Status:       deferred

## DEF-003 — `score_lead` rating fallback is dead and a latent None/zero trap
- Surfaced:     2026-06-15, during auto-pipeline Phase 7 of node 01 (silent-failure-hunter + python-reviewer)
- Why deferred: Currently unreachable — `analyze.py` always writes the `rating` key and no stage writes `review_rating` onto the lead, so `lead.get('rating', lead.get('review_rating')) or 0.0` never exercises the fallback. Not a live bug. Becomes one if a future stage writes `rating: None`/`0` as a sentinel: `.get` returns the present None, `or 0.0` coerces it to 0, and `quality_score` then awards the maximum rating-gap term (~+19.6 raw). One-line fix (`lead.get('rating') or lead.get('review_rating') or 0.0`) but it changes plan-verbatim code, so deferred for a deliberate pass.
- Size:         small
- Relates to:   lib/ranking.py:score_lead, docs/specs/2026-06-15-reachability-rating.md
- Status:       deferred

## DEF-004 — `agent_pain_hits or pain_hits` lets stale legacy pain override an authoritative empty
- Surfaced:     2026-06-15, during auto-pipeline Phase 7 of node 01 (silent-failure-hunter)
- Why deferred: `score_lead` (and the pre-existing `csv_builder._pain_hits_field`) use `lead.get('agent_pain_hits') or lead.get('pain_hits') or {}`. A present-empty `agent_pain_hits == {}` (classifier ran, found nothing) is falsy, so a stale non-empty legacy `pain_hits` silently wins. Harmless on fresh single-pass masters (both empty); reachable only when reprocessing a legacy SBERT master through merge_classifications. Fix: distinguish present-empty from absent. Bundle with the "drop the legacy fallback" cleanup the ADR already anticipates.
- Size:         small
- Relates to:   lib/ranking.py:score_lead, lib/handoff/csv_builder.py:_pain_hits_field, DDD-0001
- Status:       deferred

## DEF-005 — CSV formula injection in the sales handoff (repo-wide, pre-existing)
- Surfaced:     2026-06-15, during auto-pipeline Phase 7 of node 01 (security-reviewer)
- Why deferred: The handoff CSV writes scraped strings (`owner_name`, `pocs`, `primary_contact`, pain quotes, and now `reachability_representative`) into cells with no leading-`= + - @` guard, so a crafted business/POC name can execute as a formula in Excel/Sheets. Pre-existing and systemic (no cell-escaping anywhere in `lib/`); node 01 adds one more column with the same pattern but no net-new attacker capability. Fix is a single writer-level prefix-guard over every cell in `build_handoff`, not a node-01 change.
- Size:         small
- Relates to:   lib/handoff/csv_builder.py:build_handoff, all scraped-text CSV columns
- Status:       deferred
