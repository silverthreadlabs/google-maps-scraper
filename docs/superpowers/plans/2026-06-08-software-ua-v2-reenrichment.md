# software_ua_v2 Re-enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-deliver the Ukrainian software-firm leads as a new campaign `software_ua_v2` that is deeply enriched — each high-value lead carrying a named, reachable decision-maker and English-translated pain quotes — by fixing two pipeline gaps and running the decision-maker stages that were skipped.

**Architecture:** Reuse the existing outreach pipeline. Add a reusable, locale-gated `translate` stage (sidecar + merge, mirroring `classify`/`merge_classifications`); add English/`_original` pain-quote columns and `primary_contact`/`primary_contact_channel` to the handoff; wire `locale` onto `CampaignConfig` and let campaign `overrides.py` tune the OSINT targeting. Then run the full chain (incl. owner-lookup + osint-enrich) on the tier A/B/C subset behind a 20-lead feasibility pilot.

**Tech Stack:** Python 3.12, `unittest` (run each test file with `python <file>`), no new third-party dependencies. Config is the merge of `verticals/software/config.py` + `locations/ua.yaml` + `campaigns/<slug>/overrides.py` via `lib/campaign_config.py`.

**Spec:** `docs/superpowers/specs/2026-06-08-software-ua-v2-reenrichment-design.md`

---

## Context the implementer needs

- **The software vertical is already Ezly-ICP-tuned.** `verticals/software/config.py` maps every pain to "Ezly — AI Communication Assistant", weights `frontline_communication`/`followup_dropped` highest, targets Founder/CEO/Owner/Partner/Director in `poc_title_markers_js`, and biases `OSINT_SERP_QUERIES["linkedin_url_poc"]` toward "CEO OR founder". Do **not** re-add ICP weighting — the campaign override only *extends* it (UA outsourcer exclusions already exist; we add BizDev/sales emphasis to the SERP query).
- **Do NOT extend the POC validator.** Measurement showed re-running `validate` (which already calls `poc_confidence`) sinks the badge POCs; only 3/489 tech-ish names survive, on a column that is now secondary. The POC tech-token denylist was explicitly dropped from the spec.
- **`agent_pain_hits` shape** (on each lead): `{ "<main_category>": [ {"sub","confidence","snippet","rating","reviewer","reasoning"}, ... ] }`. The handoff's `top_pain_with_quotes` reads `hit["snippet"]`.
- **CLAUDE.md rule 1:** never drop rows or replace values — add fields with `_source`/`_added_at` provenance; atomic write (temp + rename).
- **Test convention:** each test file starts with `sys.path.insert(0, <outreach root>)`, uses `unittest`, ends with `if __name__ == '__main__': unittest.main(verbosity=2)`. Run a single file: `python outreach/lib/<...>/test_x.py`.
- **Full test loop** (run before declaring done):
  ```bash
  cd /home/fassihhaider/Work/google-maps-scraper
  for t in $(find outreach/lib outreach/tests -name 'test_*.py' -o -name '*_tests.py'); do python "$t" || echo "FAIL: $t"; done
  ```

## File structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `outreach/campaigns/software_ua_v2/campaign.yaml` | Names vertical=software, location=ua, slug |
| Create | `outreach/campaigns/software_ua_v2/overrides.py` | UA outsourcer exclusions + ICP OSINT SERP override |
| Create | `outreach/campaigns/software_ua_v2/raw/*.json` | Copied raw scrape NDJSONs (immutable) |
| Create | `outreach/campaigns/software_ua_v2/enrichment/pain_classifications/2026-05-22.json` | Copied classification sidecar (reuse) |
| Modify | `outreach/lib/campaign_config.py` | Expose `locale`/`country`; merge OSINT fields from overrides |
| Create | `outreach/lib/lang_detect.py` | `needs_translation(snippet, locale)` |
| Create | `outreach/lib/lang_detect_tests.py` | Tests for the detector |
| Create | `outreach/lib/cli/translate.py` | Build the translation-request sidecar (locale/script gated) |
| Create | `outreach/lib/cli/tests/test_translate.py` | Tests for snippet selection |
| Create | `outreach/lib/cli/merge_translations.py` | Graft `snippet_en` onto `agent_pain_hits` |
| Create | `outreach/lib/cli/tests/test_merge_translations.py` | Tests for the merge |
| Modify | `outreach/lib/handoff/csv_builder.py` | English/`_original` quote columns + `primary_contact` |
| Modify | `outreach/lib/handoff/tests/test_csv_builder.py` | Tests for the new columns |
| Modify | `outreach/lib/campaign_config_tests.py` | Tests for locale + OSINT override merge |
| Modify | `.claude/skills/outreach/SKILL.md` | Register `translate` stage in the runbook |

---

## Task 0: Scaffold the `software_ua_v2` campaign

**Files:**
- Create: `outreach/campaigns/software_ua_v2/campaign.yaml`
- Create: `outreach/campaigns/software_ua_v2/overrides.py`
- Copy: raw NDJSONs + classification sidecar

- [ ] **Step 1: Create the campaign directory and copy immutable inputs**

```bash
cd /home/fassihhaider/Work/google-maps-scraper
mkdir -p outreach/campaigns/software_ua_v2/raw
mkdir -p outreach/campaigns/software_ua_v2/enrichment/pain_classifications
cp outreach/campaigns/software_ua/raw/*.json outreach/campaigns/software_ua_v2/raw/
cp outreach/campaigns/software_ua/enrichment/pain_classifications/2026-05-22.json \
   outreach/campaigns/software_ua_v2/enrichment/pain_classifications/2026-05-22.json
# Reuse the existing website crawl — same raw, same hostnames. Re-crawling is
# the biggest time sink and risks different data from listing churn (CLAUDE.md
# rule 2). The badge-POC problem was a scoring issue (fixed by re-running
# validate), not a crawl-data issue, so the crawl payload is reused as-is.
cp outreach/campaigns/software_ua/enrichment/website_crawl.json \
   outreach/campaigns/software_ua_v2/enrichment/website_crawl.json
ls -la outreach/campaigns/software_ua_v2/raw/
```

Expected: `dnipro.json`, `kyiv.json`, `lviv.json` present; `enrichment/website_crawl.json` copied.

- [ ] **Step 2: Write `campaign.yaml`**

Create `outreach/campaigns/software_ua_v2/campaign.yaml`:

```yaml
vertical: software
location: ua
slug: software_ua_v2
```

- [ ] **Step 3: Write `overrides.py` (copy UA brands; ICP OSINT override added in Task 3)**

For now, copy the existing UA-brand override verbatim so the campaign loads. The ICP SERP override is appended in Task 3 (after the config wiring it depends on exists).

```bash
cp outreach/campaigns/software_ua/overrides.py outreach/campaigns/software_ua_v2/overrides.py
```

- [ ] **Step 4: Verify the campaign config imports cleanly**

```bash
cd /home/fassihhaider/Work/google-maps-scraper
python -c "import sys; sys.path.insert(0,'outreach'); from lib.campaign_config import load_campaign; c=load_campaign('software_ua_v2'); print('slug=',c.slug,'vertical=',c.vertical,'location=',c.location)"
```

Expected: `slug= software_ua_v2 vertical= software location= ua` (no traceback).

- [ ] **Step 5: Commit**

```bash
git add outreach/campaigns/software_ua_v2/campaign.yaml outreach/campaigns/software_ua_v2/overrides.py
git commit -m "chore(outreach): scaffold software_ua_v2 campaign (raw + classification reused)"
```

Note: raw NDJSONs and the copied sidecar are data, not code — confirm with the user whether they are committed or kept local before staging them.

---

## Task 1: Expose `locale` (and `country`) on `CampaignConfig`

The translate stage gates on `locale`, but `CampaignConfig` reads it from the yaml and then drops it. Add the fields.

**Files:**
- Modify: `outreach/lib/campaign_config.py`
- Test: `outreach/lib/campaign_config_tests.py`

- [ ] **Step 1: Write the failing test**

Add to `outreach/lib/campaign_config_tests.py` (inside the existing test class, or a new one — match the file's style):

```python
def test_locale_exposed_from_location_yaml(self):
    from lib.campaign_config import load_campaign
    cfg = load_campaign('software_ua_v2')
    self.assertEqual(cfg.locale, 'uk-UA')
    self.assertEqual(cfg.country, 'UA')
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python outreach/lib/campaign_config_tests.py -k test_locale_exposed_from_location_yaml`
Expected: FAIL — `AttributeError: 'CampaignConfig' object has no attribute 'locale'`.

- [ ] **Step 3: Add the fields to the dataclass**

In `outreach/lib/campaign_config.py`, in the `CampaignConfig` dataclass under `# Identity`, add:

```python
    # Identity
    slug: str
    vertical: str
    location: str
    locale: str = ''
    country: str = ''
```

- [ ] **Step 4: Populate them in `_merge`**

In `_merge`, in the `return CampaignConfig(...)` call, immediately after `location=meta['location'],` add:

```python
        locale=location.get('locale', ''),
        country=location.get('country', ''),
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python outreach/lib/campaign_config_tests.py`
Expected: PASS (all tests, including the new one).

- [ ] **Step 6: Commit**

```bash
git add outreach/lib/campaign_config.py outreach/lib/campaign_config_tests.py
git commit -m "feat(outreach): expose locale/country on CampaignConfig"
```

---

## Task 2: Let campaign `overrides.py` tune the OSINT config

`_merge` currently reads OSINT fields only from the vertical. To put ICP targeting in `overrides.py`, let overrides overlay the SERP queries and extend the desired fields.

**Files:**
- Modify: `outreach/lib/campaign_config.py`
- Test: `outreach/lib/campaign_config_tests.py`

- [ ] **Step 1: Write the failing test**

Add to `outreach/lib/campaign_config_tests.py`. This uses a tiny synthetic override module via the existing `_merge` (import the helpers the file already imports; mirror how other tests there construct inputs). If the test file builds configs only through `load_campaign`, instead assert against `software_ua_v2` after Task 3 — but prefer a direct `_merge` unit test here:

```python
def test_overrides_overlay_osint_serp_queries(self):
    from types import SimpleNamespace
    from lib.campaign_config import _merge
    vertical = SimpleNamespace(
        OSINT_SERP_QUERIES={'linkedin_url_poc': 'VERTICAL', 'social_urls': 'KEEP'},
        OSINT_FIELDS_DESIRED=['poc_name'],
    )
    overrides = SimpleNamespace(
        OSINT_SERP_QUERIES={'linkedin_url_poc': 'OVERRIDDEN'},
        OSINT_FIELDS_DESIRED=['poc_role'],
    )
    cfg = _merge(
        {'slug': 's', 'vertical': 'software', 'location': 'ua'},
        vertical,
        {'metros': [], 'metro_area_codes': {}, 'geographic_prefixes': set(),
         'locale': 'uk-UA', 'country': 'UA'},
        overrides,
    )
    self.assertEqual(cfg.osint_serp_queries['linkedin_url_poc'], 'OVERRIDDEN')
    self.assertEqual(cfg.osint_serp_queries['social_urls'], 'KEEP')
    self.assertIn('poc_name', cfg.osint_fields_desired)
    self.assertIn('poc_role', cfg.osint_fields_desired)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python outreach/lib/campaign_config_tests.py -k test_overrides_overlay_osint_serp_queries`
Expected: FAIL — `linkedin_url_poc` is `'VERTICAL'`, not `'OVERRIDDEN'`.

- [ ] **Step 3: Implement override-aware OSINT merge**

In `outreach/lib/campaign_config.py` `_merge`, replace the three OSINT lines:

```python
        osint_fields_desired=list(getattr(vertical, 'OSINT_FIELDS_DESIRED', [])),
```
…and…
```python
        osint_serp_queries=dict(getattr(vertical, 'OSINT_SERP_QUERIES', {})),
```
…and…
```python
        osint_industry_terms=list(getattr(vertical, 'OSINT_INDUSTRY_TERMS', [])),
```

with override-aware versions:

```python
        osint_fields_desired=list(dict.fromkeys(
            list(getattr(vertical, 'OSINT_FIELDS_DESIRED', []))
            + (list(getattr(o, 'OSINT_FIELDS_DESIRED', []) or []) if o else [])
        )),
```
```python
        osint_serp_queries=_overlay_dict(
            getattr(vertical, 'OSINT_SERP_QUERIES', {}),
            getattr(o, 'OSINT_SERP_QUERIES', None) if o else None,
        ),
```
```python
        osint_industry_terms=list(dict.fromkeys(
            list(getattr(vertical, 'OSINT_INDUSTRY_TERMS', []))
            + (list(getattr(o, 'OSINT_INDUSTRY_TERMS', []) or []) if o else [])
        )),
```

(`dict.fromkeys(...)` preserves order while de-duping. `_overlay_dict` already exists in the file.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `python outreach/lib/campaign_config_tests.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add outreach/lib/campaign_config.py outreach/lib/campaign_config_tests.py
git commit -m "feat(outreach): merge OSINT config fields from campaign overrides"
```

---

## Task 3: Add the ICP OSINT override to `software_ua_v2/overrides.py`

**Files:**
- Modify: `outreach/campaigns/software_ua_v2/overrides.py`

- [ ] **Step 1: Append the ICP SERP override**

Append to `outreach/campaigns/software_ua_v2/overrides.py` (keep the existing `DSO_TITLE_REGEX_EXTRA` / `DSO_EMAIL_DOMAINS_EXTRA` blocks):

```python
# ── Ezly ICP targeting (campaign-scoped) ────────────────────────────────
# Ezly's buyer is the person who runs client communications — founder,
# co-founder, business-development / sales / partnerships lead — and lives on
# LinkedIn. The software vertical already biases the POC LinkedIn query toward
# "CEO OR founder"; here we widen it to the client-comms roles and add a
# direct people-search query. Overlaid on the vertical via campaign_config.
OSINT_SERP_QUERIES = {
    "linkedin_url_poc":
        'site:linkedin.com/in "{poc_name}" "{city}" '
        '(founder OR CEO OR "business development" OR sales OR partnerships OR owner)',
    "linkedin_url_company":
        'site:linkedin.com/company "{business_name}" "{city}"',
}

# Ensure the person-level decision-maker fields are explicitly desired so the
# osint gap-detector chases them even if the vertical default changes.
OSINT_FIELDS_DESIRED = [
    "linkedin_url_poc", "poc_name", "poc_email", "poc_role",
]
```

- [ ] **Step 2: Verify the override takes effect**

```bash
cd /home/fassihhaider/Work/google-maps-scraper
python -c "import sys; sys.path.insert(0,'outreach'); from lib.campaign_config import load_campaign; c=load_campaign('software_ua_v2'); print(c.osint_serp_queries['linkedin_url_poc']); print(c.osint_fields_desired)"
```

Expected: the `linkedin_url_poc` query contains `business development`, and `osint_fields_desired` contains `poc_name`, `poc_role`, plus the vertical's other fields (order-deduped).

- [ ] **Step 3: Commit**

```bash
git add outreach/campaigns/software_ua_v2/overrides.py
git commit -m "feat(outreach): software_ua_v2 ICP OSINT targeting (client-comms roles + LinkedIn)"
```

---

## Task 4: Language detector — `needs_translation`

**Files:**
- Create: `outreach/lib/lang_detect.py`
- Test: `outreach/lib/lang_detect_tests.py`

- [ ] **Step 1: Write the failing test**

Create `outreach/lib/lang_detect_tests.py`:

```python
"""Tests for the translate-stage language gate."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.lang_detect import needs_translation


class TestNeedsTranslation(unittest.TestCase):
    def test_cyrillic_snippet_needs_translation(self):
        s = "Заказывал доработку сайта, взяли аванс и ничего не сделали"
        self.assertTrue(needs_translation(s, 'uk-UA'))

    def test_english_snippet_in_ua_campaign_skipped(self):
        s = "The program isn't bad, but the manager acts like a debt collector"
        self.assertFalse(needs_translation(s, 'uk-UA'))

    def test_english_locale_always_skips(self):
        s = "Заказывал доработку"  # even Cyrillic is skipped for en campaigns
        self.assertFalse(needs_translation(s, 'en-US'))

    def test_empty_snippet_skipped(self):
        self.assertFalse(needs_translation('', 'uk-UA'))
        self.assertFalse(needs_translation('   ', 'uk-UA'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python outreach/lib/lang_detect_tests.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.lang_detect'`.

- [ ] **Step 3: Implement the detector**

Create `outreach/lib/lang_detect.py`:

```python
"""Lightweight language gate for the translate stage.

`needs_translation(snippet, locale)` decides whether a review snippet should
be sent to the translator subagent.

Two gates, cheap and dependency-free:
  1. Locale gate — English-locale campaigns (`en-*`) never translate.
  2. Script gate — a snippet is sent only if it contains Cyrillic characters.

LIMITATION: the script gate is correct for the current Ukrainian/Russian
campaign (Cyrillic source). A future Latin-script source language (e.g. pl-PL,
es-ES) would pass the locale gate but fail the script gate, yielding a no-op.
When such a campaign appears, replace the script heuristic with a real
detector (e.g. a langdetect dependency) — the rest of the stage is unchanged.
"""
from __future__ import annotations


def _has_cyrillic(s: str) -> bool:
    return any('Ѐ' <= ch <= 'ӿ' for ch in s)


def needs_translation(snippet: str, locale: str) -> bool:
    if not snippet or not snippet.strip():
        return False
    if (locale or '').lower().startswith('en'):
        return False
    return _has_cyrillic(snippet)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python outreach/lib/lang_detect_tests.py`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add outreach/lib/lang_detect.py outreach/lib/lang_detect_tests.py
git commit -m "feat(outreach): add language gate for the translate stage"
```

---

## Task 5: `translate` stage — build the translation-request sidecar

Mirrors `classify`: a script prepares work for an LLM subagent. Here it selects the snippets that will surface in the handoff (top-2 pain quotes per lead), filters through `needs_translation`, and writes a request sidecar keyed by `place_id` → `{snippet_key: snippet}`. The translator subagent fills English (operational, Task 10); `merge_translations` grafts it (Task 6).

**Files:**
- Create: `outreach/lib/cli/translate.py`
- Test: `outreach/lib/cli/tests/test_translate.py`

- [ ] **Step 1: Write the failing test**

Create `outreach/lib/cli/tests/test_translate.py`:

```python
"""Tests for the translate stage's snippet selection."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.cli.translate import snippet_key, select_for_translation


class TestSnippetKey(unittest.TestCase):
    def test_stable_and_whitespace_insensitive(self):
        self.assertEqual(snippet_key('  abc  '), snippet_key('abc'))
        self.assertNotEqual(snippet_key('abc'), snippet_key('abd'))


class TestSelectForTranslation(unittest.TestCase):
    def _lead(self, pid, snippet):
        return {
            'place_id': pid,
            'agent_pain_hits': {
                'frontline_communication': [
                    {'snippet': snippet, 'rating': 1, 'reviewer': 'X'}
                ]
            },
        }

    def test_selects_cyrillic_skips_english(self):
        master = [
            self._lead('p1', 'Заказывал доработку сайта'),
            self._lead('p2', 'The manager never replied'),
        ]
        out = select_for_translation(master, locale='uk-UA',
                                     pain_weights={'frontline_communication': 5})
        self.assertIn('p1', out)
        self.assertNotIn('p2', out)
        (k, v), = out['p1'].items()
        self.assertEqual(v, 'Заказывал доработку сайта')
        self.assertEqual(k, snippet_key('Заказывал доработку сайта'))

    def test_english_locale_yields_empty(self):
        master = [self._lead('p1', 'Заказывал доработку сайта')]
        out = select_for_translation(master, locale='en-US',
                                     pain_weights={'frontline_communication': 5})
        self.assertEqual(out, {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python outreach/lib/cli/tests/test_translate.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.cli.translate'`.

- [ ] **Step 3: Implement the stage**

Create `outreach/lib/cli/translate.py`:

```python
"""
translate — build the translation-request sidecar for a campaign.

The translate stage is locale-gated (no-op for en-* campaigns) and selects the
pain snippets that will surface in the handoff (top-2 pain quotes per lead),
keeping only those that need translation (see lib.lang_detect). It writes a
request sidecar:

    enrichment/translations/<date>_request.json
    { "<place_id>": { "<snippet_key>": "<original snippet>", ... }, ... }

A translator subagent (dispatched by the /outreach skill) reads it and writes
the answer sidecar enrichment/translations/<date>.json with the same keys
mapped to English. merge_translations.py then grafts snippet_en onto master.

Usage:
    python outreach/lib/cli/translate.py <pipeline> [--output-date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.cli._common import (
    add_pipeline_arg, load_pipeline_config, pipeline_dir, pipeline_lock,
)
from lib.handoff.csv_builder import top_pain_with_quotes
from lib.lang_detect import needs_translation

N_QUOTES = 2


def snippet_key(snippet: str) -> str:
    return hashlib.sha1((snippet or '').strip().encode('utf-8')).hexdigest()[:12]


def select_for_translation(master, *, locale, pain_weights):
    """Return {place_id: {snippet_key: original_snippet}} for the handoff-
    surfaced pain quotes that need translation. Pure; no I/O."""
    out: dict[str, dict[str, str]] = {}
    for lead in master:
        pid = lead.get('place_id')
        if not pid:
            continue
        _top, quotes = top_pain_with_quotes(
            lead, pain_weights=pain_weights, n_quotes=N_QUOTES
        )
        for q in quotes:
            snippet = (q.get('snippet') or '').strip()
            if not needs_translation(snippet, locale):
                continue
            out.setdefault(pid, {})[snippet_key(snippet)] = snippet
    return out


def _latest_master(pdir: Path) -> Path | None:
    out_dir = pdir / 'outputs'
    if not out_dir.is_dir():
        return None
    dated = sorted(d for d in out_dir.iterdir() if d.is_dir())
    for d in reversed(dated):
        m = d / 'master.json'
        if m.exists():
            return m
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Build the translation-request sidecar.')
    add_pipeline_arg(parser)
    parser.add_argument('--master', type=Path, default=None)
    parser.add_argument('--output-date', default=None)
    args = parser.parse_args(argv)

    cfg = load_pipeline_config(args.pipeline)
    pdir = pipeline_dir(args.pipeline)
    master_path = args.master or _latest_master(pdir)
    if not master_path or not master_path.exists():
        sys.stderr.write(f"error: master not found for {args.pipeline}\n")
        return 2

    with pipeline_lock(args.pipeline, 'translate'):
        master = json.loads(Path(master_path).read_text())
        requests = select_for_translation(
            master, locale=cfg.locale, pain_weights=cfg.pain_weights
        )
        today = args.output_date or datetime.now(timezone.utc).strftime('%Y-%m-%d')
        req_dir = pdir / 'enrichment' / 'translations'
        req_dir.mkdir(parents=True, exist_ok=True)
        req_path = req_dir / f'{today}_request.json'
        tmp = req_path.with_suffix(req_path.suffix + '.tmp')
        tmp.write_text(json.dumps(requests, indent=2, ensure_ascii=False))
        tmp.replace(req_path)

    n_leads = len(requests)
    n_snips = sum(len(v) for v in requests.values())
    if cfg.locale.lower().startswith('en'):
        print(f"locale={cfg.locale!r} is English — nothing to translate (no-op).", flush=True)
    print(f"wrote {req_path} ({n_snips} snippet(s) across {n_leads} lead(s))", flush=True)
    print(f"next: dispatch the translator subagent over {req_path.name}, write "
          f"enrichment/translations/{today}.json, then run "
          f"merge_translations.py", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python outreach/lib/cli/tests/test_translate.py`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add outreach/lib/cli/translate.py outreach/lib/cli/tests/test_translate.py
git commit -m "feat(outreach): add translate stage (locale-gated translation-request sidecar)"
```

---

## Task 6: `merge_translations` — graft `snippet_en` onto `agent_pain_hits`

**Files:**
- Create: `outreach/lib/cli/merge_translations.py`
- Test: `outreach/lib/cli/tests/test_merge_translations.py`

- [ ] **Step 1: Write the failing test**

Create `outreach/lib/cli/tests/test_merge_translations.py`:

```python
"""Tests for grafting translations into master."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.cli.merge_translations import merge
from lib.cli.translate import snippet_key


class TestMergeTranslations(unittest.TestCase):
    def _master(self):
        snip = 'Заказывал доработку сайта'
        return [{
            'place_id': 'p1',
            'agent_pain_hits': {
                'frontline_communication': [
                    {'snippet': snip, 'rating': 1, 'reviewer': 'X'}
                ]
            },
        }], snip

    def test_grafts_snippet_en_with_provenance(self):
        master, snip = self._master()
        sidecar = {'p1': {snippet_key(snip): 'Ordered a website revision'}}
        stats = merge(master, sidecar)
        hit = master[0]['agent_pain_hits']['frontline_communication'][0]
        self.assertEqual(hit['snippet_en'], 'Ordered a website revision')
        self.assertEqual(hit['snippet_en_source'], 'translator-subagent')
        self.assertIn('snippet_en_added_at', hit)
        self.assertEqual(stats['snippets_translated'], 1)

    def test_idempotent_and_passthrough(self):
        master, snip = self._master()
        # English-source hit with no matching key is left untouched
        sidecar = {'p1': {}}
        merge(master, sidecar)
        hit = master[0]['agent_pain_hits']['frontline_communication'][0]
        self.assertNotIn('snippet_en', hit)


if __name__ == '__main__':
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python outreach/lib/cli/tests/test_merge_translations.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.cli.merge_translations'`.

- [ ] **Step 3: Implement the merge**

Create `outreach/lib/cli/merge_translations.py`:

```python
"""
Merge a translation sidecar into a campaign's master.json.

Grafts `snippet_en` onto each agent_pain_hits[*] whose snippet was translated,
matched by (place_id, snippet_key). Provenance per outreach/CLAUDE.md rule 1;
atomic write. Idempotent — re-running re-applies the same English text.

Sidecar shape (produced by the translator subagent over the *_request.json):
    { "<place_id>": { "<snippet_key>": "<english text>" } }

Usage:
    python outreach/lib/cli/merge_translations.py \\
        --master  .../outputs/<date>/master.json \\
        --sidecar .../enrichment/translations/<date>.json \\
        --out     .../outputs/<date>/master.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.cli.translate import snippet_key

PROVENANCE_TAG = 'translator-subagent'


def merge(master: list[dict], sidecar: dict[str, dict]) -> dict:
    """Mutate `master` in place; return stats. Each translated snippet gets
    snippet_en + provenance on its hit."""
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    translated = 0
    leads_touched = 0
    for lead in master:
        pid = lead.get('place_id')
        by_key = sidecar.get(pid) if pid else None
        if not by_key:
            continue
        lead_hit = False
        for hits in (lead.get('agent_pain_hits') or {}).values():
            for hit in hits:
                key = snippet_key(hit.get('snippet') or '')
                english = by_key.get(key)
                if english:
                    hit['snippet_en'] = english
                    hit['snippet_en_source'] = PROVENANCE_TAG
                    hit['snippet_en_added_at'] = now
                    translated += 1
                    lead_hit = True
        if lead_hit:
            leads_touched += 1
    return {'snippets_translated': translated, 'leads_touched': leads_touched}


def write_atomic(path: Path, master: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(master, indent=2, ensure_ascii=False))
    tmp.replace(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Graft a translation sidecar into master.json.')
    parser.add_argument('--master', type=Path, required=True)
    parser.add_argument('--sidecar', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)

    if not args.master.exists():
        sys.stderr.write(f"error: master not found: {args.master}\n")
        return 2
    if not args.sidecar.exists():
        sys.stderr.write(f"error: sidecar not found: {args.sidecar}\n")
        return 2

    master = json.loads(args.master.read_text())
    sidecar = json.loads(args.sidecar.read_text())
    if not isinstance(master, list):
        sys.stderr.write("error: master must be a JSON array of leads\n")
        return 2
    if not isinstance(sidecar, dict):
        sys.stderr.write("error: sidecar must be a JSON object keyed by place_id\n")
        return 2

    stats = merge(master, sidecar)
    write_atomic(args.out, master)
    print(f"  snippets translated: {stats['snippets_translated']}", file=sys.stderr)
    print(f"  leads touched      : {stats['leads_touched']}", file=sys.stderr)
    print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python outreach/lib/cli/tests/test_merge_translations.py`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add outreach/lib/cli/merge_translations.py outreach/lib/cli/tests/test_merge_translations.py
git commit -m "feat(outreach): merge_translations grafts snippet_en onto agent_pain_hits"
```

---

## Task 7: Handoff — English pain quotes + `_original` sibling columns

**Files:**
- Modify: `outreach/lib/handoff/csv_builder.py`
- Test: `outreach/lib/handoff/tests/test_csv_builder.py`

- [ ] **Step 1: Write the failing test**

Add to `outreach/lib/handoff/tests/test_csv_builder.py` (new test methods in the existing class, and import `_build_row`/`FIELDNAMES` are already imported):

```python
    def test_pain_quote_prefers_english_keeps_original(self):
        lead = {
            'agent_pain_hits': {
                'frontline_communication': [{
                    'snippet': 'Заказывал доработку сайта',
                    'snippet_en': 'Ordered a website revision',
                    'rating': 1, 'reviewer': 'X',
                }]
            },
        }
        row = _build_row(lead, service_map={},
                         pain_weights={'frontline_communication': 5})
        self.assertEqual(row['pain_quote_1'], 'Ordered a website revision')
        self.assertEqual(row['pain_quote_1_original'], 'Заказывал доработку сайта')

    def test_pain_quote_english_source_has_empty_original(self):
        lead = {
            'agent_pain_hits': {
                'frontline_communication': [{
                    'snippet': 'The manager never replied', 'rating': 1, 'reviewer': 'X',
                }]
            },
        }
        row = _build_row(lead, service_map={},
                         pain_weights={'frontline_communication': 5})
        self.assertEqual(row['pain_quote_1'], 'The manager never replied')
        self.assertEqual(row['pain_quote_1_original'], '')

    def test_original_columns_in_fieldnames(self):
        self.assertIn('pain_quote_1_original', FIELDNAMES)
        self.assertIn('pain_quote_2_original', FIELDNAMES)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python outreach/lib/handoff/tests/test_csv_builder.py`
Expected: FAIL — `KeyError: 'pain_quote_1_original'` / assertion on FIELDNAMES.

- [ ] **Step 3: Carry `snippet_en` through `top_pain_with_quotes`**

In `csv_builder.py`, in `top_pain_with_quotes`, change the `quotes.append({...})` dict to include the English text (add the `snippet_en` line):

```python
            quotes.append({
                'category': cat,
                'rating': hit.get('rating'),
                'reviewer': hit.get('reviewer'),
                'snippet': snippet,
                'snippet_en': (hit.get('snippet_en') or '').strip(),
                'matched': hit.get('matched'),
            })
```

- [ ] **Step 4: Add the columns to `FIELDNAMES`**

In `FIELDNAMES`, replace the pain-quote line:

```python
    'top_pain_category', 'pain_breadth_count', 'pain_quote_1', 'pain_quote_2',
    'pain_quote_1_rating', 'pain_quote_2_rating',
```
with:
```python
    'top_pain_category', 'pain_breadth_count', 'pain_quote_1', 'pain_quote_2',
    'pain_quote_1_original', 'pain_quote_2_original',
    'pain_quote_1_rating', 'pain_quote_2_rating',
```

- [ ] **Step 5: Emit English-preferred quotes + originals in `_build_row`**

In `_build_row`, replace the two `pain_quote_1` / `pain_quote_2` lines:

```python
        'pain_quote_1': (q1 or {}).get('snippet', ''),
        'pain_quote_2': (q2 or {}).get('snippet', ''),
```
with:
```python
        'pain_quote_1': (q1 or {}).get('snippet_en') or (q1 or {}).get('snippet', ''),
        'pain_quote_2': (q2 or {}).get('snippet_en') or (q2 or {}).get('snippet', ''),
        'pain_quote_1_original': (q1 or {}).get('snippet', '') if (q1 or {}).get('snippet_en') else '',
        'pain_quote_2_original': (q2 or {}).get('snippet', '') if (q2 or {}).get('snippet_en') else '',
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python outreach/lib/handoff/tests/test_csv_builder.py`
Expected: PASS (existing + 3 new).

- [ ] **Step 7: Commit**

```bash
git add outreach/lib/handoff/csv_builder.py outreach/lib/handoff/tests/test_csv_builder.py
git commit -m "feat(outreach): handoff shows English pain quotes, keeps original in sibling column"
```

---

## Task 8: Handoff — `primary_contact` + `primary_contact_channel`

Surface the single best reachable contact and channel, in this order:
1. owner-lookup person (`owner_name` + `owner_linkedin`) — ICP-targeted decision-maker;
2. osint person (`poc_name` + `linkedin_url_poc`/`poc_email`);
3. highest-confidence crawled POC name + that POC's email/socials;
4. company-level fallback channel (`linkedin_url_company` or company LinkedIn social).

Channel preference within a contact: LinkedIn → personal email → other social.

**Files:**
- Modify: `outreach/lib/handoff/csv_builder.py`
- Test: `outreach/lib/handoff/tests/test_csv_builder.py`

- [ ] **Step 1: Write the failing test**

Add to `test_csv_builder.py` (and add `primary_contact` to the imports from `lib.handoff.csv_builder` at the top of the file):

```python
    def test_primary_contact_prefers_owner_linkedin(self):
        lead = {
            'owner_name': 'Olena K', 'owner_linkedin': 'https://linkedin.com/in/olenak',
            'poc_name': 'Ignored', 'linkedin_url_poc': 'https://linkedin.com/in/ignored',
        }
        name, channel = primary_contact(lead)
        self.assertEqual(name, 'Olena K')
        self.assertEqual(channel, 'https://linkedin.com/in/olenak')

    def test_primary_contact_falls_back_to_osint_poc(self):
        lead = {
            'poc_name': 'Dmytro H', 'poc_email': 'dmytro@firm.com',
        }
        name, channel = primary_contact(lead)
        self.assertEqual(name, 'Dmytro H')
        self.assertEqual(channel, 'dmytro@firm.com')

    def test_primary_contact_empty_when_nothing_reachable(self):
        name, channel = primary_contact({})
        self.assertEqual(name, '')
        self.assertEqual(channel, '')

    def test_primary_contact_in_fieldnames(self):
        self.assertIn('primary_contact', FIELDNAMES)
        self.assertIn('primary_contact_channel', FIELDNAMES)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python outreach/lib/handoff/tests/test_csv_builder.py`
Expected: FAIL — `ImportError: cannot import name 'primary_contact'`.

- [ ] **Step 3: Implement `primary_contact`**

In `csv_builder.py`, add this function (place it after `pocs_field`):

```python
def _best_kept_poc(l):
    """Highest-confidence non-invalid crawled POC dict, or None."""
    pocs = [
        p for p in (l.get('pocs') or [])
        if isinstance(p, dict) and not p.get('invalid') and p.get('name')
        and (p.get('confidence') is None or p.get('confidence') >= POC_MIN_CONFIDENCE)
    ]
    if not pocs:
        return None
    return max(pocs, key=lambda p: p.get('confidence') if p.get('confidence') is not None else 0.0)


def _first_social(l, needle):
    for s in (l.get('socials') or []) + (l.get('crawled_socials') or []):
        if needle in s.lower():
            return s
    return ''


def primary_contact(l):
    """Return (name, channel) for the single best reachable contact.

    Preference order for the person: owner-lookup → osint poc → crawled POC.
    Channel preference: LinkedIn → personal email → other social → company
    LinkedIn. Returns ('', '') when nothing reachable is known."""
    # 1. owner-lookup decision-maker (ICP-targeted)
    if l.get('owner_name'):
        channel = (
            l.get('owner_linkedin')
            or l.get('poc_email') or ''
        )
        return l['owner_name'], channel
    # 2. osint-discovered person
    if l.get('poc_name'):
        channel = (
            l.get('linkedin_url_poc')
            or l.get('poc_email') or ''
        )
        return l['poc_name'], channel
    # 3. highest-confidence crawled POC
    poc = _best_kept_poc(l)
    if poc:
        channel = (
            next((s for s in (poc.get('socials') or []) if 'linkedin' in s.lower()), '')
            or poc.get('email') or ''
            or (poc.get('socials') or [''])[0]
        )
        if not channel:
            channel = l.get('linkedin_url_company') or _first_social(l, 'linkedin.com')
        return poc['name'], channel
    # 4. no person — company-level channel only is not a "contact"
    return '', ''
```

- [ ] **Step 4: Wire it into `FIELDNAMES` and `_build_row`**

In `FIELDNAMES`, in the decision-maker group, change:

```python
    'owner_name', 'owner_title', 'owner_linkedin', 'additional_team', 'pocs',
```
to:
```python
    'owner_name', 'owner_title', 'owner_linkedin', 'additional_team', 'pocs',
    'primary_contact', 'primary_contact_channel',
```

In `_build_row`, immediately before the `row = {` literal, compute the tuple once:

```python
    pc_name, pc_channel = primary_contact(l)
```

Then, after the `'pocs': pocs_field(l),` line inside the dict, add:

```python
        'primary_contact': pc_name,
        'primary_contact_channel': pc_channel,
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python outreach/lib/handoff/tests/test_csv_builder.py`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add outreach/lib/handoff/csv_builder.py outreach/lib/handoff/tests/test_csv_builder.py
git commit -m "feat(outreach): handoff surfaces primary_contact + channel (ICP-ordered)"
```

---

## Task 9: Register the `translate` stage in the outreach runbook

**Files:**
- Modify: `.claude/skills/outreach/SKILL.md`

- [ ] **Step 1: Add `translate` to the stage list and pipeline order**

In `.claude/skills/outreach/SKILL.md`, in the "Args" stage enum, add `translate`:

```
  `analyze | classify | translate | enrich | validate | handoff | owner-lookup | osint-enrich`.
```

In "Standard pipeline order", insert `translate` after `classify` and before `validate`:

```
scrape → analyze → enrich → merge-crawl → classify → translate → validate → handoff
```

- [ ] **Step 2: Add a `## Stage: translate` section**

Insert after the `classify` section:

````markdown
## Stage: translate

`outreach <pipeline> translate`

Locale-gated translation of the pain quotes that surface in the handoff. No-op
for `en-*` campaigns. For non-English campaigns it sends only the non-English
snippets (script-detected) to a translator subagent, then grafts English back.

Steps:

1. `python outreach/lib/cli/translate.py <pipeline> [--master PATH] [--output-date <date>]`
   - Writes `enrichment/translations/<date>_request.json`:
     `{ "<place_id>": { "<snippet_key>": "<original>" } }`.
   - If the campaign locale is `en-*`, the request is empty — skip the rest.
2. Dispatch the `translator` subagent (Silverthread `ai-translator-private`
   `translator` skill rules: anti-fabrication; preserve numbers, currency,
   person/company names, URLs, identifiers; English must read natively) over
   the request sidecar in batches. The subagent writes
   `enrichment/translations/<date>.json` with the SAME keys mapped to English.
3. `python outreach/lib/cli/merge_translations.py --master <master> --sidecar enrichment/translations/<date>.json --out <master>`
   - Grafts `snippet_en` onto each `agent_pain_hits[*]` with provenance.

next: `outreach <pipeline> validate`
````

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/outreach/SKILL.md
git commit -m "docs(outreach): register translate stage in the runbook"
```

---

## Task 9.5: Pre-run verifications (cheap, do before the live run)

Two assumptions Task 10 relies on. Verify, don't trust.

- [ ] **Step 1: Tier-function parity**

The subset filter uses `tier` set by `lib.ranking.tier` (during `merge_classifications`); the CSV `tier` column uses `csv_builder.tier` (A≥60/B≥30/C≥15). If thresholds differ, "~430 A/B/C" and the delivered CSV tiers disagree.

```bash
cd /home/fassihhaider/Work/google-maps-scraper
python - <<'PY'
import sys; sys.path.insert(0,'outreach')
from lib.ranking import tier as rt
from lib.handoff.csv_builder import tier as ct
mismatch = [q for q in (10,14,15,16,29,30,31,59,60,61,100) if rt(q) != ct(q)]
print("ranking.tier vs csv_builder.tier mismatches at:", mismatch or "NONE (parity OK)")
PY
```
Expected: `NONE (parity OK)`. If there are mismatches, reconcile the thresholds (prefer making `csv_builder.tier` defer to `lib.ranking.tier`) and add a test before proceeding.

- [ ] **Step 2: No positional CSV consumer**

Inserting columns mid-`FIELDNAMES` is safe for `DictWriter`/`DictReader` (keyed by name) but would break any reader that indexes columns by position.

```bash
grep -rn "handoff.csv\|csv.reader\|\.split(','\|row\[[0-9]" outreach/lib outreach/campaigns/software_ua_v2 2>/dev/null | grep -iv test || echo "no positional CSV consumers found"
```
Inspect `outreach/lib/cli/push_leads.py` specifically — confirm it reads by column name (`DictReader`), not by index. If it indexes positionally, fix it to key by name before shipping the new columns.

---

## Task 10: Execution runbook — produce the `software_ua_v2` delivery

This task runs the pipeline on real data. It is operational, not code. The **pilot gate (Step 5) is a STOP-for-human-review** checkpoint. Use the latest dated `outputs/` folder produced by `analyze`.

- [ ] **Step 1: Build the initial master**

```bash
cd /home/fassihhaider/Work/google-maps-scraper
python outreach/lib/cli/analyze.py software_ua_v2
```
Note the printed `outputs/<date>/master.json` path; call it `$M` below.

- [ ] **Step 2: Merge the reused classification sidecar**

```bash
python outreach/lib/cli/merge_classifications.py \
  --master  "$M" \
  --sidecar outreach/campaigns/software_ua_v2/enrichment/pain_classifications/2026-05-22.json \
  --out     "$M"
```
Check the `orphan place_ids` stat is near-zero (same raw → same place_ids). A high count means the sidecar doesn't match this master — investigate before continuing.

- [ ] **Step 3: Build the tier A/B/C crawl queue (~430 leads)**

```bash
python - "$M" <<'PY'
import json, sys
from pathlib import Path
M = Path(sys.argv[1]); leads = json.loads(M.read_text())
sub = [l for l in leads if l.get('tier') in ('A','B','C')]
# dedupe by hostname for the crawl queue
from urllib.parse import urlparse
seen=set(); queue=[]
for l in sorted(sub, key=lambda x:-(x.get('quality_score') or 0)):
    host = urlparse((l.get('website') or l.get('web_site') or '')).netloc.lower()
    if not host or host in seen: continue
    seen.add(host); queue.append(l.get('website') or l.get('web_site'))
q = M.parent.parent.parent / 'enrichment' / 'crawl_queue.json'
q.write_text(json.dumps(queue, indent=2))
print(f"{len(sub)} A/B/C leads, {len(queue)} unique hostnames -> {q}")
PY
```
(If `enrich.py` expects a different queue shape, match it — see `outreach/lib/cli/enrich.py` `--queue` handling. Adjust the writer above to that shape before running enrich.)

- [ ] **Step 4: Merge the reused crawl (don't re-crawl)**

The crawl payload was copied in Task 0. Graft it; only crawl gaps if needed.

```bash
python outreach/lib/cli/merge_crawl_into_master.py software_ua_v2 --master "$M"
```
Optional — if many A/B/C leads have `crawl_attempted: False` (hostnames not in the reused crawl, e.g. churn), build a gap-only queue of just those hostnames and run `enrich.py --queue <gaps>` for them, then re-merge. Do **not** re-crawl the whole subset.

- [ ] **Step 5: PILOT GATE — deep-enrich ~20 leads, measure OWNER-LOOKUP yield, STOP for review**

Important framing: `osint-enrich` mostly *attaches a LinkedIn URL to a name you already have* (its `linkedin_url_poc` query is skipped when `no_poc_name_known`). The stage that actually *discovers* decision-makers for the many leads with no crawled POC is **owner-lookup** (manual web search). So the pilot's load-bearing metric is owner-lookup yield, not the aggregate.

Run owner-lookup + osint-enrich on the top ~20 A/B/C leads only (owner-lookup `--print-queue --limit 20`; for osint, process only the first 20 sidecar records). Then measure both, but gate on owner-lookup:

```bash
python - "$M" <<'PY'
import json, sys
from pathlib import Path
leads = json.loads(Path(sys.argv[1]).read_text())
sub = [l for l in leads if l.get('tier') in ('A','B','C')][:20]
owner_found  = sum(1 for l in sub if l.get('owner_name'))
owner_reach  = sum(1 for l in sub if l.get('owner_name') and l.get('owner_linkedin'))
any_reach    = sum(1 for l in sub if (l.get('owner_name') or l.get('poc_name'))
                   and (l.get('owner_linkedin') or l.get('linkedin_url_poc') or l.get('poc_email')))
n = max(len(sub), 1)
print(f"owner-lookup found a name : {owner_found}/{len(sub)} = {100*owner_found/n:.0f}%")
print(f"owner-lookup name+LinkedIn: {owner_reach}/{len(sub)} = {100*owner_reach/n:.0f}%  <-- GATE")
print(f"any reachable POC (incl osint/crawl): {any_reach}/{len(sub)} = {100*any_reach/n:.0f}%")
PY
```

**STOP.** Report all three numbers to the user. Proceed to Step 6 only if the owner-lookup name+LinkedIn yield is ≥ ~30% (the spec's go/no-go) or the user approves. If lower, pause and rethink scope — 430 manual owner-lookups is the biggest cost in the run, so a weak pilot should change the plan before spending it.

- [ ] **Step 6: Full deep-enrichment across the A/B/C subset**

On approval, run all three deep passes across the full subset: `owner-lookup` (print-queue → web-search → sidecar → `--apply`), `osint-enrich` (script → `osint-binder` subagent batches → `--apply-judgments` → `merge_osint_into_master.py`), and confirm the crawl POC pass from Step 4. Follow the `## Stage: owner-lookup` and `## Stage: osint-enrich` sections of `SKILL.md` exactly.

- [ ] **Step 7: Translate the pain quotes**

```bash
python outreach/lib/cli/translate.py software_ua_v2 --master "$M"
```
Dispatch the `translator` subagent over `enrichment/translations/<date>_request.json` (batches), writing `enrichment/translations/<date>.json`. Then:
```bash
python outreach/lib/cli/merge_translations.py \
  --master "$M" --sidecar outreach/campaigns/software_ua_v2/enrichment/translations/<date>.json --out "$M"
```

- [ ] **Step 8: Validate (scores POCs, flags emails/phones)**

```bash
python outreach/lib/cli/validate.py software_ua_v2 --master "$M"
```

- [ ] **Step 9: Build the handoff CSV**

```bash
python outreach/lib/cli/handoff.py software_ua_v2 --master "$M"
```

- [ ] **Step 10: Diff vs the old delivery and report**

```bash
python - <<'PY'
import json
from pathlib import Path
old = json.loads(Path('outreach/campaigns/software_ua/outputs/2026-05-22/master.json').read_text())
import glob, os
newest = sorted(glob.glob('outreach/campaigns/software_ua_v2/outputs/*/master.json'))[-1]
new = json.loads(Path(newest).read_text())
def reach(ls):
    return sum(1 for l in ls if (l.get('owner_name') or l.get('poc_name'))
               and (l.get('owner_linkedin') or l.get('linkedin_url_poc') or l.get('poc_email')))
print(f"OLD leads={len(old)} reachable_POC={reach(old)}")
print(f"NEW leads={len(new)} reachable_POC={reach(new)}  ({newest})")
PY
```
Report to the user: lead counts, tier mix, and **% of leads with a reachable POC** — the headline metric. Surface big shifts before declaring done.

---

## Self-Review

**Spec coverage:**
- P2 translation (English in handoff, original preserved) → Tasks 4–7, 10.7. ✓
- P1 reachable POCs (run skipped stages, primary_contact) → Tasks 8, 10.5–10.6. ✓
- Reusable locale-gated translate stage → Tasks 1, 4, 5, 6, 9. ✓
- ICP targeting in overrides → Tasks 2, 3. ✓
- Dropped POC tech-token denylist → intentionally no task (Context note). ✓
- New campaign dir, raw copied, classification reused → Task 0. ✓
- Pilot gate ~30% → Task 10.5. ✓

**Placeholder scan:** No TBD/TODO; every code step shows the code; commands have expected output. Step 10.3 flags the one thing to verify against `enrich.py`'s queue shape — that's an explicit verification instruction, not a placeholder.

**Type consistency:** `snippet_key` defined in Task 5 (`translate.py`) is imported by Tasks 6 (`merge_translations`) and used in tests; `primary_contact` returns `(name, channel)` consistently in Task 8 def, tests, and `_build_row`; `needs_translation(snippet, locale)` signature matches across Tasks 4 and 5; `select_for_translation(master, *, locale, pain_weights)` matches its test. `CampaignConfig.locale` (Task 1) is read by `translate.py` (Task 5). ✓

---

## Execution Handoff

Plan complete. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task with review between tasks.
2. **Inline Execution** — execute tasks in this session with checkpoints.

Tasks 1–9 are pure code/config (TDD, fully specified). Task 10 is the live data run with a human STOP at the pilot gate — it should be driven interactively, not autonomously.
