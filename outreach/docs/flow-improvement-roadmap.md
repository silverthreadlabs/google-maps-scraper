# Outreach pipeline — flow improvement roadmap

## Context

You asked for an opinionated read on how the outreach flow can be
improved, sourced from both an internal architecture review (architect
agent over `outreach/`) and external best-practice research (web search
on B2B lead-gen, deliverability, compliance, observability). This file
synthesizes both into a single prioritized roadmap.

The pipeline is sound — three campaigns delivered, rules-of-record
discipline (never drop rows, sibling flags, append-only sidecars) is
real, and the SBERT→agent classifier migration measurably improved
quality (main F1 0.43 → 0.78). What's below is the *next* layer of
work: the gaps that compound as you add verticals and the strategic
holes vs. how mature B2B outbound teams operate.

---

## Tier 0 — Strategic gaps (do these, or accept the ceiling)

These are not code-level fixes. Each one caps how far the current
pipeline can go regardless of internal polish.

### S1. Close the sales-feedback loop

**The single largest weakness.** CSV→sales is one-way today; you have
no signal on which leads bounced, replied, were interested, or
converted. Without it: pain weights, tier thresholds, and the F1
target itself are uncalibrated guesses. Modern outbound orgs retrain
scoring weekly–monthly off structured disposition codes (Default 2025,
Reform.app feature engineering, Leadgen Economy 2025).

**Architecturally** (architect rec #6): don't build a CRM. Two thin
pieces:
- `outreach/scripts/ingest_dispositions.py` — reads a CSV sales dumps,
  appends to `enrichment/sales_dispositions/<date>.json` (append-only,
  matches existing pattern). Schema as sketched in TODO.md, with
  history (latest-wins is a UI decision, not a data decision).
- **Consume at validate, not handoff.** Validate is already the
  sibling-flag boundary. Add `email_bounced`, `prior_disposition` on
  the lead, and auto-blocklist domains after 3 bounces in 30 days.
  Handoff filters out converted / not_interested, surfaces interested
  at the top.

The CSV ingester is a 1-day MVP. Replace it later with a Slack
webhook / CRM integration without touching the consuming wiring.

**Effort:** M · **Open question for you:** what does sales actually
have today — Google Sheet, HubSpot, raw email logs? Defines the
ingest format.

### S2. Move scoring from one-axis to two-axis (fit × intent)

Today `quality_score = log10(reviews) + rating_gap + weighted_pain`.
That's the *Pain* slot of MEDDIC and the activity-signal of fit, but
nothing else. Best-in-class teams use fit (firmographics, ICP match)
× intent (engagement, behavior, timing). [Clearbit/HubSpot,
Default 5-step model 2025, Warmly 2026.]

**Concrete first step:** add a `fit_score` column composed from
already-collected signals — practice age (years on Google), website
presence (`crawl_status == 'success'`), staff size proxy (POC count
from crawler), socials presence, location-count signal (independent
vs chain). Tier becomes `fit × pain`, not just `pain`. No new data
collection needed; just composition. Once the feedback loop ships
(S1), tune weights against conversion outcomes.

**Effort:** S · **Why now:** unlocks meaningful tier comparison
across verticals (currently retail/cosmetic ship dental's pain
weights — labeled "unproven" in their own configs).

### S3. Add a deliverability gate before handoff

Google/Yahoo/Microsoft May 2025 bulk-sender rules: <0.3% complaint
rate, <2% bounce, mandatory SPF+DKIM+DMARC for >5K/day. Independent
verification (ZeroBounce/Kickbox/NeverBounce, ~95–99.6% claimed)
catches what RFC-shape validators don't. Without this gate, sales'
sending domain reputation degrades silently until inbox placement
collapses.

**Concrete:** `validate.py` already has the right shape. Add an
optional `--verify-with <provider>` flag that pipes
`trustworthy_emails` through Kickbox/ZeroBounce, sets
`email_verification_status` per address, and emits a
`bounce_risk_score` per lead. Don't drop — sibling-flag invalid like
the rest. Cost ~$0.005/email for ~200/campaign = $1, but the
sending-domain reputation it protects is worth orders of magnitude
more.

**Effort:** S · **Open question:** which sending tool/domain does
sales use today? That determines whether SPF/DKIM/DMARC is your
problem or theirs.

### S4. Compliance posture if scope expands beyond US

Current campaigns (dental Sunbelt, retail Toronto, cosmetic Dallas)
mix US + CA. CASL is stricter than CAN-SPAM — *implied or express
consent* required, scraped lists are explicitly flagged risk.
Penalties up to CAD $10M.

**Concrete:**
- Provenance is already partially there (per-field `_source` /
  `_added_at`). Add `lead_data_source` at the lead level
  (`google_maps_scrape`) and `scrape_query` so origin is auditable.
- Add `outreach/lib/suppression.py` + a `suppression_list.txt`
  checked at handoff. Solves "customer asked us to stop", the
  bounce-blocklist (S1), and creates the substrate for any opt-out
  request that comes in.
- If you ever go to EU/UK, the legitimate-interest test (genuine
  business reason, role-relevance, no surprise) becomes a
  per-vertical attestation — defer until needed.

**Effort:** S · **Why P0 for retail_toronto specifically:** CASL is
already in scope.

### S5. Decision-maker enrichment scaling

Manual `owner_lookup.py` is right-shaped for SMB and idempotent, but
won't scale past ~75 A+B/campaign without burning your time.
Apollo (~$0.002/email, $49/user/mo) + Clay-style waterfall
(Apollo→RocketReach→Hunter) hits ZoomInfo accuracy at 30–40% the
cost on SMB data (Saber Q3 2025, Unkoa 2025).

**Concrete:** TODO.md already proposes the right shape — slot an
automated provider behind `--print-queue` writing the sidecar; the
`--apply` interface stays unchanged. Defer until volume justifies
($50/mo for Apollo is trivial; the question is whether your time
saved is the bottleneck or the deal flow is).

**Effort:** M (post-vendor-pick) · **Decision required:** when does
your sales-team capacity start outpacing supply? Until then, manual
is fine.

---

## Tier 1 — Internal architecture (compounding cost)

These are concrete code-level wins from the architect review. Each
gets cheaper now than after the 4th vertical lands.

### A1. Per-delivery `run.json` manifest

Each `outputs/<date>/` has no record of *what produced it*. Adding
`run.json` (stage list, git_sha, input file SHA-256s, classifier
prompt SHA, taxonomy SHA, counts) turns audit from "read prose" to
`diff` two manifests. Implement once in `scripts/_common.py`; every
script appends.

**Effort:** S · Mirrors dbt-manifest pattern from web research §7.

### A2. Cache the classify stage on `(review_text, taxonomy_sha, prompt_sha)`

The only LLM stage. Today every rerun is full-cost and
nondeterministic. A single shared on-disk cache at
`outreach/.cache/pain_classifier/<sha>.json` makes reruns cheap and
deterministic. Side benefit: chain-sibling reviews (same text scraped
under multiple locations) cache-hit instead of paying twice.

**Effort:** M

### A3. Pre-classify dispatch filter

Currently the runbook proposes "top-N by quality_score, default all."
But `quality_score` pre-classify is `log10(reviews) + rating_gap` —
chains, zero-negative-review leads, and tier-D leads are not filtered
before LLM dispatch. Skip them; they're guaranteed-empty hits or
not-pitchable anyway. Surface filter counts in the spot-check.

**Effort:** S

### A4. Fold `merge_crawl_into_master` into `enrich.py`'s tail

Hidden coupling. `enrich.py:74` says `next: classify`, but you must
run `merge_crawl_into_master.py` between them or validate ships
empty `crawled_emails`. The "always run" rule lives in prose only.
Either fold the merge into `enrich.py` (preferred) or fix the `next:`
hint and add a programmatic guard in `validate.py`.

**Effort:** S

### A5. End-to-end shape test

71 unit tests, zero integration test. The "never drop rows" rule is
prose-enforced. Two real bugs already shipped that an e2e test would
have caught (`merge_classifications` not refreshing `quality_score`;
`all_emails` leaking validate-flagged junk — both fixed 2026-05-01).

**Concrete:** `outreach/tests/test_e2e_shape.py` with a 5-lead
synthetic raw NDJSON, runs `analyze → merge_crawl (no-op) →
merge_classifications → validate → handoff`. Asserts row preservation,
junk-email routing, DSO flagging, CSV completeness, pain-driven
ranking. Each assertion maps to a CLAUDE.md rule.

**Effort:** M

### A6. Hostname-redirect brittleness in `merge_crawl_into_master`

Crawl follows redirects (`website_redirect_target` already captured).
If the resolved hostname differs from the gosom-input hostname, the
join silently drops crawl data. Index by both hostnames; surface a
`redirect_match_count` stat.

**Effort:** S

### A7. Schema-validate sidecars + drop dead schema fields

Two related cleanups:
- `merge_classifications.py` should assert every `(main, sub)` pair
  in the sidecar appears in the parsed `pain_categories.md`
  taxonomy. Hallucinated categories error instead of merging.
- Drop dead fields: `score` duplicate of `quality_score`,
  `pain_hits = {}` legacy SBERT slot, `or l.get('pain_hits')`
  fallback in csv_builder. They confuse readers and constrain
  refactors. CLAUDE.md rule 1 means "preserve provenance", not
  "every field that ever existed must remain forever."

**Effort:** S

### A8. `validate_pipeline_config` pre-flight

Three pipelines depend on the same config attribute set
(`PAIN_WEIGHTS`, `SERVICE_MAP`, `DSO_TITLE_REGEX`, …). None of it
is enforced — a typo in retail's config crashes mid-stage with a
`KeyError`. Add a validator in `scripts/_common.py` that the
`/outreach` pre-flight calls; structured error listing all
missing/malformed keys at once.

**Effort:** S · Defers the chain-registry refactor (correctly per
TODO.md) but stops new verticals from drifting in shape.

---

## Tier 2 — Lower priority / nice-to-have

- **Suppression-list infra** (covered partly in S4) — 30-line addition
  to handoff that solves multiple problems.
- **Cross-pipeline lead dedup** — same `place_id` scraped under
  multiple verticals. Defer until it bites; one-shot script later
  is cheaper than infrastructure now.
- **Crawler stealth fallback** — if Cloudflare-blocked sites become
  a noticeable share of the retry queue, add `playwright-stealth`
  fallback before scaling worker count. Concurrency model is fine.
- **Production confidence histogram in run.json** — feeds A1; lets
  you spot taxonomy/agent drift across deliveries before sales does.
  Cheaper than expanding the gold set until S1 ships conversion data.
- **JSON-LD via `extruct`** — defer is correct (TODO.md). Most
  practice sites lack structured data; `extruct` doesn't fix
  no-data-at-all.

---

## Recommended sequence

If you're picking what to do next, this is my opinion on order:

1. **A1 (run.json manifest)** + **A4 (enrich auto-merge)** — half a
   day; immediately removes two operator papercuts.
2. **A5 (e2e shape test)** — the safety net that lets you do
   everything below without fear of regressions.
3. **S3 (deliverability gate)** + **S4 (suppression list)** — these
   protect sales' sending reputation; cheap and don't depend on
   anyone else.
4. **S1 (sales feedback loop, MVP)** — biggest strategic unlock;
   needs a 30-min conversation with sales first to define the
   ingest format.
5. **A2 (classify cache)** + **A3 (pre-classify filter)** — token
   cost reduction once the cache is in place.
6. **S2 (fit × pain scoring)** — once S1 is feeding back data,
   weights stop being guesses.
7. Everything else as it bites.

---

## What I am NOT proposing (and why)

- A workflow orchestrator (Airflow/Prefect/dbt). Three pipelines,
  one operator. Bash + slash command is right-sized.
- The chain registry. TODO.md correctly defers this to the 4th
  vertical. A8 covers the immediate config-shape pain.
- ZoomInfo. Cost vs SMB-coverage tradeoff is wrong; Apollo+waterfall
  is the SMB pattern.
- Replacing the gold set with conversion data immediately — F1 stays
  a useful drift detector even after S1 ships, just no longer the
  only signal.

---

## Files referenced

Internal: `outreach/{README.md, CLAUDE.md, TODO.md}`,
`.claude/commands/outreach.md`, `.claude/agents/pain-classifier.md`,
`outreach/scripts/{analyze,enrich,validate,handoff,
merge_crawl_into_master,merge_classifications,owner_lookup}.py`,
`outreach/lib/{handoff/csv_builder,enrichers/website_crawl,
chain_detection,ranking}.py`, `outreach/pipelines/*/config.py`,
`outreach/pipelines/dental_sunbelt/eval/eval_runner.py`.

External (selected): SPOTIO 2025 (qualification frameworks), Default
2025 (5-step lead scoring), Painsight WASSA@ACL 2023 (unsupervised
pain extraction), Instantly bulk-sender 2026, Digital Bloom B2B
deliverability 2025, Mailpool compliance checklist 2025, Saber Q3
2025 (Apollo vs ZoomInfo vs Clay), Leadgen Economy 2025 (feedback
loops), Datadog dbt-expectations 2025.

---

## Verification

This is a roadmap, not an implementation. To verify any single item
when you pick it up:

- Tier 1 items (A1–A8) all have clear file boundaries. Each gets a
  unit test or e2e assertion before declaring done; existing TDD
  rules apply.
- Tier 0 items (S1–S5) require a decision/conversation first
  (sales-team integration shape, sending-domain ownership,
  compliance scope, vendor budget). I've flagged the open question
  on each.
