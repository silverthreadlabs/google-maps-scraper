# Software UA campaign

Ukrainian software / digital / design agencies (Kyiv, Lviv, Dnipro)
as prospects for Ezly. See `verticals/software/README.md` for fit
notes and `overrides.py` for the UA-specific outsourcer list.

## Custom scripts

This campaign has 4 one-off scripts under `scripts/`:

- `build_classify_batches.py` — top-N lead selection + review batching
- `build_enrich_queue.py` — websites to crawl (whitelist + foreign-filter)
- `merge_batches.py` — sidecar assembly from batch outputs
- `retry_via_curl.py` — recoverable subset of the playwright retry queue

These are NOT generalized into `outreach/lib/cli/` — they carry
campaign-specific filter lists (`WHITELIST`, `FOREIGN_TITLE_TOKENS`,
`PRODUCT_EXCLUDE_TITLES`, `FOREIGN_BRANDS`). Generalization is a
separate refactor.

Invoke from the repo root, e.g.:

```bash
python outreach/campaigns/software_ua/scripts/build_classify_batches.py
```
