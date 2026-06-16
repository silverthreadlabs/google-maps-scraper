<!-- Generated: 2026-06-15 | Files scanned: lib/{,validators,enrichers,handoff}/*.py | Token estimate: ~850 -->

# Shared library (codemap)

`lib/` is industry-agnostic — no vertical knobs, no hardcoded category names. CLI stages (`lib/cli/`, see `pipeline.md`) compose these. Consumers noted per module.

## Top-level `lib/`

| Module (lines) | Key API | Used by |
|----------------|---------|---------|
| `campaign_config.py` (302) | `load_campaign(slug) -> CampaignConfig`; merges vertical + location + overrides | every stage (`_common.load_pipeline_config`) |
| `chain_detection.py` (131) | `ChainDetector(.fit/.classify_one) -> ChainResult`; `extract_hostname`, `extract_brand_prefix`, `email_domain_is_dso` | analyze |
| `ranking.py` (119) | `quality_score(...)`, `tier(score) -> Tier` (legacy open-ended scale, unchanged); **blended rating:** `score_lead(lead) -> dict`, `service_fit_norm(...)`, `blended_tier(score)` (0–100, tiers 75/50/25) | analyze, merge_classifications, csv_builder |
| `reachability.py` (153) | `reachability_score(lead) -> (0–50, breakdown)`, `usable_contacts(lead)`, channel detectors `is_personal_linkedin` / `is_reachable_email` / `is_personal_social` | ranking.score_lead |
| `url_normalize.py` (75) | `normalize_url(url)` — strip tracking params, canonical hostname | enrich, merge_crawl, handoff |
| `render_queries.py` (93) | `render_for_campaign(...)` — query template × location → per-city query files | query generation |
| `lead_fields.py` (86) | `resolve_business_name`, `resolve_city`, `resolve_poc_name` (lead-field accessors) | handoff, push |
| `lang_detect.py` (28) | `needs_translation(snippet, locale)` (Cyrillic heuristic) | translate |

## `lib/validators/` — boundary guards (reject false positives at ingest, not downstream)

| Module | API |
|--------|-----|
| `email.py` (117) | `validate_email(...)` — placeholder/image-artifact/vendor rejects |
| `phone.py` (85) | `normalize(phone)` (E.164), `validate_phone(...)` (metro area-code mismatch) |
| `poc.py` (204) | `validate_poc(name)`, `poc_confidence(poc)` — badge/section-heading rejects |

## `lib/enrichers/` — contact + OSINT candidate producers

| Module (lines) | API | Notes |
|----------------|-----|-------|
| `website_crawl.py` (632) | `EnrichProfile` (dataclass), `run_pool(...)`, `crawl_url(...)`, `lease_single_session(...)`, `filter_valid_emails` | session-pool crawler via agent-browser subprocess; **largest module** |
| `deep_site_crawl.py` (198) | `crawl_domain(...)`, `extract_jsonld_persons`, `extract_heading_proximity_persons`, `plan_fetch_paths` | OSINT person discovery |
| `serp.py` (140) | `run_serp_query_with_fallback(query, fetch_fn)`, `parse_{google,bing,ddg}_results`, `is_blocked` | OSINT search w/ engine fallback |
| `whois_lookup.py` (83) | `lookup_domain(domain)` (`python-whois`), `_is_redacted` | OSINT registrant |
| `poc_filters.py` (70) | `flag_review_author_pocs(...)`, `is_reviewer_label` | strips review-author false POCs |

## `lib/handoff/`

| Module (lines) | API |
|----------------|-----|
| `csv_builder.py` (419) | `build_handoff(...)`, `_build_row(...)`, `top_pain_with_quotes(...)`, `trustworthy_emails`, `primary_contact`, `apply_url_normalization` — reads `*_invalid` flags (validate must run first); delegates tier to `ranking.blended_tier` and recomputes the blended grade authoritatively at output (DDD-0001) |

## Tests

Co-located: `lib/**/test_*.py` and `lib/*_tests.py`. Run all: see `../../CLAUDE.md` "Workflow" / `../../TDD-RULES.md`.
