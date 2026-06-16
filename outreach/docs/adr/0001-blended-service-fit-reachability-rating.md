# DDD-0001: Blended lead rating — service-fit + reachability on a fixed 0–100 scale

- **Status:** accepted
- **Date:** 2026-06-15

## Context

Until now a Lead's **Quality score** measured only **service-fit**: weighted pain × breadth × log(size) × rating-gap, on an open-ended scale (most leads 0–20, a rare few up to ~334), with tier lines at 60 / 30 / 15. It answered "how well can we *help* this business?" but said nothing about "can we actually *reach* a decision-maker here?" — even though the pipeline already collects per-person contact data (`pocs[]`, `owner_linkedin`, `linkedin_url_poc`, `poc_email`, …).

Sales reaches businesses **through a person (a POC)**, not through the business switchboard. A great-fit lead with no reachable person is, in practice, a dead end; a mediocre-fit lead with a decision-maker's LinkedIn and direct email is workable. The rating did not reflect that.

We decided to fold **reachability** into the score as a co-equal dimension. That raised three coupled questions: how to combine two dimensions that today live on mismatched scales; how much reachability should weigh; and how to keep the A/B/C/D grades meaningful afterward. Grounding numbers (5,237 leads across all campaigns): median service-fit 6.2, p99 57.4, max 333.8; only ~3% of leads reach B/A today; only ~13% have any usable contact at all.

## Decision

The Quality score becomes a **blended 0–100 number = service-fit half (0–50) + reachability half (0–50)**, with tier lines **A ≥ 75, B ≥ 50, C ≥ 25, D < 25**.

- **Service-fit half (0–50):** the existing raw service-fit formula is kept *unchanged*, then mapped onto 0–50 by treating a reference "full-fit" value (the current A-cutoff region, `FIT_FULL = 60`) as the saturation point — linear below it, capped at 50 above. The raw, open-ended service-fit number is **retained as a hidden tiebreaker** (`service_fit_raw`) so no ranking information is lost when outliers saturate.
- **Reachability half (0–50):** scored from a single **representative POC** (the *best-reachable* usable contact) whose channels stack with priority **personal LinkedIn > directly-reachable email > personal social**, plus a **diminishing, capped multi-POC boost** for having more than one usable contact. Channels and the multi-POC boost are sourced from a unified contact list that merges `pocs[]` with the lead-level owner/OSINT contact fields. See DDD-0001's sibling rules in the spec for the exact composition.
  - *Refinement (2026-06-15, node-01 implementation, D1):* when **no** usable POC carries a reachable channel, the multi-POC boost is additionally capped at **3** (`NO_CHANNEL_MULTI_CAP`) instead of approaching the full ~10 — a pile of named-but-unreachable contacts is a research starting point, not reachability, and must not lift such a lead toward a genuinely reachable one (which would let it cross a tier line, e.g. C→B, with an empty channels column). This *elaborates* the composition above for the previously-unspecified all-channel-less case; it does not reverse it.
- **Reachability ≈ equal weight to service-fit:** a fully-reachable lead can earn up to 50, the same ceiling as a maximal fit. Reachability can therefore swing a lead two or more grades.
- **Consequence accepted deliberately:** because a lead with **no usable contact** caps at fit-half = 50, it can be **tier B at best, never tier A**. Tier A now means "strong fit **and** a real way to reach a decision-maker."

## Alternatives Considered

- **Add reachability points on top of the open-ended raw score, then re-draw tier lines.** Simplest, preserves today's math exactly — but "fit" and "reach" stay on mismatched scales, so "equal weight" is only approximate and the combined number stays hard to interpret. Rejected: the whole point of the change is to make reachability a genuine co-equal signal.
- **Relative (percentile) grading** — A = top ~5% of each batch, etc. Self-calibrating, but a lead's grade then depends on its batch rather than on the lead itself, breaking cross-campaign comparability and the "a score of X always means tier Y" property sales relies on. Rejected.
- **Keep great-fit leads able to reach tier A on fit alone** (don't cap unreachable leads at B). Rejected by the product owner: "we literally cannot reach anyone here" is a real cost that should knock a lead off the top-priority tier, not merely nudge it — the faithful result of equal-weighting. (On the corpus this demotes 38 of today's 49 A-leads to B, 15 of them having no contact at all; accepted with eyes open.)
- **Per-vertical reachability weights** (mirroring per-vertical pain weights). Rejected for now: reaching a human via LinkedIn/email/social doesn't vary by industry the way *pain* does. The config system already supports per-campaign overrides, so this stays a reversible future option, not a day-one cost.

## Consequences

- **The meaning of `quality_score` changes** from open-ended raw service-fit (0–~334) to a blended 0–100. Sorting semantics are unchanged (higher = better), but any consumer treating it as an *absolute* number — notably `push_leads.py`, which ships it to the stl-knights backend — must treat it as opaque ordering, not a fixed threshold. Flagged as a wiring check in the spec.
- **Tier thresholds move** (60/30/15 → 75/50/25) and are re-anchored to the 0–100 scale. Historical deliveries scored on the old scale are not retro-graded.
- **A single scoring entry point** (`score_lead`) becomes the one place fit-normalization + reachability + tiering happen, retiring the duplicated literal weights previously copied into the handoff CSV builder.
- **The grade refreshes whenever a Lead's pain or usable contacts change**, so later research stages (owner-lookup, OSINT) that surface a decision-maker's LinkedIn raise the grade, and validation that flags a contact bad lowers it.
- **The weights and cutoffs are tuning knobs**, calibrated once against the current corpus (A=14 / B=170 / C=218 under the chosen constants). They are expected to be re-tuned once the sales-feedback loop (see `TODO.md`) yields conversion data — at which point reachability weights could become evidence-driven rather than hand-set.
