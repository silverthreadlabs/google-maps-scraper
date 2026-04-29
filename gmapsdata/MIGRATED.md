# This folder has been migrated

All Python modules and dental campaign data are now under `outreach/`.

| Old location | New location |
|---|---|
| `gmapsdata/email_validity.py` | `outreach/lib/validators/email.py` |
| `gmapsdata/phone_validity.py` | `outreach/lib/validators/phone.py` |
| `gmapsdata/poc_extract.py` | `outreach/lib/validators/poc.py` |
| `gmapsdata/test_*.py` | `outreach/lib/validators/tests/` |
| `gmapsdata/analyze_dental.py` | Decomposed into `outreach/lib/pain/regex.py`, `outreach/lib/chain_detection.py`, `outreach/lib/ranking.py`, `outreach/pipelines/dental_sunbelt/config.py` |
| `gmapsdata/crawl_dental_full.py` | `outreach/lib/enrichers/website_crawl.py` |
| `gmapsdata/crawl_dental_emails.py` | `outreach/lib/enrichers/website_crawl_v1_legacy.py` |
| `gmapsdata/build_handoff_csv.py` | `outreach/lib/handoff/csv_builder.py` |
| `gmapsdata/dentists_*.json` | `outreach/pipelines/dental_sunbelt/raw/`, `outputs/2026-04-25/` |
| `gmapsdata/dental_*.json` | `outreach/pipelines/dental_sunbelt/enrichment/` |
| `gmapsdata/HANDOFF_README.md` | `outreach/pipelines/dental_sunbelt/outputs/2026-04-25/HANDOFF_README.md` |
| `gmapsdata/queries_dentists_*.txt` | `outreach/pipelines/dental_sunbelt/queries/` |
| `gmapsdata/insurance_sf*` | `outreach/pipelines/insurance_sf/` |

Files NOT migrated (left in place because they're not ours):
- `*.csv` from April 14 (pre-this-work, gosom scraper test outputs)
- `jobs.db*` (gosom scraper state)
