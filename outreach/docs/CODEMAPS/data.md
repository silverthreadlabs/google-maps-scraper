<!-- Generated: 2026-06-15 | Files scanned: campaigns/ layout + merge scripts | Token estimate: ~750 -->

# Data model (codemap)

**No relational database.** State is JSON files on disk under `campaigns/<v>_<loc>/`. The "tables" are file kinds; "migrations" are append-only stage merges. Persisted leads ultimately land in the stl-knights backend via `push_leads` (see `dependencies.md`).

## On-disk layout — `campaigns/<v>_<loc>/`

| Path | Kind | Mutability |
|------|------|-----------|
| `raw/*.json` | gosom NDJSON scrapes (canonical source) | **Immutable** |
| `queries/*.txt` | rendered per-city query lines | regenerable |
| `enrichment/website_crawl.json` | crawl sidecar (emails/pocs/socials) | append-only |
| `enrichment/pain_classifications/<date>.json` | classifier sidecar | append-only |
| `enrichment/osint/<date>.json` + `osint_judgments/<date>.json` | OSINT candidates + binder verdicts | append-only |
| `enrichment/owner_lookups/<date>.json`, `decision_makers/<date>.json`, `translations/<date>*.json`, `contacts/<date>*.json` | per-stage sidecars | append-only |
| `outputs/<date>/master.json` | **central state** per delivery | in-place stage updates (atomic) |
| `outputs/<date>/handoff.csv` | sales deliverable | one per delivery date |

## master.json — state versions (join key: `place_id`)

```
raw/*.json
  │ analyze.py                          (dedupe, chain detect, base quality_score, email partition)
  ▼ master v0
  │ enrich → website_crawl.json → merge_crawl_into_master.py
  ▼ master v1   + crawled_emails / pocs / crawled_socials / crawl_status
  │ pain-classifier → pain_classifications/<date>.json → merge_classifications.py
  ▼ master v2   + agent_pain_hits / weighted_pain / quality_score / tier  (recomputed)
  │ osint_enrich → osint/<date>.json → osint-binder → osint_judgments → merge_osint_into_master.py
  ▼ master v3   + linkedin_url_poc / poc_email / social_urls … (only ≥ OSINT_CONFIDENCE_THRESHOLD)
  │ validate.py
  ▼ master v4   + emails_invalid[] / phone_invalid / pocs[*].invalid   (flags, never strips)
  │ (optional) owner_lookup / decision_makers / merge_translations
  ▼ handoff.py → handoff.csv      |      push_leads.py → stl-knights API
```

## Field conventions

- **Provenance on every added field:** `<field>_source` + `<field>_added_at`. Original preserved as `<field>_raw` when normalization rewrote it.
- **Bad values → sibling flags**, never deletion: `email_invalid`/`email_invalid_reason`, `phone_invalid`, `pocs[*].invalid`.
- **Reviews:** merge `user_reviews` (~10%) **and** `user_reviews_extended` (~90%); dedupe by `(reviewer_name, description[:120])`.
- **Lead identity:** `place_id` (dedupe + all merge joins). Crawl merge additionally joins by normalized hostname (`url_normalize`).

## Idempotency / audit

Merges skip rows already carrying the target field (by provenance) → resumable. Each delivery is a frozen `outputs/<date>/` folder; re-deliver into a new date, never overwrite. Sidecars isolate expensive LLM output from cheap deterministic merges (atomic temp+rename write).
