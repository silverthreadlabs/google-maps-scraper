<!-- Generated: 2026-06-15 | Files scanned: lib/cli/*.py (18) | Token estimate: ~900 -->

# Pipeline (codemap)

Stages = `lib/cli/*.py`. Each is a standalone CLI (`main(argv) -> int`) taking a `<pipeline>` slug, run individually or chained by `/outreach`. Two stages (`classify`, `osint judge`) are LLM subagents, not scripts.

## Stage flow

```
scrape*  → analyze → enrich → (merge_crawl) → classify** → (merge_classifications)
        → osint_enrich → osint-binder** → (merge_osint) → validate → handoff → push
optional: translate/merge_translations · decision_makers · owner_lookup · contacts
```
`*` Docker/gosom (no script).  `**` LLM subagent (`.claude/agents/`).

## Stage → script → output

| Stage | Script (`lib/cli/`) | Key fns | Writes |
|-------|--------------------|---------|--------|
| analyze | `analyze.py` | `load_raw`, `dedupe_by_place_id`, `merge_reviews`, `partition_emails`, `build_lead`, `analyze` | `outputs/<date>/master.json` (v0) |
| enrich | `enrich.py` (drives `enrichers/website_crawl.run_pool`) | `main` | `enrichment/website_crawl.json` |
| merge crawl | `merge_crawl_into_master.py` | `index_crawl_by_hostname`, `graft` | master (v1) |
| classify | LLM `pain-classifier` | — | `enrichment/pain_classifications/<date>.json` |
| merge class | `merge_classifications.py` | `merge` (recomputes `quality_score`/`weighted_pain`/`tier`) | master (v2) |
| osint-enrich | `osint_enrich.py` | `detect_gaps`, `select_osint_leads`, `enrich_lead`, `apply_judgments_to_sidecar` | `enrichment/osint/<date>.json` |
| osint judge | LLM `osint-binder` | — | `osint_judgments/<date>.json` |
| merge osint | `merge_osint_into_master.py` | `graft` (threshold `OSINT_CONFIDENCE_THRESHOLD`) | master (v3) |
| validate | `validate.py` | `annotate_emails`, `annotate_phone`, `annotate_pocs` | master (v4, `*_invalid` flags) |
| handoff | `handoff.py` (uses `handoff/csv_builder.build_handoff`) | `main`, `_owner_lookup_candidates` | `outputs/<date>/handoff.csv` |
| translate | `translate.py` → `merge_translations.py` | `select_for_translation`, `snippet_key`; `merge` | `enrichment/translations/<date>*.json` → master |
| decision-makers | `decision_makers.py` | `select_queue`, `apply_sidecar`, `backfill_owner_pocs`, `_designate_primary_and_project` | `enrichment/decision_makers/<date>.json` → master |
| owner-lookup | `owner_lookup.py` | `main` (queue/apply) | `enrichment/owner_lookups/<date>.json` → master |
| contacts | `contacts.py` | `main` | contact export |
| push campaign | `push_campaign.py` | `upsert_campaign` → `POST /campaigns` | stl-knights backend |
| push leads | `push_leads.py` | `transform_lead`, `push_chunk` → `POST /leads/campaigns/:id/import` (chunks of 50) | stl-knights backend |

## Shared CLI helpers — `lib/cli/_common.py`

`load_dotenv` · `load_pipeline_config(name)` · `pipeline_dir(name)` · `add_pipeline_arg` · `require_attr` · `pipeline_lock(name, stage)` (PID-aware lock).

POC helpers — `lib/cli/_pocs.py`: `poc_from_person`, `pick_primary_index`, `is_primary_role`, `owner_scalars_from_poc`, `merge_channels_into_poc`.

## Conventions

- `latest_master(pdir)` resolves newest `outputs/<date>/master.json`; `write_atomic` = temp+rename.
- merges are **idempotent** — skip rows already carrying the target field (by provenance); join key is `place_id` (crawl merge joins by normalized hostname).
- re-delivery: `analyze.py --output-date <new-date>` writes a fresh `outputs/<date>/`; prior folder is the audit record.

CLI signatures & flags: `../README.md` "Command reference". State versions: `data.md`.
