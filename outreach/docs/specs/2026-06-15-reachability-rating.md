# Blended lead rating: service-fit + reachability

> **For agentic workers:** This feature is split into nodes — see `docs/plans/2026-06-15-reachability-rating/00-index.md`. After aligning, invoke `auto-pipeline` with this spec and the first runnable node, `docs/plans/2026-06-15-reachability-rating/01-reachability-engine-and-handoff.md`. Load `CONTEXT.md` and `docs/adr/0001-blended-service-fit-reachability-rating.md` alongside it.

**Goal:** Make a Lead's Quality score reflect not just how well we can help the business (service-fit) but how easily we can reach a decision-maker (reachability), as one blended 0–100 grade.

**Domain:** Rating dimensions, People & Channels, Score composition (see `CONTEXT.md`).

---

## Problem Statement

Today a Lead's grade measures **service-fit only** — how well Silverthread's services match the pain in the Lead's reviews. It ignores **reachability**: whether we can actually get a decision-maker on the line. Since outreach happens *through a person (a POC)*, a great-fit Lead with no reachable person is in practice a dead end, while a mediocre-fit Lead whose owner we can reach by LinkedIn and direct email is workable. The grade should say so.

## Solution

Add **reachability** as a co-equal half of the Quality score. The blended grade is **service-fit half (0–50) + reachability half (0–50) = 0–100**, with tiers **A ≥ 75, B ≥ 50, C ≥ 25, D < 25** (see DDD-0001).

Reachability is measured **only through people, never through the business front door**:

- **Business email** (`info@…`, `contact@…`) and **business social** (the company's own Facebook/LinkedIn page) are kept on the Lead but **do not** count toward reachability.
- A **directly-reachable email** (personal, or a named work address like `john-doe@acme.com`) and a **POC social** (a person's profile, gold-standard being a personal LinkedIn) **do** count.

The reachability half is built from:

1. **Representative POC channel boost** — from the single *best-reachable* usable contact, channels **stack** with priority **personal LinkedIn > directly-reachable email > personal social**, capped.
2. **Multi-POC boost** — having more than one usable contact adds a **diminishing, capped** amount (the 1→2 jump matters most; a 50-name crawl artifact doesn't dominate).

The no-double-count rule (the product owner's core constraint): per-channel credit comes from **one** representative POC only; extra POCs are rewarded *solely* through the separate multi-POC boost — a second POC's socials never stack on top of the first's.

## User Stories

1. As a **sales rep**, I want the top-graded Leads to be ones I can both *help* and *reach*, so that I don't waste a top-priority slot on a great-fit business with no contactable decision-maker.
2. As a **sales rep**, I want a Lead's grade to rise when research finds a decision-maker's LinkedIn or direct email, so that the deep-research effort visibly pays off in prioritization.
3. As a **sales rep**, I want to see *why* a Lead is reachable (which channels, how many contacts), so that I know how to approach it.
4. As a **campaign owner**, I want reachability to count contacts at the same quality bar I'm shown in the CSV, so that the grade matches the contacts actually in front of me.
5. As a **campaign owner**, I want a great-fit-but-unreachable Lead to land at tier B (not A), so that "top tier" reliably means "worth a rep's first calls."

## Implementation Decisions

Decisions made during grilling (see `CONTEXT.md` for terms, DDD-0001 for the architecture rationale):

- **Blended single grade** with a *visible* reachability sub-score (not two separate grades). [Q1]
- **Reachability ≈ equal weight** to service-fit — it can swing two or more grades. [Q2]
- **Channels stack** within the representative POC, priority **LinkedIn > email > social**, diminishing/capped. [Q3]
- **Multi-POC boost is diminishing and capped.** [Q4]
- **Representative POC = best-reachable** (strongest channel set), regardless of seniority. [Q5]
- **Directly-reachable email = generic-mailbox blocklist** — any address counts unless its local-part is a role mailbox (`info`, `contact`, `sales`, `office`, `hello`, `support`, `admin`, `reception`, `booking`, …). [Q6]
- **Personal-vs-business social is strict** — a personal LinkedIn (`/in/`) always counts; other socials count only when clearly *not* the business's own page; when unsure, exclude. [Q7]
- **Fixed 0–50 per half / 0–100 blended**, raw service-fit retained as a hidden tiebreaker; service-fit mapped onto 0–50 by saturating at a reference full-fit value. [Q8, DDD-0001]
- **Usable POC = the set sales sees** — not flagged invalid, confidence at/above the existing 0.30 bar (or unscored). Both the channel boost and the multi-POC count consider only usable POCs. [Q9]
- **A lead reachable through no channel is capped low** — when no usable POC carries a reachable channel (no personal LinkedIn, directly-reachable email, or personal social), the multi-POC boost is capped at **3** (`NO_CHANNEL_MULTI_CAP`), so several named-but-unreachable contacts cannot lift a lead toward a genuinely reachable one. A lead we can't reach at all is only marginally better than one with no contacts. [D1, 2026-06-15, node-01 implementation]
- **Universal reachability rules** — one shared set, not per-vertical (overridable later via the existing per-campaign override mechanism). [Q10]
- **Grade refreshes whenever pain or usable contacts change** — recomputed at every stage that adds/removes a usable contact, so later-discovered owners lift the grade and validated-bad contacts lower it. [Q11]
- **Great-fit-but-unreachable caps at tier B** — accepted deliberately. [Q12, DDD-0001]

Modules built/modified (domain names; exact paths in the plan):
- A new **reachability scorer** (industry-agnostic): unifies the per-person contact data into one usable-contact list, detects the qualifying channels, selects the representative POC, and returns the 0–50 reachability sub-score plus a breakdown.
- The **ranking** module gains service-fit normalization, a single **`score_lead`** entry point (fit-norm + reachability + blend + tier), and re-anchored tier thresholds.
- The **sales-handoff builder** computes the blended grade authoritatively at output time and surfaces the reachability sub-score, the service-fit sub-score, and a reachability breakdown (representative contact, channels, usable-POC count); its duplicated tier/weight logic is retired in favor of the ranking entry point.
- The **mid-pipeline merge stages** (crawl, pain, OSINT, validate, owner-lookup) recompute the blended grade so `master.json` stays current.

Interfaces that change:
- `quality_score` field meaning changes from raw service-fit (0–~334) to blended 0–100. Sorting semantics unchanged. New sibling fields: `service_fit_raw`, `service_fit_score`, `reachability_score`, `reachability_breakdown`.

Constraints / non-goals:
- Reachability **never** counts business emails or business socials, even when enrichment attached them to a person.
- Calibration constants (channel weights, multi-POC curve, `FIT_FULL`, tier cutoffs) are knobs set once against the current corpus; not learned from conversions yet.

## Testing Approach

- **Reachability scorer** — unit tests on real fixtures: the channel detectors (LinkedIn `/in/` vs `/company/`; `john-doe@acme.com` counts but `info@acme.com` doesn't; a personal FB profile counts but the business's FB page doesn't), the representative-POC selection (best channel set wins), the no-double-count rule (two POCs each with socials → only one's socials credited; the second contributes via the multi-POC boost only), the diminishing/capped multi-POC curve, and the lead-level fold (an `owner_linkedin` with no matching `pocs[]` entry still counts).
- **Ranking** — `service_fit_norm` saturates at 50 above `FIT_FULL` and is linear below; `score_lead` blends to 0–100 and assigns the right tier at the 75/50/25 boundaries; an unreachable max-fit lead lands at exactly 50 → tier B.
- **Handoff** — the CSV carries the blended grade, the two sub-scores, and the breakdown columns; sorting still puts the best leads first; the old duplicated tier/backfill path is gone.
- **Recompute wiring** — each touched stage, given a lead whose contacts change, ends with a refreshed blended grade.
- Prior art to follow: `lib/test_url_normalize.py` (unittest + subTest), `scripts/tests/test_analyze.py`, `lib/handoff/tests/test_csv_builder.py`.

## Out of Scope

- **Per-vertical reachability weights** — universal for now; revisit if a vertical proves it needs different rules (deferred, see DEFERRED.md).
- **Learning reachability/pain weights from conversions** — depends on the sales-feedback loop already tracked in `TODO.md`.
- **Sub-category pain weight granularity** — unrelated, already deferred in `TODO.md`.
- **Changing the raw service-fit formula** — kept exactly as-is; only normalized for the blend.
- **Back-grading historical deliveries** — old dated `outputs/` stay on the old scale.
