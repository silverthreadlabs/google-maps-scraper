# OSINT Enrichment Stage — Design

**Status:** Spec
**Date:** 2026-05-07
**Author:** Brainstormed with Claude (superpowers:brainstorming)
**Scope:** Add a free-tier OSINT enrichment stage to the outreach pipeline that fills gaps left by `website_crawl` and `owner_lookup`.

## Goals

Enrich leads with the data SDRs need but the existing pipeline often misses:

- LinkedIn URLs (company + POC)
- Other social URLs (Instagram, Facebook, Twitter)
- POC name, role, and email — bound confidently to the right person
- News / press mentions (URLs only)

Constraints:

- **Free**: no paid OSINT APIs (Hunter, Apollo, Proxycurl, etc.). LLM subagent calls are acceptable as they already exist in the pipeline (`pain-classifier`).
- **No LinkedIn page visits.** SERP-only discovery — never load `linkedin.com` directly. URLs come from search-engine result snippets that mention them.
- **Confident-or-skip.** If we cannot bind a candidate to the lead with high confidence, we do not ship it. False positives are worse than misses.
- **Small batches.** Designed for 50–150 leads/campaign with multi-hour runs acceptable. No rotating proxies; agent-browser session pool on a single residential IP.

## Non-Goals

- LinkedIn page scraping (ToS, account-ban risk).
- Email pattern guessing (`firstname.lastname@domain`) — explicitly out of scope per the confident-or-skip rule.
- SMTP probing or full deliverability checks (downstream sales tool already does this).
- Per-state SOS / business-registry scraping (deferred to v2 — high build effort, decide from v1 hit-rate data).
- Google My Business deep re-scrape beyond what `gosom` already captures (deferred to v2).
- Auto-population of fields the user's master already has values for (immutability per `outreach/CLAUDE.md` rule 1).

## Stage placement

Extends `.claude/commands/outreach.md`. Runs **after** `merge_crawl_into_master` and `owner_lookup --apply`, **before** `classify`:

```
scrape → analyze → enrich (website_crawl) → merge_crawl_into_master
       → owner_lookup --print-queue → owner_lookup --apply
       → osint_enrich [NEW]
       → merge_osint_into_master [NEW]
       → classify (pain-classifier) → merge_classifications
       → validate → handoff / push_leads
```

Why right after `owner_lookup`: the OSINT planner inspects each lead, sees which target fields are still empty (i.e., what `website_crawl` and `owner_lookup` did not fill), and only runs the enrichers needed to fill those gaps. POC name discovered by `owner_lookup` (or by deep-site-crawl in this stage) feeds SERP queries.

## Module layout

Extends existing patterns; no fork of `lib/`.

```
lib/enrichers/
  website_crawl.py             # existing
  serp.py                      # NEW — Google/Bing/DDG via agent-browser, captcha-aware
  deep_site_crawl.py           # NEW — /about /team /leadership /contact + JSON-LD
  whois_lookup.py              # NEW — python-whois wrapper
  tests/
    test_serp.py
    test_deep_site_crawl.py
    test_whois_lookup.py

scripts/
  osint_enrich.py              # NEW — orchestrator
  merge_osint_into_master.py   # NEW — grafts confident hits with provenance
  tests/
    test_osint_enrich.py
    test_merge_osint_into_master.py

.claude/agents/
  pain-classifier.md           # existing
  osint-binder.md              # NEW — Haiku-based LLM-judge for candidate→lead binding

pipelines/dental_sunbelt/eval/
  pain_classifier/             # existing
  osint_binding/               # NEW
    gold_set.json
    eval_runner.py
    README.md
```

## Per-enricher behavior

Run order per lead (cheap/deterministic first, brittle/rate-limited last):

```
WHOIS  →  deep_site_crawl  →  SERP  →  LLM-judge (per-lead, per-field batch)
```

Two-wave orchestration: discovery wave (WHOIS + deep_site_crawl can surface POC name we did not have) → field-fill wave (SERP queries reuse the discovered name) → judge → write sidecar.

### `lib/enrichers/whois_lookup.py`

`python-whois` against the lead's domain. Parses `registrant_name`, `registrant_email`, `registrant_org`. ~70% are privacy-redacted (clean miss, no candidate emitted). The 30% with real data go to the judge — registrant might be the business owner OR a webmaster/agency/reseller, so binding is the judge's job.

Rate limit: most TLDs allow ~50 whois queries/hour from one IP. For 50–150 leads/campaign, no throttling needed. Single-threaded.

Failure modes: redacted → clean miss; no whois server response → retry once, then skip; parse error → log + skip.

### `lib/enrichers/deep_site_crawl.py`

Given the known domain (we already have it from `website_crawl`), fetches a small set of high-leverage paths:

```python
DEFAULT_PATHS = [
    "/about", "/about-us", "/our-team", "/team", "/staff",
    "/leadership", "/our-doctors", "/dentists",   # dental-specific paths come from config
    "/contact", "/contact-us",
]
```

Two extractors:

1. **JSON-LD / schema.org** — parses `Person`, `Organization`, `founder`, `employee` fields. Highest signal; cleanly typed; near-certain binding (data is on the lead's own site).
2. **Heading + proximity extraction** — extends `lib/validators/poc_validator.py` (which already handles `Contact Dr.`, `About Dr.`, `Meet Dr.` per recent hardening). Looks for name → role → email/phone in nearby DOM nodes.

Skips URLs `website_crawl.py` already fetched (reads `enrichment/website_crawl.json` to dedupe).

Failure modes: 404 on every guessed path → clean miss; JS-only / SPA → use existing agent-browser-rendered fetch from `website_crawl.py`; no JSON-LD or recognizable patterns → clean miss.

### `lib/enrichers/serp.py`

Agent-browser-driven Google / Bing / DDG search. Per-vertical query templates in `pipelines/<name>/config.py`:

```python
SERP_QUERIES = {
  "linkedin_url_poc":     'site:linkedin.com/in "{poc_name}" "{city}" {industry_term}',
  "linkedin_url_company": 'site:linkedin.com/company "{business_name}" "{city}"',
  "social_urls":          '"{business_name}" "{city}" instagram OR facebook OR twitter',
  "news_mentions":        '"{business_name}" "{city}" news OR press OR opening',
}
```

Returns `{url, title, snippet, engine, query}` per result; ~5–10 results per query.

Engine fallback ladder: **DDG → Bing → Google** (DDG has the lightest rate limits, Google the heaviest captcha aggression). On captcha: cooldown 2–5 min, retry on next engine; if all three blocked, emit `serp_blocked: true` and skip the field for this lead. Jittered 2–5 sec delay between queries on the same engine.

We never load the URLs the SERP returns. We never visit `linkedin.com`. The URL string and the snippet the search engine has indexed are the entire payload.

### `.claude/agents/osint-binder.md` (LLM-judge subagent)

Haiku-based, dispatched in batches per the `pain-classifier` pattern. Input: lead context + candidate set for one field. Output:

```json
{
  "best_match_index": 0,
  "confidence": 0.95,
  "reasoning": "snippet directly names the lead's business and city",
  "rejected": [
    {"index": 1, "reason": "different industry — Software Engineer at Google"}
  ]
}
```

Or, when no candidate clears the bar:

```json
{
  "best_match_index": null,
  "confidence": 0.0,
  "reasoning": "no candidate provides corroborating signal beyond name match",
  "rejected": [...]
}
```

Default threshold `0.85`, configurable per vertical. Below threshold → skip (confident-or-skip rule). Both accepted and rejected candidates land in the sidecar with the judge's reasoning, so threshold tuning later does not require re-fetching.

## Parallelism

Per `outreach/CLAUDE.md` rule 4 — session pool, not round-robin. Cross-target lanes, serial per target:

- **Lane 1 (SERP)**: one agent-browser session pinned to the SERP engines. Jittered, captcha-aware.
- **Lane 2 (deep_site_crawl)**: agent-browser session pool, same pattern as `website_crawl.py`.
- **Lane 3 (WHOIS)**: deterministic Python, no browser.

Each lane processes leads serially; lanes run concurrently. LLM-judge invoked per-lead-per-field after all lanes have produced their candidates for that lead.

Realistic free-tier speedup: ~2–3x over fully serial. Hard ceiling — shared residential IP dominates Google/Bing rate limits regardless of internal parallelism.

## Sidecar schema

`pipelines/<name>/enrichment/osint/<date>.json` — one record per lead, all candidates including rejected:

```jsonc
{
  "place_id": "ChIJ...",
  "domain": "smithfamilydental.com",
  "enriched_at": "2026-05-07T15:00:00Z",
  "fields": {
    "linkedin_url_poc": {
      "candidates": [
        {
          "value": "https://linkedin.com/in/john-smith-phoenix-dds",
          "source": "serp_google",
          "query": "site:linkedin.com/in \"Dr. John Smith\" \"Phoenix\" dental",
          "snippet": "Dr. John Smith — Owner at Smith Family Dental",
          "judge_verdict": "match",
          "judge_confidence": 0.95,
          "judge_reasoning": "snippet directly names lead's business and city"
        },
        {
          "value": "https://linkedin.com/in/john-smith-2342",
          "source": "serp_google",
          "snippet": "John Smith - Software Engineer at Google",
          "judge_verdict": "rejected",
          "judge_confidence": 0.0,
          "judge_reasoning": "different industry"
        }
      ],
      "selected_index": 0,
      "selected_confidence": 0.95
    },
    "poc_email": {
      "candidates": [],
      "selected_index": null,
      "skipped_reason": "no_results"
    },
    "linkedin_url_company": {
      "candidates": [/* ... */],
      "selected_index": null,
      "skipped_reason": "below_threshold"
    }
  },
  "errors": []
}
```

Why all candidates including rejected: threshold tuning. If we later raise/lower the threshold, `merge_osint_into_master.py` re-runs over the existing sidecar with no re-fetching — same shape `merge_classifications.py` already uses. Rejected candidates with reasoning are also gold for the eval harness.

## Merge contract

`scripts/merge_osint_into_master.py` joins by `place_id`. For each field with `selected_index != null AND selected_confidence >= threshold`:

```python
master_lead[field] = candidate.value
master_lead[f"{field}_source"] = f"osint_{candidate.source}"     # e.g. "osint_serp_google"
master_lead[f"{field}_added_at"] = enriched_at
master_lead[f"{field}_confidence"] = candidate.judge_confidence
master_lead[f"{field}_query"] = candidate.query                    # SERP only
master_lead[f"{field}_judge_reasoning"] = candidate.judge_reasoning
```

**Immutability rule** (`outreach/CLAUDE.md` rule 1): if the master already has a non-empty value for `<field>`, we do NOT overwrite. Keep first-seen, log a notice. Re-merge with a different threshold can only ADD fields that were previously skipped, never replace ones that were grafted.

**Validators still gate at the boundary** (`outreach/CLAUDE.md` rule 5): any `email` field grafted from OSINT goes through `lib/validators/email_validator.py`. Judge confidence does not bypass syntax / disposable / vendor-domain checks. Failed validation → sibling `<field>_invalid: true` per the existing pattern.

**Handoff CSV opt-in:** `pipelines/<name>/config.py` has `OSINT_HANDOFF_FIELDS = [...]` listing which OSINT fields appear in the final CSV. Default for dental: `linkedin_url_poc`, `linkedin_url_company`, `social_urls`. Audit fields (`_source`, `_confidence`, `_query`) stay in master but not in the CSV unless explicitly added.

## Per-vertical config

`pipelines/<name>/config.py` extension:

```python
# OSINT enrichment
OSINT_ENABLED = True
OSINT_SOURCES = ["whois", "deep_site_crawl", "serp"]   # toggle per source
OSINT_FIELDS_DESIRED = [
    "linkedin_url_company",
    "linkedin_url_poc",
    "social_urls",
    "poc_name",
    "poc_email",
    "poc_role",
    "news_mentions",
]
OSINT_CONFIDENCE_THRESHOLD = 0.85
OSINT_HANDOFF_FIELDS = ["linkedin_url_poc", "linkedin_url_company", "social_urls"]

OSINT_SERP_QUERIES = {
    "linkedin_url_poc":     'site:linkedin.com/in "{poc_name}" "{city}" dentist OR DDS OR DMD',
    "linkedin_url_company": 'site:linkedin.com/company "{business_name}" "{city}" dental',
    "social_urls":          '"{business_name}" "{city}" instagram OR facebook OR twitter',
    "news_mentions":        '"{business_name}" "{city}" news OR press OR opening',
}

OSINT_DEEP_CRAWL_PATHS = [
    "/about", "/about-us", "/our-team", "/team", "/staff",
    "/leadership", "/our-doctors", "/dentists",         # vertical-specific
    "/contact", "/contact-us",
]

OSINT_INDUSTRY_TERMS = ["dentist", "DDS", "DMD", "dental practice"]
```

Other verticals (`cosmetic_surgeons_dallas`, `retail_toronto`, `insurance_sf`) fork these knobs. `lib/` stays vertical-agnostic per `outreach/CLAUDE.md`.

## Eval harness

Mirror `pipelines/dental_sunbelt/eval/pain_classifier/` shape:

```
pipelines/dental_sunbelt/eval/osint_binding/
  gold_set.json     # 50–100 hand-labeled (lead, candidates, correct_index | null)
  eval_runner.py    # runs osint-binder on gold set
  README.md
```

Reports:

- **Precision** (primary) — confident-or-skip means false-positives hurt most.
- **Recall at threshold** — how many real matches we capture.
- **Threshold sweep** across `[0.70, 0.80, 0.85, 0.90, 0.95]` — pick threshold from data.

Bootstrap: run OSINT once on real `dental_sunbelt` leads, hand-correct the judge's verdicts, save labeled set. Same iterative workflow as the pain-classifier eval.

## Resumability

Same as `website_crawl.py` and `owner_lookup.py`:

- Sidecar written incrementally as each lead completes.
- Restart skips leads already processed.
- `--force` re-runs everything.

State stored in the sidecar itself; no separate state file.

## Manual queue (deferred to v1.1)

When ALL desired fields come back empty for a lead, optionally surface via `osint_enrich.py --print-queue` (matches `owner_lookup.py` shape). SDR researches manually, pastes findings into a structured input, `--apply` grafts them.

Decision: defer to v1.1. If v1's hit-rate is 60–70% the manual queue is high-value; if 90%+ it is overkill. Decide from real data.

## Failure modes (summary)

| Source | Failure | Behavior |
|---|---|---|
| WHOIS | redacted | clean miss, no candidate |
| WHOIS | no server response | retry once, then skip |
| deep_site_crawl | 404 on all paths | clean miss |
| deep_site_crawl | JS-only / SPA | use existing agent-browser fallback |
| SERP | captcha | engine fallback ladder; if all three blocked, skip field with `serp_blocked: true` |
| SERP | zero results | clean miss |
| LLM-judge | low confidence | skip per confident-or-skip |
| LLM-judge | timeout / error | log + skip the field, do not crash batch |

## Testing

Per `outreach/TDD-RULES.md`:

- `lib/enrichers/tests/test_serp.py` — mocked SERP HTML, captcha detection, engine fallback.
- `lib/enrichers/tests/test_deep_site_crawl.py` — mocked HTML with JSON-LD, proximity patterns, 404 paths.
- `lib/enrichers/tests/test_whois_lookup.py` — mocked redacted + unredacted responses.
- `scripts/tests/test_osint_enrich.py` — gap-detection, two-wave ordering, judge dispatch.
- `scripts/tests/test_merge_osint_into_master.py` — immutability respected, threshold filter, validator gating preserved.

## Runbook update

`.claude/commands/outreach.md` — new stage entry between `owner_lookup --apply` and `classify`:

```
## OSINT enrich

`/outreach <pipeline> osint-enrich`

Runs after merge_crawl_into_master + owner_lookup --apply. Inspects each
lead's gaps against OSINT_FIELDS_DESIRED, runs enrichers (whois →
deep_site_crawl → serp), batches binding judgments through the
osint-binder subagent. Writes enrichment/osint/<date>.json. Resumable.

next: python outreach/scripts/merge_osint_into_master.py --pipeline <name>
```

## Field-shape clarifications

Some fields are list-typed in master (multiple URLs may all clear the threshold and all are useful). Others are single-valued (one definitive answer or none).

| Field | Cardinality in master | Notes |
|---|---|---|
| `linkedin_url_company` | single | one canonical URL |
| `linkedin_url_poc` | single | per the primary POC; if there are multiple POCs, only the one matched by `poc_name` is filled |
| `social_urls` | list of `{platform, url}` | each candidate represents one platform; all that clear threshold land in master |
| `news_mentions` | list of `{url, title, snippet}` | all that clear threshold; cap at ~5 most recent |
| `poc_name` | single | the primary contact |
| `poc_email` | single | bound to `poc_name` |
| `poc_role` | single | bound to `poc_name` |

For list-typed fields, provenance is per-element: each list item carries its own `source`, `confidence`, `query`, `judge_reasoning` — not a single field-level provenance object.

## Two-wave orchestration: name disambiguation

Wave 1 (WHOIS + deep_site_crawl) may return multiple candidate `poc_name` values with different confidences. Wave 2's SERP queries that require `{poc_name}` use the highest-confidence above-threshold candidate. If no Wave-1 candidate clears the threshold AND `owner_lookup` did not provide a name, SERP queries needing `{poc_name}` are skipped this run — they emit no candidates, and the field is marked `skipped_reason: "no_poc_name_known"` in the sidecar. A subsequent run after manual `owner_lookup` can re-attempt.

## Open questions for implementation

- **Initial threshold**: `0.85` is the design default. The eval gold set on real `dental_sunbelt` leads will move it. Tune before first production run.
- **Industry-term richness for non-dental verticals**: dental has a clean term set (`dentist`, `DDS`, `DMD`). Broader verticals (retail, insurance) will need their own term lists in `OSINT_INDUSTRY_TERMS`. Decided per-vertical when the OSINT stage is enabled for that pipeline.
- **Cross-pipeline batching**: a single `osint_enrich.py` invocation processes one pipeline at a time. Cross-pipeline batching deferred unless throughput becomes a constraint.

## Out of scope (explicit)

- Paid OSINT APIs (Hunter, Apollo, Snov, Dropcontact, Proxycurl).
- LinkedIn page scraping or any direct `linkedin.com` request.
- Email pattern guessing without verification.
- SMTP probing.
- Rotating residential proxies.
- SOS / state business registry scraping (v2 candidate).
- Google My Business deep re-scrape (v2 candidate).
- Manual queue (v1.1 candidate).
