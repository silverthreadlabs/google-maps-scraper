# Outreach Pipeline — Architecture

Companion to `architecture.excalidraw` (open in <https://excalidraw.com>). This document explains what each layer does, how state flows, and which invariants hold across the system.

---

## 1. Purpose

The `outreach/` tree turns raw Google Maps scrapes into a sales-ready CSV (and optional CRM push) by passing leads through a **fixed sequence of pipeline stages**. Each stage is a Python script under `outreach/lib/cli/`, except `classify`, which is an LLM subagent invocation. The whole sequence is orchestrated by a single slash-command runbook: `.claude/commands/outreach.md`.

Two design rules dominate everything below:

1. **Never drop rows or replace field values** (CLAUDE.md rule 1). Bad values get sibling flags (`email_invalid`, `phone_invalid_reason`); they are never stripped. Every added field carries `<field>_source` + `<field>_added_at` provenance.
2. **`lib/` is industry-agnostic**; all vertical-specific knobs live in `verticals/<v>/config.py (+ optional campaigns/<v>_<loc>/overrides.py)`. To add a vertical, copy `campaigns/dentist_sunbelt/` and edit `config.py` — never fork `lib/`.

---

## 2. Top-level layers

```
┌──────────────────────────────────────────────────────────────────┐
│  /outreach <pipeline> <stage>   ← .claude/commands/outreach.md   │
│  (slash-command runbook — the only user-facing entry point)      │
└──────────────────────────────────────────────────────────────────┘
        │  dispatches
        ▼
┌──────────────────────────────────────────────────────────────────┐
│  PIPELINE STAGES   outreach/lib/cli/*.py                         │
│  analyze → enrich → classify → osint-enrich → validate → handoff │
└──────────────────────────────────────────────────────────────────┘
        │  reads / writes
        ▼
┌──────────────────────────────────────────────────────────────────┐
│  DATA  outputs/<date>/master.json   (central state)              │
│        enrichment/<sidecar>.json    (append-only per stage)      │
└──────────────────────────────────────────────────────────────────┘
        │  uses
        ▼
┌──────────────────────────────────────────────────────────────────┐
│  lib/   chain_detection · ranking · url_normalize ·              │
│         validators · enrichers · handoff · scrapers              │
└──────────────────────────────────────────────────────────────────┘
```

Two LLM **subagents** (`.claude/agents/`) plug into the stages that need judgment rather than deterministic transformation:

- `pain-classifier` → feeds the `classify` stage
- `osint-binder` → feeds the `osint-enrich` stage

---

## 3. Directory map

```
outreach/
├── CLAUDE.md                        # repo-rules for agents
├── README.md                        # daily-driver overview
├── TDD-RULES.md                     # test discipline for this tree
├── docs/                            # design docs (this file lives here)
├── lib/                             # industry-agnostic shared code
│   ├── chain_detection.py
│   ├── ranking.py
│   ├── url_normalize.py
│   ├── validators/                  # email, phone — boundary guards
│   ├── enrichers/                   # website_crawl, osint candidate sources
│   ├── handoff/                     # csv_builder
│   └── scrapers/                    # gosom adapter
├── scripts/                         # the pipeline stages
│   ├── analyze.py
│   ├── enrich.py + merge_crawl_into_master.py
│   ├── merge_classifications.py
│   ├── osint_enrich.py + merge_osint_into_master.py
│   ├── owner_lookup.py
│   ├── validate.py
│   ├── handoff.py
│   ├── push_campaign.py / push_leads.py     # CRM delivery
│   └── _common.py
├── silverthread/
│   └── pain_categories.md           # STL pain taxonomy (vertical-agnostic)
└── campaigns/<v>_<loc>/
    ├── config.py                    # PAIN_WEIGHTS, DSO regex, METROS, …
    ├── raw/                         # gosom NDJSON scrapes  (IMMUTABLE)
    ├── enrichment/                  # append-only sidecars
    │   ├── pain_classifications/<date>.json
    │   ├── website_crawl.json
    │   ├── osint/<date>.json
    │   ├── osint_judgments/<date>.json
    │   └── owner_lookups/<date>.json
    └── outputs/<date>/              # one folder per delivery
        ├── master.json
        └── handoff.csv
```

---

## 4. Orchestration — `/outreach`

`.claude/commands/outreach.md` is a runbook the agent follows when the user types `/outreach <pipeline> <stage>`. It is not a Python entry point — it is a Markdown-defined protocol that tells the assistant:

- which script to invoke for each stage (or which subagent to dispatch for `classify`/`osint-enrich`)
- the exact CLI flags, default paths, and the pre-flight checks (e.g. import-test the pipeline config before doing anything)
- how to handle re-deliveries (write into a new ISO-dated `outputs/<date>-N/` rather than overwriting)
- the post-stage hand-off summary the assistant must print

This means orchestration logic lives in version-controlled prose, not in a bespoke runner. Adding a new stage means adding a section to `outreach.md` plus the underlying script.

---

## 5. The 6 pipeline stages

Each stage reads the latest `outputs/<date>/master.json` (or `raw/` on first run) and either updates master in-place or writes an append-only sidecar that a `merge_*` step later grafts back into master.

| # | Stage | Script | Output | What it does |
|---|-------|--------|--------|--------------|
| 1 | **analyze** | `analyze.py` | `outputs/<date>/master.json` | Dedupe raw scrapes by `place_id`, chain detection, initial `quality_score`, partition gosom emails into `emails` vs `emails_invalid` via `lib/validators/email`. |
| 2 | **enrich** | `enrich.py` + `merge_crawl_into_master.py` | `enrichment/website_crawl.json`, then grafted into master | Crawl each lead's website with a session-pool worker, extract `crawled_emails` / `pocs` / `crawled_socials`. The merge step joins by hostname and adds provenance fields. |
| 3 | **classify** | LLM-only via `pain-classifier` subagent, then `merge_classifications.py` | `enrichment/pain_classifications/<date>.json`, then grafted into master | Classify reviews against the STL pain taxonomy. The merge step recomputes `weighted_pain`, `quality_score`, and `tier` from `PAIN_WEIGHTS` in `config.py`. |
| 4 | **osint-enrich** | `osint_enrich.py` (waves: whois + deep_site_crawl → serp) → `osint-binder` subagent (per-batch judgment) → `--apply-judgments` → `merge_osint_into_master.py` | `enrichment/osint/<date>.json` + `osint_judgments/<date>.json` | For leads missing `OSINT_FIELDS_DESIRED`, collect candidates, ask the binder to judge them with confidence scoring, and graft only hits above `OSINT_CONFIDENCE_THRESHOLD` (default 0.85). |
| 5 | **validate** | `validate.py` | annotates master in place | Run `lib/validators/{email,phone}` over the post-enrichment data, append sibling flags (`emails_invalid[]`, `phone_invalid`, `pocs[*].invalid`). Never strips. |
| 6 | **handoff** | `handoff.py` (uses `lib/handoff/csv_builder`) | `outputs/<date>/handoff.csv` | Build the sales-facing CSV. `PAIN_WEIGHTS` + `SERVICE_MAP` (both keyed by STL `main` names) drive the ranking and the per-lead service recommendation columns. |

**Optional post-stages:**

- **owner-lookup** (`owner_lookup.py`) — two-step queue/apply flow for filling `owner_name` on tier-A/B leads via manual web search; idempotent and provenance-clean. After `--apply`, re-run `handoff`.
- **push** (`push_campaign.py` / `push_leads.py`) — ships the CSV / leads to the downstream CRM (Mixmax / Instantly).

**Re-delivery flow:** when classifier or taxonomy changes, re-run from `analyze --output-date <new-date>` so the prior delivery stays intact as the audit record. The merge scripts join on `place_id`, so the master fed to merge must carry it (analyze guarantees this).

---

## 6. LLM subagents

Both subagents live under `.claude/agents/` and are dispatched via the `Agent` / `Task` tool with a tightly scoped tool budget (`Read, Write` only).

### `pain-classifier`

- **Input:** list of `{id, text}` review rows, in batches of 20–40.
- **Required first read:** `outreach/silverthread/pain_categories.md` (the taxonomy is read every invocation — never classified from memory).
- **Output:** for each review, zero/one/many `{main, sub, confidence, quote, reasoning}` entries. `quote` must be a verbatim substring of `text`. Out-of-taxonomy → emit nothing. `sub` is null when no listed sub fits — don't force the closest match.
- **Dispatch shape:** all batches sent in **one assistant message** so the runtime parallelizes them; per-batch outputs are joined via an in-memory `review_index[id]` keyed by `place_id`.
- **Quality gate:** stratified spot-check (≥1 sample per `main` that fired) + mean confidence check (flag if <0.6). Sidecar is written atomically; conflicting same-day file goes to `<date>-2.json`.

### `osint-binder`

- **Input:** records of `{place_id, field, lead, candidates[]}` produced by `osint_enrich.py`.
- **Output:** per record, a list of `{index, verdict, confidence, reasoning}` plus `best_match_index` and `selected_confidence`.
- **Binding rules (encoded in the agent prompt):**
  1. **Confident-or-skip** — match needs ≥2 corroborating signals from {business name, city, industry, POC name, domain, phone}.
  2. POC name alone is necessary but not sufficient.
  3. Industry mismatch and geographic mismatch are hard rejects.
  4. Confidence >0.9 requires 3+ corroborating signals; 0.85–0.9 is the typical match band; below 0.85 → reject.
  5. WHOIS registrant matches need domain or business-name corroboration (registrant might be a webmaster).
- Only judgments at or above `OSINT_CONFIDENCE_THRESHOLD` get grafted into master.

Both agents are deliberately **non-strategist, non-summarizer**. Their job is structured classification/binding output, not narrative.

---

## 7. Data flow & state model

`outputs/<date>/master.json` is the single source of truth per delivery. The pipeline is intentionally **append-only at the data layer**:

```
raw/*.json  (immutable, canonical)
    │
    ▼  analyze.py
master.json (v0 — dedupe, chain, base score)
    │
    │  enrich.py → website_crawl.json
    ▼  merge_crawl_into_master.py
master.json (v1 — + crawled_emails / pocs / crawl_status)
    │
    │  pain-classifier → pain_classifications/<date>.json
    ▼  merge_classifications.py
master.json (v2 — + agent_pain_hits / weighted_pain / tier)
    │
    │  osint_enrich.py → osint/<date>.json
    │  osint-binder    → osint_judgments/<date>.json
    │  --apply-judgments
    ▼  merge_osint_into_master.py
master.json (v3 — + linkedin_url_poc / owner_email / …)
    │
    ▼  validate.py
master.json (v4 — + email/phone/poc invalid flags)
    │
    │  (optional) owner_lookup.py --apply
    │
    ▼  handoff.py
handoff.csv (sales delivery)
```

Each merge step is **resumable and idempotent**: scripts skip rows already carrying the target field (matched by provenance), so partial runs can be re-driven without double-writing.

### Why sidecars instead of writing master directly

- **Audit trail.** A failed classifier run leaves the prior `pain_classifications/<previous-date>.json` intact; you can diff to see what changed.
- **Cost isolation.** LLM stages are expensive — sidecars let a deterministic merge be re-run cheaply.
- **Crash safety.** Atomic write (`temp + rename`) of a sidecar can't corrupt master.
- **Parallelism.** Sidecar producers (e.g. classifier batches) can run concurrently; the merge is a single ordered pass.

---

## 8. Shared library (`lib/`)

`lib/` is the only place industry-agnostic logic lives. **Vertical-specific values never leak in.**

| Module | Purpose | Consumed by |
|--------|---------|-------------|
| `chain_detection.py` | Detect chain/DSO listings; respects `GEOGRAPHIC_PREFIXES` from each pipeline's `config.py` so same-metro practices sharing a brand prefix aren't false-positive chained. | analyze |
| `ranking.py` | `quality_score` / `tier` calculation from pain weights. | analyze, merge_classifications |
| `url_normalize.py` | Canonical hostname → join key for crawl/enrich merges. | enrich, merge_crawl_into_master |
| `validators/email.py` | Boundary guard: rejects placeholder/image-artifact/vendor emails. Used at gosom ingest time AND post-crawl. | analyze, enrich, validate |
| `validators/phone.py` | E.164 normalization, metro-area-code mismatch check. | validate |
| `enrichers/website_crawl.py` | Session-pool crawler (queue.Queue lease — never round-robin assignment, per CLAUDE.md rule 4). | enrich |
| `enrichers/osint/*` | WHOIS, SERP, deep-site-crawl candidate producers. | osint_enrich |
| `handoff/csv_builder.py` | The CSV schema; reads sibling `*_invalid` flags so validate must run first. | handoff |
| `scrapers/` | Gosom adapter — translates the raw JSON shape into the pipeline's expected fields. | analyze |

**Adding a new false-positive class is always a `lib/` change with a test**, not a downstream fix. Validators guard at the boundary, not the consumer.

---

## 9. Per-vertical configuration

`verticals/<v>/config.py (+ optional campaigns/<v>_<loc>/overrides.py)` is the only place vertical-specific knobs live:

| Key | Used by | Why per-vertical |
|-----|---------|------------------|
| `PAIN_WEIGHTS` | merge_classifications, handoff | Pain priorities differ by industry (a dental cancellation matters more than a software shop's slow reply). Keyed by STL `main` names. |
| `SERVICE_MAP` | handoff | Which Silverthread service to pitch for each pain main. |
| `DSO_TITLE_REGEX`, `DSO_EMAIL_DOMAINS` | analyze | Chain-org membership patterns. |
| `GEOGRAPHIC_PREFIXES` | chain_detection | Same-metro brand prefixes that should NOT be chain-detected. |
| `METROS`, `METRO_AREA_CODES` | analyze, validate | Geo tagging + phone mismatch detection. |
| `VENDOR_DOMAINS_EXTRA` | validate | Vertical-specific marketing-vendor email rejects. |
| `ENRICH_PROFILE` | enrich | Crawl behavior — selectors, max pages, allowlists. |
| `OSINT_FIELDS_DESIRED`, `OSINT_CONFIDENCE_THRESHOLD` | osint-enrich | Which gaps to chase and how strict to be. |

**To add a vertical:** copy `campaigns/dentist_sunbelt/`, edit `config.py`, drop new query files in `queries/`, scrape into `raw/`, then run `/outreach <new-vertical> analyze`.

---

## 10. Invariants (the things you can't violate without breaking the pipeline)

1. **Append-only data.** Every stage adds fields with `_source` / `_added_at`. Filtering is a subset view in a new file, never a mutation of master.
2. **Reviews come from both `user_reviews` AND `user_reviews_extended`.** Reading only the first drops ~90% of the pain signal (CLAUDE.md rule 3).
3. **Raw scrapes never go to `/tmp`.** They are the most valuable artifact and `/tmp` is auto-cleaned by systemd-tmpfiles (CLAUDE.md rule 2).
4. **Crawler parallelism uses a session pool**, not round-robin assignment (CLAUDE.md rule 4) — otherwise concurrent tasks contaminate each other's browser state.
5. **Pain-key contract.** `SERVICE_MAP` and `PAIN_WEIGHTS` are keyed by STL `main` names (`calls_unanswered`, `booking_friction`, …) — same keys the classifier emits as `hit['main']`. Sub-level weight granularity is intentionally deferred.
6. **Validate before handoff.** Handoff reads sibling `*_invalid` flags; skipping validate produces a CSV with `phone_invalid: None` strings and section-heading captures (`"MEET THE"`) in the `pocs` column.
7. **One delivery per dated folder.** Re-deliveries write `outputs/<new-date>/`; the prior folder is the audit record.

---

## 11. Where to look when…

| Question | File |
|----------|------|
| How is a stage invoked? | `.claude/commands/outreach.md` (the stage's section) |
| What does the classifier emit? | `.claude/agents/pain-classifier.md` |
| What are the OSINT binding rules? | `.claude/agents/osint-binder.md` |
| What pain categories exist? | `outreach/silverthread/pain_categories.md` |
| What knobs does this vertical have? | `outreach/campaigns/<vertical>/config.py` |
| How is `quality_score` computed? | `outreach/lib/ranking.py` + `merge_classifications.py` |
| Why was a row dropped from the CSV? | It wasn't — check `emails_invalid`, `phone_invalid`, `tier` in master. |
| Why is `crawled_emails` empty? | `merge_crawl_into_master.py` wasn't run after `enrich.py`. |
| How to add a vertical? | Copy `campaigns/dentist_sunbelt/`, edit `config.py`. Never fork `lib/`. |

---

## 12. Related docs

- `outreach/README.md` — daily-driver commands, quick-start
- `outreach/CLAUDE.md` — rules the assistant must follow when editing this tree
- `outreach/TDD-RULES.md` — test discipline
- `outreach/docs/flow-improvement-roadmap.md` — backlog of pipeline ergonomics work
- `outreach/docs/2026-05-07-osint-enrichment-design.md` — OSINT stage design rationale
- `outreach/docs/architecture.excalidraw` — visual companion to this document
