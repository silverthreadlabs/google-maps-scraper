<!-- Generated: 2026-06-15 | Files scanned: campaign_config.py, verticals/*, locations/*, campaigns/*/{campaign.yaml,overrides.py} | Token estimate: ~650 -->

# Configuration (codemap)

A campaign's effective config is merged from 3 layers by `lib/campaign_config.load_campaign(slug) -> CampaignConfig` (302 lines). `lib/cli/_common.load_pipeline_config` is the stage-facing entry.

## Merge order (later overrides earlier)

```
verticals/<v>/config.py        # vertical template (pain weights, services, DSO regex, enrich + OSINT profile)
        +
locations/<loc>.yaml           # pure geo: cities, metro_area_codes, geographic_prefixes, neighborhoods, country, locale
        +
campaigns/<v>_<loc>/overrides.py   # OPTIONAL per-campaign tweaks
        ↓
campaign.yaml binds them:  { vertical: <v>, location: <loc>, slug: <v>_<loc> }
```
Merge helpers: `_concat_regex`, `_union_sets`, `_overlay_dict`, `_merge`. Regex/sets are **unioned** (not replaced); dicts overlay.

## Layer 1 — `verticals/<v>/config.py` (knobs)

| Key | Consumed by |
|-----|-------------|
| `PAIN_WEIGHTS` (keyed by STL `main` names) | merge_classifications, handoff |
| `SERVICE_MAP` (pain → STL service pitch) | handoff |
| `DSO_TITLE_REGEX`, `DSO_EMAIL_DOMAINS` | analyze / chain_detection |
| `GEOGRAPHIC_PREFIXES_GENERIC` (category words e.g. "family dental") | chain_detection |
| `VENDOR_DOMAINS_EXTRA` | validate (email) |
| `ENRICH_PROFILE` (= `EnrichProfile`: selectors, link gates, person markers) | enrich |
| `INDEPENDENT_FILTERS` | handoff subset views |
| `OSINT_*` (`FIELDS_DESIRED`, `CONFIDENCE_THRESHOLD`, `SERP_QUERIES`, `DEEP_CRAWL_PATHS`, `INDUSTRY_TERMS`, `SOURCES`) | osint_enrich, osint-binder |

Verticals present: `dentist`, `software`, `cosmetic_surgery`, `retail`, `automotive` (each: `config.py` + `query_templates.txt` + `README.md`).

## Layer 2 — `locations/<loc>.yaml` (geo, vertical-reusable)

`country`, `locale`, `cities[]` each with `name`, `state`, `metro_area_codes[]` (phone mismatch), `geographic_prefixes[]` (anti-false-chain), `neighborhoods[]`. Present: `dallas`, `sunbelt`, `toronto`, `sanfrancisco`, `ua`.

## Layer 3 — `campaigns/<v>_<loc>/overrides.py` (optional)

Region-specific extras merged onto vertical defaults: `DSO_TITLE_REGEX_EXTRA`, `DSO_EMAIL_DOMAINS_EXTRA`, `PAIN_WEIGHTS` override.

## Pain taxonomy (separate, vertical-agnostic)

`silverthread/pain_categories.md` — STL pain hierarchy the `pain-classifier` subagent reads every run. `PAIN_WEIGHTS`/`SERVICE_MAP` keys must match its `main` names.

## Add a campaign / vertical

See `../README.md` "Adding a campaign" / "Adding a new vertical" and `../../CLAUDE.md`. Rule: copy a campaign + edit config; **never fork `lib/`**.
