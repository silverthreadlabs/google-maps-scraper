# software_ua_v2 — depth-over-breadth re-enrichment

**Date:** 2026-06-08
**Status:** Design — approved for planning
**Author:** outreach pipeline work

## Problem

The `software_ua` campaign was delivered to sales and judged useless. Two
problems were reported (P1, P2). Investigation of the shipped delivery
(`outputs/2026-05-22/master.json`, 1,422 leads / `handoff.csv`, 1,165 rows)
found the root causes are an **execution gap plus one bug**, not a missing
capability:

### P1 — "bad emails, no reachable POCs"
- Emails are dominated by generic role inboxes: `info@` (197), `hello@` (61),
  `sales@` (40), `support@` (21). Sales says these are useless.
- The two stages built to find reachable decision-makers were **never run**:
  `owner_name` is empty on **all 1,422 leads** (owner-lookup skipped), and
  there is no `enrichment/osint/` directory (osint-enrich skipped).
- The website-crawl POC extractor has a **precision problem**: of 489 POC
  entries, names include `React Native`, `Google Partner`, `Meta Business`,
  `Microsoft Gold`, `Acquia Partner`, `Your SaaS`, `Central Europe` — tech-stack
  and partner/marketing badges, not people. Real names are mixed in but
  precision is poor.
- POCs have no reach channel: exactly **1 of 489** carries an email; none have
  a direct handle.

Root cause of the badge leakage: the `2026-05-22` master predates POC
confidence scoring (`lib/validators/poc.py` updated 2026-06-01). Every POC has
`confidence: None`, so the handoff filter's "keep unscored" fallback
(`csv_builder.pocs_field`, gated by `POC_MIN_CONFIDENCE`) let the badges
through. Re-running `validate` with current code scores and sinks most of them;
the residual gap is tech-stack/marketing tokens the badge vocab does not cover.

### P2 — pain points in another language
- Of 264 selected pain snippets, **237 (90%) are Cyrillic** (Russian/Ukrainian).
  The strongest column in the CSV (`pain_quote_*`) is unreadable to sales.

## Goal

Deliver a new campaign, `software_ua_v2`, that is **deeply enriched over broad**:
high-value UA software firms, each — wherever publicly feasible — carrying a
**named decision-maker and at least one verified reach channel** (LinkedIn OR
personal email OR direct social), with pain quotes in **English** while the
original Cyrillic is preserved for audit. No pipeline rebuild.

### Product being pitched — shapes the ICP

The campaign exists to pitch **ezly** (https://www.getezly.com) — an AI
client-communication assistant (Chrome extension) for **freelancers, solo
consultants, and small agencies** who manage client comms on Upwork, Fiverr,
**LinkedIn**, Gmail, Discord. Implications for enrichment:

- The ideal contact at these UA software firms is the **founder /
  business-development / sales / client-comms person** — not the tech lead.
  Deep-enrichment must bias toward that role.
- **LinkedIn is the preferred handle**: ezly plugs into LinkedIn and that is
  where this buyer lives.
- The `frontline_communication` pain category (slow / poor client responses,
  mined from reviews) is a **direct pitch hook** for ezly — which is exactly
  why translating those quotes to English (P2) matters: they become the
  opener, not just a ranking input.

## Decisions (locked with stakeholder)

| Decision | Choice |
|----------|--------|
| Approach | Re-run the existing pipeline correctly + fix bugs (no rebuild) |
| Scope | Deep-enrich the full tier A/B/C subset (~430 leads) |
| Reach channel | Any verified channel per POC (LinkedIn / personal email / social) |
| Translation in CSV | English replaces the quote; original kept in a sibling column |
| Output location | New campaign dir `software_ua_v2` (raw leads copied in) |
| Enrichment depth | **Maximum** — run owner-lookup + POC crawl + osint-enrich, all three, across the full subset |
| Enrichment targeting | Bias toward founder / BizDev / sales / owner role + LinkedIn handle (ezly's ICP), configured in `campaigns/software_ua_v2/overrides.py` |
| Feasibility pilot | Yes — run the deep stages on ~20 leads first; measure yield; go/no-go |

## Architecture — reuse the pipeline; 2 code changes + targeting + correct execution

The outreach pipeline already has every stage needed
(`analyze → enrich → merge-crawl → classify → validate → handoff`, plus
`owner-lookup` and `osint-enrich`). The fix is two targeted code changes, an
enrichment-targeting bias, and running the skipped stages on a filtered subset.

### Not doing: a POC tech-framework denylist

An earlier draft proposed extending `lib/validators/poc.py`'s `_BADGE_TOKENS`
with tech-stack tokens. **Dropped after measurement.** Re-running the current
`validate` (which already scores POC confidence — `validate.py` calls
`poc_confidence`, and `csv_builder.pocs_field` filters at
`POC_MIN_CONFIDENCE = 0.30`) sinks the badges already: of 489 POCs, only **3**
tech-ish names survive the filter (`React Native`, `Flutter CTO`,
`Central Europe`). The residual noise is a different class (0.45 img_alt
two-word captures like `Official Race`, `Game Development`), which a tech-token
list does not address. And because the **real** contact now comes from
owner-lookup / osint, the crawled `pocs` column is a secondary signal — its
existing filtering is sufficient. Net: the extension would clean 3 names on a
column that is no longer the deliverable. Not worth it.

### Targeting — bias deep-enrichment to ezly's ICP

Not a code change to the libs; a targeting rule applied when running
owner-lookup and osint-enrich:

- **owner-lookup** queries (`--print-queue`) and the manual web-search step
  prioritize finding the **founder / co-founder / CEO / business-development /
  sales / partnerships** person and their **LinkedIn**, over a generic
  "owner".
- **osint-enrich** / the `osint-binder` subagent: when multiple candidate
  people are found, prefer the one whose role matches the ICP and who has a
  LinkedIn profile.
- The ICP role/channel preference lives in
  **`campaigns/software_ua_v2/overrides.py`** (campaign-scoped, not the shared
  `verticals/software/config.py`) — so it biases this ezly campaign without
  changing behaviour for other software campaigns. Override the desired OSINT
  fields / role markers (`OSINT_FIELDS_DESIRED`, POC title markers) there to
  favour founder/BizDev/sales/owner + LinkedIn.

### Change 1 — new `translate` stage (first-class, reusable, locale-gated)
**Files:** new `outreach/lib/cli/translate.py` + a merge step (CLI or function),
following the `classify` / `merge_classifications` pattern. Registered in the
outreach runbook (`.claude/skills/outreach/SKILL.md`) as a standing stage —
**not** a `software_ua_v2`-specific script.

**This is a permanent pipeline stage, not a one-off.** It is reusable by any
future non-English campaign. Two layers of gating keep it correct and cheap:

1. **Invocation gate — campaign `locale`.** The stage is part of the standard
   pipeline order, but only does work for non-English campaigns. For `en-*`
   locales (SF, Dallas, Toronto) it is a no-op / skipped; for `uk-UA` (and any
   future `es-*`, `pl-*`, …) it runs. `locale` already exists on every
   `locations/<loc>.yaml`, so no per-campaign code is needed.
2. **Per-snippet gate — language detection.** Campaign content is *mixed*
   (software_ua is ~90% Cyrillic but some firms' reviews are already English).
   Inside the stage, each candidate snippet is language-detected; only
   non-English snippets are sent to the translator. English-source snippets
   pass through untouched.

Mechanics:

- Select the pain snippets that will actually surface in the handoff — the
  **top-2 pain quotes per lead**, across the whole master (the CSV ships all
  rows, so all surfaced quotes should be readable). Cost is bounded two ways:
  only the top-2 quotes per lead, and only the non-English ones (the script
  gate drops already-English snippets) — far fewer than the full hit set.
- Batch the non-English snippets to a **translator subagent** governed by the
  `translator` skill's anti-fabrication rules: preserve numbers, currency,
  person/company names, URLs, and identifiers exactly; English must read
  natively.
- Write the sidecar `enrichment/translations/<date>.json`, keyed by
  `(place_id, snippet-hash)`.
- Merge step grafts `snippet_en` onto each `agent_pain_hits[*]` with provenance
  (`snippet_en_source`, `snippet_en_added_at`). Idempotent; English-source
  snippets pass through unchanged; re-running translates only newly-appearing
  non-English snippets.

**Pipeline-order placement:** after `classify` (snippets exist) and before
`handoff` (which consumes `snippet_en`). Independent of crawl/owner/osint, so
it can run any time the pain hits are settled.

### Change 2 — handoff columns
**File:** `outreach/lib/handoff/csv_builder.py`.

- `pain_quote_1` / `pain_quote_2` emit `snippet_en` when present, else the
  original snippet.
- Add sibling columns `pain_quote_1_original` / `pain_quote_2_original` holding
  the source Cyrillic.
- Add `primary_contact` + `primary_contact_channel` surfacing the single best
  reachable POC (name + the one verified channel). **Selection order:**
  (1) an ICP-role person (founder/BizDev/sales/owner) with a LinkedIn, from
  owner-lookup/osint; (2) any owner-lookup/osint person with a verified
  channel; (3) highest-confidence crawled json_ld POC. Channel preference
  within a contact: LinkedIn → personal email → other social.

### Correct execution
Run the stages that were skipped, **all three deep passes**, on the A/B/C
subset, behind a one-time pilot gate.

## Data flow / sequence

1. **Scaffold** `campaigns/software_ua_v2/`: `campaign.yaml`
   (`vertical: software`, `location: ua`, `slug: software_ua_v2`), copy
   `overrides.py`, **copy raw NDJSONs** from `software_ua/raw/` (immutable,
   CLAUDE.md rule 2), and copy the existing
   `pain_classifications/2026-05-22.json` sidecar to reuse classification
   (avoid re-paying the LLM classify stage).
2. **analyze** `software_ua_v2` → master (place_ids, tiers, chain flags, email
   partition into `emails` / `emails_invalid`).
3. **merge classification sidecar** → pain hits + recomputed
   `quality_score` / `weighted_pain` / `tier`.
4. **Build the A/B/C crawl queue** (~430 leads), dedup by hostname.
5. **enrich** (website crawl) → **merge_crawl_into_master**. Re-running
   `validate` scores POC confidence so badges sink below threshold (no code
   change needed).
6. **PILOT GATE — ~20 top-quality_score subset leads:** run `osint-enrich` +
   `owner-lookup` + the crawl POC pass, **with ICP-role/LinkedIn targeting**;
   measure **yield = % of pilot leads with a named, reachable ICP-role POC +
   verified channel**. Report to stakeholder → proceed / adjust / abort.
   Go/no-go threshold: **~30%** (below this, reconsider before the full spend).
7. **On approval, run all three deep passes across the full A/B/C subset**
   (owner-lookup, osint-enrich, POC crawl) — maximum enrichment, ICP-targeted.
8. **translate** → merge English snippets.
9. **validate** → POC confidence, email/phone invalid flags.
10. **handoff** → CSV: English pains, original siblings, `primary_contact` /
    `primary_contact_channel`.
11. **Diff vs `2026-05-22`**: lead counts, tier mix, and the headline metric
    **% of leads with a reachable POC**. Surface before declaring done.

## Testing

TDD per `outreach/TDD-RULES.md`:
- translate stage — locale gate (`en-*` campaign → no-op; non-English → runs);
  per-snippet language detection (Cyrillic snippet → translated; English
  snippet → passed through untouched).
- translate-merge — `snippet_en` grafted with provenance; idempotent;
  English-source pass-through; re-run translates only new non-English snippets.
- `lib/handoff/tests` — `pain_quote_*` prefer English; `*_original` carries
  Cyrillic; `primary_contact` selection order (ICP-role+LinkedIn first,
  then any verified channel, then crawled json_ld; channel preference
  LinkedIn → personal email → social).
- Run the repo test loop before declaring done.
- (No validator-token tests — the POC denylist extension was dropped.)

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Pilot yield low — UA software DMs not publicly reachable | The pilot gate catches this before the full spend; if <~30%, reconsider (accept company-level LinkedIn, narrow subset) |
| owner-lookup is a manual web-search flow; 430 is labor-intensive | Pilot calibrates effort per lead; stakeholder chose maximum enrichment knowing the cost; can cap after pilot |
| Translation cost on many snippets | Scope to the top-2 surfaced quotes per subset lead, not all hits |
| New campaign dir duplicates raw + breaks provenance continuity | Copy (not move) raw; carry the classification sidecar; keep `software_ua` intact as the audit record |

## Out of scope

- Re-scraping Google Maps (raw leads are reused as-is).
- Re-running the LLM classify stage (existing sidecar reused).
- Sub-level pain-weight granularity (deferred, per existing TODO).
