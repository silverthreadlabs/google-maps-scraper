# reachability-rating — plan index
<!-- Generated: 2026-06-15 -->

Implements `docs/specs/2026-06-15-reachability-rating.md` (DDD-0001). Split rolling-wave: the engine + ranking + handoff node delivers correct blended grades to the **sales CSV** with zero existing-test breakage; the eager-recompute node then propagates the blended grade into `master.json` for the backend-push and audit paths.

**Forcing function for the split:** the tier-scale change ripples into ~5 existing stage tests (e.g. `test_merge_classifications` asserts old-scale `tier`/`quality_score`), and the eager-recompute touches stage files not yet read. Node 01 sidesteps that by adding a *new* blended tier function and computing authoritatively at handoff, leaving existing stages (and their tests) untouched. Node 02 is detailed next cycle against the shipped Node 01.

| Node | Depends on | Status | Owns (top dir) | Goal |
|------|------------|--------|----------------|------|
| 01-reachability-engine-and-handoff | — | ✓ done (2026-06-15) | `lib/reachability.py`, `lib/ranking.py`, `lib/handoff/` | Score reachability, blend to 0–100, and surface the blended grade + sub-scores in the sales handoff CSV |
| 02-eager-recompute-wiring | 01 | ✎ sketched | `lib/cli/` | Recompute the blended grade at every stage that adds/removes a usable contact so `master.json` (and `push_leads`) carry it; collapse to one tier function |

**Runnable now:** none — 01 is ✓ done (implemented 2026-06-15, incl. the D1 channel-less cap; see node-01 plan + DDD-0001). 02's dependency is now satisfied.
**Sketched (not yet detailed):** 02-eager-recompute-wiring — dependency-unblocked but still sketched; detail it in the next align cycle, against the code Node 01 shipped, before implementing.

**Transient state between 01 and 02 (expected, closed by 02):** after 01, `handoff.csv` carries the new 0–100 blended grade, but `master.json` still stores the old open-ended `quality_score` until a stage recomputes it. The sales deliverable is correct; `push_leads.py` (sends `quality_score` to the stl-knights backend) should run **after** 02, or knowingly ship old-scale scores until then.
