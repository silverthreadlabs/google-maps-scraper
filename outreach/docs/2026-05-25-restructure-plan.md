# Outreach Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose `outreach/pipelines/<vertical>_<location>/` into `verticals/`, `locations/`, `campaigns/`, and a unified `lib/` so vertical knobs, location data, and run instances each live in one place.

**Architecture:** A campaign is a triple (vertical template, location data, optional campaign overrides). A new `lib/campaign_config.py` loader merges the three at runtime into a single `CampaignConfig` object that existing CLI scripts consume. Per-city query files are regenerated from `verticals/<v>/query_templates.txt` × `locations/<loc>.yaml` via a new `lib/render_queries.py`. The `outreach/scripts/` directory collapses into `outreach/lib/cli/` so there is one home for shared code.

**Tech Stack:** Python 3.10+, `unittest` (existing pattern — tests are run as `python path/to/test_*.py`), PyYAML (new dep for location data), `git mv` for history-preserving moves.

**Decisions locked from spec:**
- Overrides format: **Python** (`overrides.py`) — reuses existing compiled-regex + `EnrichProfile` patterns.
- CLI arg name: **keep `<pipeline>` positional** — operators and runbooks already use it; the value just resolves to `campaigns/<name>/` in the new world.

---

## File Structure

### New files (created in Phase A)

| Path | Responsibility |
|---|---|
| `outreach/lib/campaign_config.py` | Merging loader. Reads `campaigns/<c>/campaign.yaml`, imports `verticals/<v>/config.py`, parses `locations/<l>.yaml`, optionally imports `campaigns/<c>/overrides.py`, returns a `CampaignConfig` dataclass. |
| `outreach/lib/campaign_config_tests.py` | Tests for the loader. (Tests live next to module per existing pattern — see `lib/test_url_normalize.py`.) |
| `outreach/lib/render_queries.py` | Renders `verticals/<v>/query_templates.txt` × `locations/<l>.yaml` → `campaigns/<c>/queries/<city>.txt`. Idempotent. |
| `outreach/lib/render_queries_tests.py` | Tests for the renderer. |
| `outreach/locations/sunbelt.yaml` | Cities: austin, phoenix, tampa. |
| `outreach/locations/ua.yaml` | Cities: kyiv, lviv, dnipro. UA mobile prefixes shared across cities. |
| `outreach/locations/dallas.yaml` | City: dallas (DFW area codes). |
| `outreach/locations/toronto.yaml` | City: toronto (416/647/437/905/289/365). |
| `outreach/verticals/dentist/config.py` | Pain weights, services, enrich profile, vertical-wide DSO regex, OSINT templates. |
| `outreach/verticals/dentist/query_templates.txt` | `dentist in {neighborhood} {city} {state}` etc. |
| `outreach/verticals/dentist/README.md` | Vertical fit notes (where vertical-level docstring content from the old `config.py` goes). |
| `outreach/verticals/software/config.py` | Same shape, software-tuned. |
| `outreach/verticals/software/query_templates.txt` | `software agency in {city}` etc. |
| `outreach/verticals/software/README.md` | |
| `outreach/verticals/cosmetic_surgery/config.py` | Same shape. |
| `outreach/verticals/cosmetic_surgery/query_templates.txt` | |
| `outreach/verticals/cosmetic_surgery/README.md` | |
| `outreach/verticals/retail/config.py` | Same shape. |
| `outreach/verticals/retail/query_templates.txt` | |
| `outreach/verticals/retail/README.md` | |

### Files moved (Phases B–C)

| From | To | History |
|---|---|---|
| `outreach/scripts/_common.py` | `outreach/lib/cli/_common.py` | `git mv` |
| `outreach/scripts/analyze.py` | `outreach/lib/cli/analyze.py` | `git mv` |
| `outreach/scripts/enrich.py` | `outreach/lib/cli/enrich.py` | `git mv` |
| `outreach/scripts/handoff.py` | `outreach/lib/cli/handoff.py` | `git mv` |
| `outreach/scripts/validate.py` | `outreach/lib/cli/validate.py` | `git mv` |
| `outreach/scripts/merge_classifications.py` | `outreach/lib/cli/merge_classifications.py` | `git mv` |
| `outreach/scripts/merge_crawl_into_master.py` | `outreach/lib/cli/merge_crawl_into_master.py` | `git mv` |
| `outreach/scripts/merge_osint_into_master.py` | `outreach/lib/cli/merge_osint_into_master.py` | `git mv` |
| `outreach/scripts/osint_enrich.py` | `outreach/lib/cli/osint_enrich.py` | `git mv` |
| `outreach/scripts/owner_lookup.py` | `outreach/lib/cli/owner_lookup.py` | `git mv` |
| `outreach/scripts/push_campaign.py` | `outreach/lib/cli/push_campaign.py` | `git mv` |
| `outreach/scripts/push_leads.py` | `outreach/lib/cli/push_leads.py` | `git mv` |
| `outreach/scripts/tests/*` (9 files) | `outreach/lib/cli/tests/*` | `git mv` |
| `outreach/pipelines/dental_sunbelt/` | `outreach/campaigns/dentist_sunbelt/` | `git mv` |
| `outreach/pipelines/software_ua/` | `outreach/campaigns/software_ua/` | `git mv` |
| `outreach/pipelines/cosmetic_surgeons_dallas/` | `outreach/campaigns/cosmetic_surgeons_dallas/` | `git mv` |
| `outreach/pipelines/retail_toronto/` | `outreach/campaigns/retail_toronto/` | `git mv` |
| `outreach/pipelines/software_ua/build_classify_batches.py` | `outreach/campaigns/software_ua/scripts/build_classify_batches.py` | already moved by parent git mv |
| `outreach/pipelines/software_ua/build_enrich_queue.py` | `outreach/campaigns/software_ua/scripts/build_enrich_queue.py` | ditto |
| `outreach/pipelines/software_ua/merge_batches.py` | `outreach/campaigns/software_ua/scripts/merge_batches.py` | ditto |
| `outreach/pipelines/software_ua/retry_via_curl.py` | `outreach/campaigns/software_ua/scripts/retry_via_curl.py` | ditto |

### Files deleted (Phase D)

| Path | Why |
|---|---|
| `outreach/pipelines/` (empty after C) | Replaced by `campaigns/` |
| `outreach/scripts/` (empty after B) | Replaced by `lib/cli/` |
| `outreach/lib/scrapers/` (empty today) | Unused stub |
| `outreach/pipelines/insurance_sf/` | No `config.py`, no raw, no outputs — dead campaign |
| Per-campaign `config.py` files (all 4) | Knobs migrated to `verticals/` + `locations/` + `overrides.py` |

### Files modified (Phase D)

| Path | What changes |
|---|---|
| `outreach/CLAUDE.md` | Rule 2 paths, "add a vertical" instructions |
| `outreach/README.md` | Daily-driver commands, directory map |
| `outreach/TODO.md` | Path references |
| `outreach/requirements.txt` | Add `PyYAML>=6.0` |
| `.claude/skills/outreach/SKILL.md` | Path examples, test-find command |

---

## Phase A — Build new layout alongside old

No deletions in this phase. Old `pipelines/` and `scripts/` still work; new directories appear as scaffolding.

---

### Task A0: Add PyYAML to requirements

**Files:**
- Modify: `outreach/requirements.txt`

- [ ] **Step A0.1: Append PyYAML to requirements**

Edit `outreach/requirements.txt` to add a third line:

```
python-whois>=0.9.0
beautifulsoup4>=4.12
PyYAML>=6.0
```

- [ ] **Step A0.2: Install the dependency locally**

Run:

```bash
pip install 'PyYAML>=6.0'
```

Expected: `Successfully installed PyYAML-...` (or "Requirement already satisfied").

- [ ] **Step A0.3: Verify import works**

Run:

```bash
python -c "import yaml; print(yaml.__version__)"
```

Expected: a version string `>=6.0`.

- [ ] **Step A0.4: Commit**

```bash
git add outreach/requirements.txt
git commit -m "chore(outreach): add PyYAML for location config loader"
```

---

### Task A1: Create `lib/campaign_config.py` skeleton

**Files:**
- Create: `outreach/lib/campaign_config.py`
- Create: `outreach/lib/campaign_config_tests.py`

This task creates the empty module and a first failing test. The dataclass and loader are filled in by subsequent tasks.

- [ ] **Step A1.1: Write the failing test for `CampaignConfig` import**

Create `outreach/lib/campaign_config_tests.py`:

```python
"""Tests for outreach/lib/campaign_config.py."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestImports(unittest.TestCase):
    def test_can_import_campaign_config_dataclass(self):
        from lib.campaign_config import CampaignConfig
        self.assertTrue(hasattr(CampaignConfig, '__dataclass_fields__'))

    def test_can_import_load_function(self):
        from lib.campaign_config import load_campaign
        self.assertTrue(callable(load_campaign))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step A1.2: Run the test, confirm it fails**

Run:

```bash
python outreach/lib/campaign_config_tests.py
```

Expected: `ModuleNotFoundError: No module named 'lib.campaign_config'` or similar.

- [ ] **Step A1.3: Create the minimal module to make the test pass**

Create `outreach/lib/campaign_config.py`:

```python
"""Campaign config loader.

A campaign config is the merge of three sources:

    verticals/<vertical>/config.py    — vertical template
    locations/<location>.yaml         — location data
    campaigns/<campaign>/overrides.py — optional campaign-specific tweaks

Plus the per-campaign descriptor `campaigns/<campaign>/campaign.yaml`,
which names the vertical + location to load.

The merged result is a `CampaignConfig` dataclass that CLI scripts in
`lib/cli/` consume in place of the legacy `pipelines/<name>/config.py`
module.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

OUTREACH_ROOT = Path(__file__).resolve().parent.parent

if str(OUTREACH_ROOT) not in sys.path:
    sys.path.insert(0, str(OUTREACH_ROOT))


@dataclass
class CampaignConfig:
    """Merged config for a single campaign run.

    All fields below match the legacy `pipelines/<name>/config.py`
    public surface so CLI scripts can swap import sources without
    field-by-field rewiring.
    """

    # Identity
    slug: str
    vertical: str
    location: str

    # Pain ranking (vertical default, optionally overridden by campaign)
    pain_weights: dict[str, int] = field(default_factory=dict)
    service_map: dict[str, tuple[str, str]] = field(default_factory=dict)

    # Chain detection (vertical + campaign extras merged)
    dso_title_regex: re.Pattern[str] = field(default=re.compile(r'^$'))
    dso_email_domains: set[str] = field(default_factory=set)
    geographic_prefixes: set[str] = field(default_factory=set)

    # Region / metro
    metros: list[str] = field(default_factory=list)
    metro_area_codes: dict[str, set[str]] = field(default_factory=dict)

    # Enrichment / validation
    enrich_profile: Any = None
    vendor_domains_extra: frozenset[str] = field(default_factory=frozenset)
    independent_filters: dict[str, Any] = field(default_factory=dict)

    # OSINT
    osint_enabled: bool = False
    osint_sources: list[str] = field(default_factory=list)
    osint_fields_desired: list[str] = field(default_factory=list)
    osint_confidence_threshold: float = 0.85
    osint_handoff_fields: list[str] = field(default_factory=list)
    osint_serp_queries: dict[str, str] = field(default_factory=dict)
    osint_deep_crawl_paths: list[str] = field(default_factory=list)
    osint_industry_terms: list[str] = field(default_factory=list)


def load_campaign(campaign_slug: str) -> CampaignConfig:
    """Load + merge the three config sources for `campaign_slug`.

    Caller passes the slug (directory name under campaigns/), e.g.
    'dentist_sunbelt'. Returns a fully-merged CampaignConfig.
    """
    raise NotImplementedError('filled in by subsequent tasks')
```

- [ ] **Step A1.4: Run the test, confirm it passes**

Run:

```bash
python outreach/lib/campaign_config_tests.py
```

Expected: `OK` with 2 tests run.

- [ ] **Step A1.5: Commit**

```bash
git add outreach/lib/campaign_config.py outreach/lib/campaign_config_tests.py
git commit -m "feat(outreach): scaffold campaign_config loader skeleton"
```

---

### Task A2: Parse `campaign.yaml`

Adds the first piece of `load_campaign`: reading the campaign descriptor.

**Files:**
- Modify: `outreach/lib/campaign_config.py`
- Modify: `outreach/lib/campaign_config_tests.py`

- [ ] **Step A2.1: Write failing tests for `campaign.yaml` parsing**

Append to `outreach/lib/campaign_config_tests.py` (before the `if __name__` block):

```python
class TestCampaignYamlParsing(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'campaigns' / 'dentist_sunbelt').mkdir(parents=True)
        (self.root / 'campaigns' / 'dentist_sunbelt' / 'campaign.yaml').write_text(
            "vertical: dentist\n"
            "location: sunbelt\n"
            "slug: dentist_sunbelt\n"
            "display_name: Dental Sunbelt\n"
        )

    def test_reads_vertical_location_slug(self):
        from lib.campaign_config import _read_campaign_yaml
        meta = _read_campaign_yaml(
            self.root / 'campaigns' / 'dentist_sunbelt' / 'campaign.yaml'
        )
        self.assertEqual(meta['vertical'], 'dentist')
        self.assertEqual(meta['location'], 'sunbelt')
        self.assertEqual(meta['slug'], 'dentist_sunbelt')

    def test_missing_file_raises_filenotfound(self):
        from lib.campaign_config import _read_campaign_yaml
        with self.assertRaises(FileNotFoundError):
            _read_campaign_yaml(self.root / 'campaigns' / 'nonexistent.yaml')

    def test_missing_required_key_raises_valueerror(self):
        (self.root / 'campaigns' / 'broken').mkdir()
        (self.root / 'campaigns' / 'broken' / 'campaign.yaml').write_text(
            "vertical: dentist\n"  # no location, no slug
        )
        from lib.campaign_config import _read_campaign_yaml
        with self.assertRaises(ValueError) as cm:
            _read_campaign_yaml(self.root / 'campaigns' / 'broken' / 'campaign.yaml')
        self.assertIn('location', str(cm.exception))
```

- [ ] **Step A2.2: Run tests, confirm new ones fail**

Run:

```bash
python outreach/lib/campaign_config_tests.py
```

Expected: 3 failures with `ImportError: cannot import name '_read_campaign_yaml'`.

- [ ] **Step A2.3: Implement `_read_campaign_yaml`**

Edit `outreach/lib/campaign_config.py`. Add at the top, after the existing imports:

```python
import yaml
```

Then add the function above `load_campaign`:

```python
_REQUIRED_CAMPAIGN_KEYS = ('vertical', 'location', 'slug')


def _read_campaign_yaml(path: Path) -> dict:
    """Read campaigns/<c>/campaign.yaml; validate required keys."""
    if not path.exists():
        raise FileNotFoundError(f'campaign.yaml not found: {path}')
    data = yaml.safe_load(path.read_text()) or {}
    missing = [k for k in _REQUIRED_CAMPAIGN_KEYS if k not in data]
    if missing:
        raise ValueError(
            f'{path} missing required key(s): {", ".join(missing)}'
        )
    return data
```

- [ ] **Step A2.4: Run tests, confirm pass**

Run:

```bash
python outreach/lib/campaign_config_tests.py
```

Expected: `OK` with 5 tests run.

- [ ] **Step A2.5: Commit**

```bash
git add outreach/lib/campaign_config.py outreach/lib/campaign_config_tests.py
git commit -m "feat(outreach): parse campaign.yaml descriptors"
```

---

### Task A3: Parse `locations/<loc>.yaml`

**Files:**
- Modify: `outreach/lib/campaign_config.py`
- Modify: `outreach/lib/campaign_config_tests.py`

- [ ] **Step A3.1: Write failing tests for location YAML parsing**

Append to `outreach/lib/campaign_config_tests.py`:

```python
class TestLocationYamlParsing(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'locations').mkdir()
        (self.root / 'locations' / 'sunbelt.yaml').write_text(
            "country: US\n"
            "locale: en-US\n"
            "cities:\n"
            "  - name: austin\n"
            "    state: TX\n"
            "    metro_area_codes: ['512', '737']\n"
            "    geographic_prefixes:\n"
            "      - south austin\n"
            "      - round rock\n"
            "    neighborhoods:\n"
            "      - Downtown\n"
            "      - South Austin\n"
            "  - name: phoenix\n"
            "    state: AZ\n"
            "    metro_area_codes: ['480', '602']\n"
            "    geographic_prefixes:\n"
            "      - chandler\n"
            "    neighborhoods:\n"
            "      - Downtown Phoenix\n"
        )

    def test_extracts_metros_in_order(self):
        from lib.campaign_config import _read_location_yaml
        loc = _read_location_yaml(self.root / 'locations' / 'sunbelt.yaml')
        self.assertEqual(loc['metros'], ['austin', 'phoenix'])

    def test_extracts_metro_area_codes_as_sets(self):
        from lib.campaign_config import _read_location_yaml
        loc = _read_location_yaml(self.root / 'locations' / 'sunbelt.yaml')
        self.assertEqual(loc['metro_area_codes']['austin'], {'512', '737'})
        self.assertEqual(loc['metro_area_codes']['phoenix'], {'480', '602'})

    def test_unions_geographic_prefixes_across_cities(self):
        from lib.campaign_config import _read_location_yaml
        loc = _read_location_yaml(self.root / 'locations' / 'sunbelt.yaml')
        self.assertEqual(
            loc['geographic_prefixes'],
            {'south austin', 'round rock', 'chandler'},
        )

    def test_keeps_per_city_neighborhoods(self):
        from lib.campaign_config import _read_location_yaml
        loc = _read_location_yaml(self.root / 'locations' / 'sunbelt.yaml')
        self.assertEqual(
            loc['neighborhoods']['austin'],
            ['Downtown', 'South Austin'],
        )
        self.assertEqual(
            loc['neighborhoods']['phoenix'],
            ['Downtown Phoenix'],
        )
```

- [ ] **Step A3.2: Run tests, confirm failure**

```bash
python outreach/lib/campaign_config_tests.py
```

Expected: `ImportError: cannot import name '_read_location_yaml'`.

- [ ] **Step A3.3: Implement `_read_location_yaml`**

Add to `outreach/lib/campaign_config.py`, above `load_campaign`:

```python
def _read_location_yaml(path: Path) -> dict:
    """Read locations/<loc>.yaml; return a flattened dict.

    Returns:
        metros: list[str]                — city names in declared order
        metro_area_codes: dict[str, set[str]]
        geographic_prefixes: set[str]    — UNION across all cities
        neighborhoods: dict[str, list[str]]
        country: str
        locale: str
    """
    if not path.exists():
        raise FileNotFoundError(f'location yaml not found: {path}')
    data = yaml.safe_load(path.read_text()) or {}
    cities = data.get('cities') or []
    metros: list[str] = []
    area_codes: dict[str, set[str]] = {}
    prefixes: set[str] = set()
    neighborhoods: dict[str, list[str]] = {}
    for city in cities:
        name = city['name']
        metros.append(name)
        area_codes[name] = set(str(c) for c in (city.get('metro_area_codes') or []))
        prefixes.update(city.get('geographic_prefixes') or [])
        neighborhoods[name] = list(city.get('neighborhoods') or [])
    return {
        'metros': metros,
        'metro_area_codes': area_codes,
        'geographic_prefixes': prefixes,
        'neighborhoods': neighborhoods,
        'country': data.get('country', ''),
        'locale': data.get('locale', ''),
    }
```

- [ ] **Step A3.4: Run tests, confirm pass**

```bash
python outreach/lib/campaign_config_tests.py
```

Expected: `OK` with 9 tests run.

- [ ] **Step A3.5: Commit**

```bash
git add outreach/lib/campaign_config.py outreach/lib/campaign_config_tests.py
git commit -m "feat(outreach): parse locations/<loc>.yaml"
```

---

### Task A4: Import vertical config + optional campaign overrides

**Files:**
- Modify: `outreach/lib/campaign_config.py`
- Modify: `outreach/lib/campaign_config_tests.py`

- [ ] **Step A4.1: Write failing tests for module import helpers**

Append to `outreach/lib/campaign_config_tests.py`:

```python
class TestPythonModuleLoading(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'verticals' / 'dentist').mkdir(parents=True)
        (self.root / 'verticals' / 'dentist' / 'config.py').write_text(
            "PAIN_WEIGHTS = {'calls_unanswered': 5}\n"
            "SERVICE_MAP = {'calls_unanswered': ('Voice AI', 'silverthreadlabs.com/voice')}\n"
            "DSO_TITLE_REGEX = None  # placeholder\n"
            "DSO_EMAIL_DOMAINS = {'aspendental.com'}\n"
            "GEOGRAPHIC_PREFIXES_GENERIC = {'family dental'}\n"
            "VENDOR_DOMAINS_EXTRA = frozenset({'gargle.com'})\n"
            "OSINT_ENABLED = True\n"
        )

    def test_load_vertical_module_returns_module(self):
        from lib.campaign_config import _load_python_module
        mod = _load_python_module(
            self.root / 'verticals' / 'dentist' / 'config.py',
            module_name='outreach_vertical_dentist',
        )
        self.assertEqual(mod.PAIN_WEIGHTS, {'calls_unanswered': 5})

    def test_load_overrides_returns_none_when_file_missing(self):
        from lib.campaign_config import _load_python_module_optional
        mod = _load_python_module_optional(
            self.root / 'campaigns' / 'fake' / 'overrides.py',
            module_name='outreach_overrides_fake',
        )
        self.assertIsNone(mod)

    def test_load_overrides_returns_module_when_present(self):
        (self.root / 'campaigns' / 'with_overrides').mkdir(parents=True)
        (self.root / 'campaigns' / 'with_overrides' / 'overrides.py').write_text(
            "PAIN_WEIGHTS = {'calls_unanswered': 99}\n"
        )
        from lib.campaign_config import _load_python_module_optional
        mod = _load_python_module_optional(
            self.root / 'campaigns' / 'with_overrides' / 'overrides.py',
            module_name='outreach_overrides_with_overrides',
        )
        self.assertIsNotNone(mod)
        self.assertEqual(mod.PAIN_WEIGHTS, {'calls_unanswered': 99})
```

- [ ] **Step A4.2: Run tests, confirm failure**

```bash
python outreach/lib/campaign_config_tests.py
```

Expected: `ImportError` on the new helpers.

- [ ] **Step A4.3: Implement the helpers**

Add at the top of `outreach/lib/campaign_config.py` (after existing imports):

```python
import importlib.util
```

Then add above `load_campaign`:

```python
def _load_python_module(path: Path, *, module_name: str) -> ModuleType:
    """Import a .py file at `path` as a fresh module named `module_name`.

    Unique `module_name` prevents collisions when multiple verticals or
    overrides are loaded in the same process (e.g. during the equivalence
    test).
    """
    if not path.exists():
        raise FileNotFoundError(f'python module not found: {path}')
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f'cannot build spec for {path}')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_python_module_optional(path: Path, *, module_name: str) -> ModuleType | None:
    """Same as _load_python_module but returns None if path doesn't exist."""
    if not path.exists():
        return None
    return _load_python_module(path, module_name=module_name)
```

- [ ] **Step A4.4: Run tests, confirm pass**

```bash
python outreach/lib/campaign_config_tests.py
```

Expected: `OK` with 12 tests run.

- [ ] **Step A4.5: Commit**

```bash
git add outreach/lib/campaign_config.py outreach/lib/campaign_config_tests.py
git commit -m "feat(outreach): add python module loaders for verticals + overrides"
```

---

### Task A5: Merge regex / set / dict primitives

**Files:**
- Modify: `outreach/lib/campaign_config.py`
- Modify: `outreach/lib/campaign_config_tests.py`

This task introduces the three primitives that combine vertical + campaign data: `_concat_regex`, `_union_sets`, and `_overlay_dict`.

- [ ] **Step A5.1: Write failing tests for merge primitives**

Append to `outreach/lib/campaign_config_tests.py`:

```python
class TestMergePrimitives(unittest.TestCase):
    def test_concat_regex_alternation(self):
        from lib.campaign_config import _concat_regex
        a = re.compile(r'\b(Aspen Dental|Heartland)\b', re.I)
        b = re.compile(r'\b(Coast Dental)\b', re.I)
        merged = _concat_regex(a, b)
        self.assertIsNotNone(merged.search('aspen dental'))
        self.assertIsNotNone(merged.search('coast dental'))
        self.assertIsNone(merged.search('mom & pop dentistry'))

    def test_concat_regex_none_extra_returns_base(self):
        from lib.campaign_config import _concat_regex
        a = re.compile(r'\bAspen Dental\b', re.I)
        merged = _concat_regex(a, None)
        self.assertIs(merged, a)

    def test_concat_regex_none_base_returns_extra(self):
        from lib.campaign_config import _concat_regex
        b = re.compile(r'\bCoast Dental\b', re.I)
        merged = _concat_regex(None, b)
        self.assertIs(merged, b)

    def test_union_sets(self):
        from lib.campaign_config import _union_sets
        self.assertEqual(_union_sets({'a', 'b'}, {'b', 'c'}), {'a', 'b', 'c'})
        self.assertEqual(_union_sets({'a'}, None), {'a'})
        self.assertEqual(_union_sets(None, {'a'}), {'a'})
        self.assertEqual(_union_sets(None, None), set())

    def test_overlay_dict_replaces_when_present(self):
        from lib.campaign_config import _overlay_dict
        base = {'a': 1, 'b': 2}
        overlay = {'b': 99, 'c': 3}
        self.assertEqual(_overlay_dict(base, overlay), {'a': 1, 'b': 99, 'c': 3})

    def test_overlay_dict_returns_base_when_overlay_none(self):
        from lib.campaign_config import _overlay_dict
        base = {'a': 1}
        result = _overlay_dict(base, None)
        self.assertEqual(result, {'a': 1})
        self.assertIsNot(result, base)  # must return a copy
```

- [ ] **Step A5.2: Run tests, confirm failure**

```bash
python outreach/lib/campaign_config_tests.py
```

Expected: import errors on the new helpers.

- [ ] **Step A5.3: Implement merge primitives**

Add to `outreach/lib/campaign_config.py` above `load_campaign`:

```python
def _concat_regex(
    base: re.Pattern[str] | None,
    extra: re.Pattern[str] | None,
) -> re.Pattern[str]:
    """Concatenate two regexes with alternation.

    Both patterns are expected to be anchored at word boundaries; the
    result preserves the LH side's flags. Returns one of the inputs
    unchanged when the other is None.
    """
    if base is None and extra is None:
        return re.compile(r'(?!)')  # never matches
    if extra is None:
        return base  # type: ignore[return-value]
    if base is None:
        return extra
    return re.compile(
        f'(?:{base.pattern})|(?:{extra.pattern})',
        base.flags,
    )


def _union_sets(a: set | None, b: set | None) -> set:
    """Return a ∪ b, treating None as empty. Always returns a new set."""
    out: set = set()
    if a:
        out.update(a)
    if b:
        out.update(b)
    return out


def _overlay_dict(base: dict, overlay: dict | None) -> dict:
    """Return a copy of `base` with `overlay` values merged on top.

    Used for PAIN_WEIGHTS and SERVICE_MAP — campaign override completely
    replaces vertical default per key.
    """
    out = dict(base)
    if overlay:
        out.update(overlay)
    return out
```

- [ ] **Step A5.4: Run tests, confirm pass**

```bash
python outreach/lib/campaign_config_tests.py
```

Expected: `OK` with 18 tests run.

- [ ] **Step A5.5: Commit**

```bash
git add outreach/lib/campaign_config.py outreach/lib/campaign_config_tests.py
git commit -m "feat(outreach): add regex/set/dict merge primitives"
```

---

### Task A6: Wire `load_campaign` end-to-end

**Files:**
- Modify: `outreach/lib/campaign_config.py`
- Modify: `outreach/lib/campaign_config_tests.py`

- [ ] **Step A6.1: Write failing end-to-end test**

Append to `outreach/lib/campaign_config_tests.py`:

```python
class TestLoadCampaignEndToEnd(unittest.TestCase):
    """Build a fake outreach root with one vertical + location + campaign,
    point OUTREACH_ROOT at it, call load_campaign, assert merged shape."""

    def setUp(self):
        import tempfile
        from unittest.mock import patch
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

        (self.root / 'verticals' / 'dentist').mkdir(parents=True)
        (self.root / 'verticals' / 'dentist' / 'config.py').write_text(
            "import re\n"
            "PAIN_WEIGHTS = {'calls_unanswered': 5, 'booking_friction': 4}\n"
            "SERVICE_MAP = {\n"
            "  'calls_unanswered': ('Voice AI', 'silverthreadlabs.com/voice'),\n"
            "  'booking_friction': ('Booking', 'silverthreadlabs.com/booking'),\n"
            "}\n"
            "DSO_TITLE_REGEX = re.compile(r'\\\\b(Aspen Dental|Heartland)\\\\b', re.I)\n"
            "DSO_EMAIL_DOMAINS = {'aspendental.com'}\n"
            "GEOGRAPHIC_PREFIXES_GENERIC = {'family dental'}\n"
            "ENRICH_PROFILE = 'sentinel-enrich-profile'\n"
            "VENDOR_DOMAINS_EXTRA = frozenset({'gargle.com'})\n"
            "INDEPENDENT_FILTERS = {'max_rating_exclusive': 5.0}\n"
            "OSINT_ENABLED = True\n"
            "OSINT_SOURCES = ['whois', 'serp']\n"
            "OSINT_FIELDS_DESIRED = ['poc_name']\n"
            "OSINT_CONFIDENCE_THRESHOLD = 0.85\n"
            "OSINT_HANDOFF_FIELDS = ['poc_name']\n"
            "OSINT_SERP_QUERIES = {'poc_name': 'site:linkedin.com {city}'}\n"
            "OSINT_DEEP_CRAWL_PATHS = ['/about']\n"
            "OSINT_INDUSTRY_TERMS = ['dentist']\n"
        )

        (self.root / 'locations').mkdir()
        (self.root / 'locations' / 'sunbelt.yaml').write_text(
            "country: US\n"
            "locale: en-US\n"
            "cities:\n"
            "  - name: austin\n"
            "    state: TX\n"
            "    metro_area_codes: ['512']\n"
            "    geographic_prefixes: ['round rock']\n"
            "    neighborhoods: ['Downtown']\n"
        )

        (self.root / 'campaigns' / 'dentist_sunbelt').mkdir(parents=True)
        (self.root / 'campaigns' / 'dentist_sunbelt' / 'campaign.yaml').write_text(
            "vertical: dentist\n"
            "location: sunbelt\n"
            "slug: dentist_sunbelt\n"
            "display_name: Dental Sunbelt\n"
        )

        self.patch = patch('lib.campaign_config.OUTREACH_ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_load_returns_campaign_config_with_identity(self):
        from lib.campaign_config import load_campaign
        cfg = load_campaign('dentist_sunbelt')
        self.assertEqual(cfg.slug, 'dentist_sunbelt')
        self.assertEqual(cfg.vertical, 'dentist')
        self.assertEqual(cfg.location, 'sunbelt')

    def test_load_propagates_pain_weights_from_vertical(self):
        from lib.campaign_config import load_campaign
        cfg = load_campaign('dentist_sunbelt')
        self.assertEqual(cfg.pain_weights['calls_unanswered'], 5)
        self.assertEqual(cfg.pain_weights['booking_friction'], 4)

    def test_load_unions_geographic_prefixes_from_vertical_and_location(self):
        from lib.campaign_config import load_campaign
        cfg = load_campaign('dentist_sunbelt')
        self.assertEqual(cfg.geographic_prefixes, {'family dental', 'round rock'})

    def test_load_metros_come_from_location(self):
        from lib.campaign_config import load_campaign
        cfg = load_campaign('dentist_sunbelt')
        self.assertEqual(cfg.metros, ['austin'])
        self.assertEqual(cfg.metro_area_codes['austin'], {'512'})

    def test_load_carries_enrich_profile_and_osint(self):
        from lib.campaign_config import load_campaign
        cfg = load_campaign('dentist_sunbelt')
        self.assertEqual(cfg.enrich_profile, 'sentinel-enrich-profile')
        self.assertTrue(cfg.osint_enabled)
        self.assertEqual(cfg.osint_industry_terms, ['dentist'])

    def test_load_applies_campaign_overrides_for_pain_weights(self):
        (self.root / 'campaigns' / 'dentist_sunbelt' / 'overrides.py').write_text(
            "PAIN_WEIGHTS = {'calls_unanswered': 99}\n"
        )
        from lib.campaign_config import load_campaign
        cfg = load_campaign('dentist_sunbelt')
        self.assertEqual(cfg.pain_weights['calls_unanswered'], 99)
        self.assertEqual(cfg.pain_weights['booking_friction'], 4)

    def test_load_applies_campaign_dso_regex_extra(self):
        import re
        (self.root / 'campaigns' / 'dentist_sunbelt' / 'overrides.py').write_text(
            "import re\n"
            "DSO_TITLE_REGEX_EXTRA = re.compile(r'\\\\bCoast Dental\\\\b', re.I)\n"
        )
        from lib.campaign_config import load_campaign
        cfg = load_campaign('dentist_sunbelt')
        self.assertIsNotNone(cfg.dso_title_regex.search('Coast Dental of Tampa'))
        self.assertIsNotNone(cfg.dso_title_regex.search('Aspen Dental'))

    def test_load_missing_campaign_raises(self):
        from lib.campaign_config import load_campaign
        with self.assertRaises(FileNotFoundError):
            load_campaign('does_not_exist')
```

- [ ] **Step A6.2: Run tests, confirm failure**

```bash
python outreach/lib/campaign_config_tests.py
```

Expected: `NotImplementedError` raised by the placeholder.

- [ ] **Step A6.3: Implement `load_campaign`**

Replace the `load_campaign` body in `outreach/lib/campaign_config.py`:

```python
def load_campaign(campaign_slug: str) -> CampaignConfig:
    """Load + merge the three config sources for `campaign_slug`."""
    campaign_dir = OUTREACH_ROOT / 'campaigns' / campaign_slug
    if not campaign_dir.is_dir():
        raise FileNotFoundError(f'campaign directory not found: {campaign_dir}')

    meta = _read_campaign_yaml(campaign_dir / 'campaign.yaml')
    vertical_name = meta['vertical']
    location_name = meta['location']

    vertical_mod = _load_python_module(
        OUTREACH_ROOT / 'verticals' / vertical_name / 'config.py',
        module_name=f'outreach_vertical_{vertical_name}',
    )

    location = _read_location_yaml(
        OUTREACH_ROOT / 'locations' / f'{location_name}.yaml',
    )

    overrides = _load_python_module_optional(
        campaign_dir / 'overrides.py',
        module_name=f'outreach_overrides_{campaign_slug}',
    )

    return _merge(meta, vertical_mod, location, overrides)


def _merge(
    meta: dict,
    vertical: ModuleType,
    location: dict,
    overrides: ModuleType | None,
) -> CampaignConfig:
    """Combine the three sources into a single CampaignConfig."""
    o = overrides

    return CampaignConfig(
        slug=meta['slug'],
        vertical=meta['vertical'],
        location=meta['location'],

        pain_weights=_overlay_dict(
            getattr(vertical, 'PAIN_WEIGHTS', {}),
            getattr(o, 'PAIN_WEIGHTS', None) if o else None,
        ),
        service_map=_overlay_dict(
            getattr(vertical, 'SERVICE_MAP', {}),
            getattr(o, 'SERVICE_MAP', None) if o else None,
        ),

        dso_title_regex=_concat_regex(
            getattr(vertical, 'DSO_TITLE_REGEX', None),
            getattr(o, 'DSO_TITLE_REGEX_EXTRA', None) if o else None,
        ),
        dso_email_domains=_union_sets(
            getattr(vertical, 'DSO_EMAIL_DOMAINS', set()),
            getattr(o, 'DSO_EMAIL_DOMAINS_EXTRA', None) if o else None,
        ),
        geographic_prefixes=_union_sets(
            _union_sets(
                getattr(vertical, 'GEOGRAPHIC_PREFIXES_GENERIC', set()),
                location.get('geographic_prefixes'),
            ),
            getattr(o, 'GEOGRAPHIC_PREFIXES_EXTRA', None) if o else None,
        ),

        metros=list(location.get('metros') or []),
        metro_area_codes=dict(location.get('metro_area_codes') or {}),

        enrich_profile=getattr(vertical, 'ENRICH_PROFILE', None),
        vendor_domains_extra=frozenset(
            getattr(vertical, 'VENDOR_DOMAINS_EXTRA', frozenset())
        ) | frozenset(
            getattr(o, 'VENDOR_DOMAINS_EXTRA', frozenset()) if o else frozenset()
        ),
        independent_filters=dict(
            getattr(vertical, 'INDEPENDENT_FILTERS', {})
        ),

        osint_enabled=getattr(vertical, 'OSINT_ENABLED', False),
        osint_sources=list(getattr(vertical, 'OSINT_SOURCES', [])),
        osint_fields_desired=list(getattr(vertical, 'OSINT_FIELDS_DESIRED', [])),
        osint_confidence_threshold=float(
            getattr(vertical, 'OSINT_CONFIDENCE_THRESHOLD', 0.85)
        ),
        osint_handoff_fields=list(getattr(vertical, 'OSINT_HANDOFF_FIELDS', [])),
        osint_serp_queries=dict(getattr(vertical, 'OSINT_SERP_QUERIES', {})),
        osint_deep_crawl_paths=list(
            getattr(vertical, 'OSINT_DEEP_CRAWL_PATHS', [])
        ),
        osint_industry_terms=list(getattr(vertical, 'OSINT_INDUSTRY_TERMS', [])),
    )
```

- [ ] **Step A6.4: Run tests, confirm pass**

```bash
python outreach/lib/campaign_config_tests.py
```

Expected: `OK` with 26 tests run.

- [ ] **Step A6.5: Commit**

```bash
git add outreach/lib/campaign_config.py outreach/lib/campaign_config_tests.py
git commit -m "feat(outreach): wire load_campaign end-to-end"
```

---

### Task A7: Create `lib/render_queries.py`

**Files:**
- Create: `outreach/lib/render_queries.py`
- Create: `outreach/lib/render_queries_tests.py`

The renderer turns a vertical's `query_templates.txt` (one template per line, using `{city}`, `{state}`, `{neighborhood}` placeholders) and a location's neighborhood lists into per-city `.txt` files in `campaigns/<c>/queries/`.

- [ ] **Step A7.1: Write failing tests for the renderer**

Create `outreach/lib/render_queries_tests.py`:

```python
"""Tests for outreach/lib/render_queries.py."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestRenderQueries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_substitutes_city_state_into_per_city_file(self):
        from lib.render_queries import render_for_campaign
        templates = '{vertical_keyword} in {city} {state}\n'
        location = {
            'metros': ['austin'],
            'neighborhoods': {'austin': []},
            'cities_state': {'austin': 'TX'},
            'cities_vertical_keyword': {'austin': 'dentist'},
        }
        out_dir = self.root / 'queries'
        render_for_campaign(templates, location, out_dir,
                            vertical_keyword='dentist')
        austin = (out_dir / 'austin.txt').read_text()
        self.assertEqual(austin.strip(), 'dentist in austin TX')

    def test_expands_neighborhood_lines_per_neighborhood(self):
        from lib.render_queries import render_for_campaign
        templates = (
            '{vertical_keyword} in {neighborhood} {city} {state}\n'
            '{vertical_keyword} clinic in {city} {state}\n'
        )
        location = {
            'metros': ['austin'],
            'neighborhoods': {'austin': ['Downtown', 'South Austin']},
            'cities_state': {'austin': 'TX'},
            'cities_vertical_keyword': {'austin': 'dentist'},
        }
        out_dir = self.root / 'queries'
        render_for_campaign(templates, location, out_dir,
                            vertical_keyword='dentist')
        lines = (out_dir / 'austin.txt').read_text().splitlines()
        self.assertIn('dentist in Downtown austin TX', lines)
        self.assertIn('dentist in South Austin austin TX', lines)
        self.assertIn('dentist clinic in austin TX', lines)
        self.assertEqual(len(lines), 3)

    def test_skips_template_with_neighborhood_when_city_has_none(self):
        from lib.render_queries import render_for_campaign
        templates = (
            '{vertical_keyword} in {neighborhood} {city} {state}\n'
            '{vertical_keyword} in {city} {state}\n'
        )
        location = {
            'metros': ['kyiv'],
            'neighborhoods': {'kyiv': []},
            'cities_state': {'kyiv': ''},
            'cities_vertical_keyword': {'kyiv': 'software agency'},
        }
        out_dir = self.root / 'queries'
        render_for_campaign(templates, location, out_dir,
                            vertical_keyword='software agency')
        lines = (out_dir / 'kyiv.txt').read_text().splitlines()
        self.assertEqual(lines, ['software agency in kyiv'])

    def test_writes_one_file_per_city(self):
        from lib.render_queries import render_for_campaign
        templates = '{vertical_keyword} in {city} {state}\n'
        location = {
            'metros': ['austin', 'phoenix'],
            'neighborhoods': {'austin': [], 'phoenix': []},
            'cities_state': {'austin': 'TX', 'phoenix': 'AZ'},
            'cities_vertical_keyword': {'austin': 'dentist', 'phoenix': 'dentist'},
        }
        out_dir = self.root / 'queries'
        render_for_campaign(templates, location, out_dir,
                            vertical_keyword='dentist')
        self.assertTrue((out_dir / 'austin.txt').exists())
        self.assertTrue((out_dir / 'phoenix.txt').exists())

    def test_idempotent_second_render_does_not_change_content(self):
        from lib.render_queries import render_for_campaign
        templates = '{vertical_keyword} in {city} {state}\n'
        location = {
            'metros': ['austin'],
            'neighborhoods': {'austin': []},
            'cities_state': {'austin': 'TX'},
            'cities_vertical_keyword': {'austin': 'dentist'},
        }
        out_dir = self.root / 'queries'
        render_for_campaign(templates, location, out_dir,
                            vertical_keyword='dentist')
        first = (out_dir / 'austin.txt').read_text()
        render_for_campaign(templates, location, out_dir,
                            vertical_keyword='dentist')
        self.assertEqual(first, (out_dir / 'austin.txt').read_text())


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step A7.2: Run tests, confirm failure**

```bash
python outreach/lib/render_queries_tests.py
```

Expected: `ModuleNotFoundError: No module named 'lib.render_queries'`.

- [ ] **Step A7.3: Implement the renderer**

Create `outreach/lib/render_queries.py`:

```python
"""Render per-city query files from a vertical template × a location.

Inputs:
    templates     — newline-separated template lines using placeholders
                    {vertical_keyword}, {city}, {state}, {neighborhood}.
                    Templates containing {neighborhood} expand once per
                    neighborhood in the city; templates without it emit
                    once per city.
    location      — dict with keys 'metros', 'neighborhoods',
                    'cities_state', 'cities_vertical_keyword'.
                    See render_queries_tests.py for shape.
    out_dir       — destination directory; files written as <city>.txt.

Pattern:
    Replace {city} with the metro name lowercased.
    Replace {state} with the per-city state (may be empty).
    Replace {vertical_keyword} with the caller-supplied default; per-city
        overrides are sourced from location['cities_vertical_keyword'].
    Replace {neighborhood} by expanding the line once per neighborhood.

The output is sorted-then-deduped per city so re-renders are stable.
"""
from __future__ import annotations

from pathlib import Path


def render_for_campaign(
    templates: str,
    location: dict,
    out_dir: Path,
    *,
    vertical_keyword: str,
) -> None:
    """Render templates × location into <out_dir>/<city>.txt files."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    template_lines = [
        line for line in (line.rstrip() for line in templates.splitlines())
        if line
    ]

    for city in location['metros']:
        state = location['cities_state'].get(city, '')
        neighborhoods = location['neighborhoods'].get(city) or []
        keyword = location['cities_vertical_keyword'].get(city, vertical_keyword)

        rendered: list[str] = []
        for tpl in template_lines:
            needs_neighborhood = '{neighborhood}' in tpl
            if needs_neighborhood:
                if not neighborhoods:
                    continue
                for nb in neighborhoods:
                    rendered.append(_substitute(
                        tpl, keyword=keyword, city=city, state=state,
                        neighborhood=nb,
                    ))
            else:
                rendered.append(_substitute(
                    tpl, keyword=keyword, city=city, state=state,
                ))

        # Dedupe in declaration order so re-renders are stable.
        seen: set[str] = set()
        ordered: list[str] = []
        for line in rendered:
            if line in seen:
                continue
            seen.add(line)
            ordered.append(line)

        (out_dir / f'{city}.txt').write_text('\n'.join(ordered) + '\n')


def _substitute(
    tpl: str,
    *,
    keyword: str,
    city: str,
    state: str,
    neighborhood: str = '',
) -> str:
    """Apply placeholder substitutions, then collapse any double spaces
    introduced when {state} or {neighborhood} resolves to an empty string."""
    out = (tpl
           .replace('{vertical_keyword}', keyword)
           .replace('{neighborhood}', neighborhood)
           .replace('{city}', city)
           .replace('{state}', state))
    while '  ' in out:
        out = out.replace('  ', ' ')
    return out.strip()
```

- [ ] **Step A7.4: Run tests, confirm pass**

```bash
python outreach/lib/render_queries_tests.py
```

Expected: `OK` with 5 tests run.

- [ ] **Step A7.5: Commit**

```bash
git add outreach/lib/render_queries.py outreach/lib/render_queries_tests.py
git commit -m "feat(outreach): add render_queries — vertical template × location"
```

---

### Task A8: Author `locations/sunbelt.yaml`

**Files:**
- Create: `outreach/locations/sunbelt.yaml`

Values come from `pipelines/dental_sunbelt/config.py`: `METRO_AREA_CODES` for austin/phoenix/tampa, the metro-portion of `GEOGRAPHIC_PREFIXES` (city/neighborhood names — leaving "family dental" etc. behind for the vertical), and the hand-written queries in `pipelines/dental_sunbelt/queries/*.txt` for neighborhood lists.

- [ ] **Step A8.1: Create the file**

Create `outreach/locations/sunbelt.yaml`:

```yaml
country: US
locale: en-US
cities:
  - name: austin
    state: TX
    metro_area_codes: ['512', '737']
    geographic_prefixes:
      - south austin
      - north austin
      - east austin
      - west austin
      - downtown austin
      - austin dental
      - round rock
      - cedar park
      - pflugerville dental
      - lakeway dental
    neighborhoods:
      - Downtown
      - South Austin
      - North Austin
      - East Austin
      - Westlake
      - Round Rock
      - Cedar Park
      - Pflugerville
      - Lakeway

  - name: phoenix
    state: AZ
    metro_area_codes: ['480', '602', '623', '928']
    geographic_prefixes:
      - chandler dental
      - mesa dental
      - gilbert dental
      - tempe dental
      - scottsdale dental
      - glendale dental
      - phoenix dental
    neighborhoods:
      - Downtown
      - Chandler
      - Mesa
      - Gilbert
      - Tempe
      - Scottsdale
      - Glendale

  - name: tampa
    state: FL
    metro_area_codes: ['813', '727', '941']
    geographic_prefixes:
      - south tampa
      - north tampa
      - new tampa
      - downtown tampa
      - tampa dental
      - brandon dental
      - st petersburg
      - st. petersburg
      - clearwater dental
      - wesley chapel
    neighborhoods:
      - South Tampa
      - North Tampa
      - New Tampa
      - Downtown
      - Brandon
      - St. Petersburg
      - Clearwater
      - Wesley Chapel
```

- [ ] **Step A8.2: Validate YAML parses cleanly**

Run:

```bash
python -c "import yaml; d=yaml.safe_load(open('outreach/locations/sunbelt.yaml')); assert len(d['cities'])==3, d; print('ok', [c['name'] for c in d['cities']])"
```

Expected: `ok ['austin', 'phoenix', 'tampa']`.

- [ ] **Step A8.3: Commit**

```bash
git add outreach/locations/sunbelt.yaml
git commit -m "feat(outreach): add locations/sunbelt.yaml"
```

---

### Task A9: Author `locations/ua.yaml`

**Files:**
- Create: `outreach/locations/ua.yaml`

Values from `pipelines/software_ua/config.py`: `METRO_AREA_CODES` includes the shared `_UA_MOBILE_PREFIXES` for each city, plus per-city landline codes. Neighborhood lists are empty (UA city queries don't expand by neighborhood).

- [ ] **Step A9.1: Create the file**

Create `outreach/locations/ua.yaml`:

```yaml
country: UA
locale: uk-UA
# UA mobile prefixes are nationwide (50, 63, 66, 67, 68, 73, 93, 95, 96, 97,
# 98, 99). They appear in every city's metro_area_codes because business
# mobiles outnumber landlines in software-agency listings; without them every
# mobile would flag as metro_mismatch.
cities:
  - name: kyiv
    state: ''
    metro_area_codes:
      ['44',
       '50', '63', '66', '67', '68', '73',
       '93', '95', '96', '97', '98', '99']
    geographic_prefixes:
      - kyiv
      - kiev
      - київ
      - ukraine
      - україна
    neighborhoods: []

  - name: lviv
    state: ''
    metro_area_codes:
      ['32',
       '50', '63', '66', '67', '68', '73',
       '93', '95', '96', '97', '98', '99']
    geographic_prefixes:
      - lviv
      - lvov
      - львів
    neighborhoods: []

  - name: dnipro
    state: ''
    metro_area_codes:
      ['56',
       '50', '63', '66', '67', '68', '73',
       '93', '95', '96', '97', '98', '99']
    geographic_prefixes:
      - dnipro
      - dnepr
      - дніпро
    neighborhoods: []
```

- [ ] **Step A9.2: Validate YAML parses cleanly**

```bash
python -c "import yaml; d=yaml.safe_load(open('outreach/locations/ua.yaml')); assert len(d['cities'])==3 and '44' in d['cities'][0]['metro_area_codes']; print('ok')"
```

Expected: `ok`.

- [ ] **Step A9.3: Commit**

```bash
git add outreach/locations/ua.yaml
git commit -m "feat(outreach): add locations/ua.yaml"
```

---

### Task A10: Author `locations/dallas.yaml`

**Files:**
- Create: `outreach/locations/dallas.yaml`

Values from `pipelines/cosmetic_surgeons_dallas/config.py`: `METRO_AREA_CODES['dallas']` and the DFW metroplex prefixes from `GEOGRAPHIC_PREFIXES`.

- [ ] **Step A10.1: Create the file**

Create `outreach/locations/dallas.yaml`:

```yaml
country: US
locale: en-US
cities:
  - name: dallas
    state: TX
    metro_area_codes: ['214', '469', '972', '945', '817', '682']
    geographic_prefixes:
      - dallas
      - north dallas
      - downtown dallas
      - uptown dallas
      - oak lawn
      - oak cliff
      - lakewood
      - deep ellum
      - bishop arts
      - knox-henderson
      - lower greenville
      - design district
      - victory park
      - west village
      - preston hollow
      - park cities
      - highland park
      - university park
      - plano
      - frisco
      - mckinney
      - allen
      - prosper
      - richardson
      - addison
      - garland
      - mesquite
      - irving
      - las colinas
      - lewisville
      - flower mound
      - southlake
      - grapevine
      - colleyville
      - fort worth
      - arlington
      - north texas
      - texas
      - dfw
      - metroplex
    neighborhoods:
      - Downtown
      - Uptown
      - North Dallas
      - Plano
      - Frisco
      - Richardson
      - Irving
      - Highland Park
```

- [ ] **Step A10.2: Validate YAML parses cleanly**

```bash
python -c "import yaml; d=yaml.safe_load(open('outreach/locations/dallas.yaml')); assert d['cities'][0]['name']=='dallas'; print('ok')"
```

Expected: `ok`.

- [ ] **Step A10.3: Commit**

```bash
git add outreach/locations/dallas.yaml
git commit -m "feat(outreach): add locations/dallas.yaml"
```

---

### Task A11: Author `locations/toronto.yaml`

**Files:**
- Create: `outreach/locations/toronto.yaml`

Values from `pipelines/retail_toronto/config.py`: `METRO_AREA_CODES['toronto']` and the Toronto/GTA neighborhood prefixes.

- [ ] **Step A11.1: Create the file**

Create `outreach/locations/toronto.yaml`:

```yaml
country: CA
locale: en-CA
cities:
  - name: toronto
    state: ON
    metro_area_codes: ['416', '647', '437', '905', '289', '365']
    geographic_prefixes:
      - downtown toronto
      - north york
      - scarborough
      - etobicoke
      - east york
      - york
      - yorkville
      - queen west
      - queen east
      - kensington market
      - kensington
      - the beaches
      - leslieville
      - liberty village
      - parkdale
      - bloor west
      - bloor street
      - king west
      - king east
      - distillery district
      - roncesvalles
      - church-wellesley
      - cabbagetown
      - rosedale
      - forest hill
      - st. clair
      - eglinton
      - lawrence
      - don mills
      - toronto
      - gta
    neighborhoods:
      - Downtown
      - North York
      - Scarborough
      - Etobicoke
      - Yorkville
      - Queen West
      - Liberty Village
      - Kensington Market
      - The Beaches
      - Leslieville
      - Distillery District
```

- [ ] **Step A11.2: Validate YAML parses cleanly**

```bash
python -c "import yaml; d=yaml.safe_load(open('outreach/locations/toronto.yaml')); assert '416' in d['cities'][0]['metro_area_codes']; print('ok')"
```

Expected: `ok`.

- [ ] **Step A11.3: Commit**

```bash
git add outreach/locations/toronto.yaml
git commit -m "feat(outreach): add locations/toronto.yaml"
```

---

### Task A12: Author `verticals/dentist/config.py`

**Files:**
- Create: `outreach/verticals/dentist/config.py`

This is the vertical-template extracted from `pipelines/dental_sunbelt/config.py` minus the location-specific data (`METRO_AREA_CODES`, `METROS`, `QUERIES_DIR`, the metro-name prefixes that moved to `locations/sunbelt.yaml`).

- [ ] **Step A12.1: Create the file**

Create `outreach/verticals/dentist/config.py`:

```python
"""Dentist vertical — shared template for any dental campaign.

Generic dental knobs that apply regardless of city/region. Region-specific
chain lists (e.g. Florida-heavy DSOs) go in campaigns/<c>/overrides.py
under DSO_TITLE_REGEX_EXTRA / DSO_EMAIL_DOMAINS_EXTRA.

Geographic prefixes here are vertical-generic descriptors only
("family dental", "general dental"). City-name prefixes live in
locations/<loc>.yaml so they travel with the location.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Make `lib.*` importable when this config is loaded standalone.
_OUTREACH_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_OUTREACH_ROOT) not in sys.path:
    sys.path.insert(0, str(_OUTREACH_ROOT))

from lib.enrichers.website_crawl import EnrichProfile

# ─────────────────────────────────────────────────────────────────────────────
# Pain ranking weights (vertical-agnostic STL hierarchy; dental weighting).
# ─────────────────────────────────────────────────────────────────────────────
PAIN_WEIGHTS: dict[str, int] = {
    'calls_unanswered':            5,
    'booking_friction':            4,
    'followup_dropped':            4,
    'billing_or_intake_errors':    4,
    'frontline_communication':     2,
    'service_quality_in_session':  1,
}

SERVICE_MAP: dict[str, tuple[str, str]] = {
    'calls_unanswered':            ('Voice AI Agents (Inbound Coverage)',          'silverthreadlabs.com/services/voice-agents'),
    'booking_friction':            ('Voice AI Booking + Agentic Self-Service',     'silverthreadlabs.com/services/voice-agents'),
    'followup_dropped':            ('Agentic AI Systems (Autonomous Follow-up)',   'silverthreadlabs.com/services/agentic-ai'),
    'billing_or_intake_errors':    ('Workflow Automation + Systems Integration',   'silverthreadlabs.com/services/workflow-automation'),
    'frontline_communication':     ('Voice AI + Agentic CRM Outreach',             'silverthreadlabs.com/services/voice-agents'),
    'service_quality_in_session':  ('Automation Audit',                            'silverthreadlabs.com/audit'),
}

# Vendors specific to dental practice websites.
VENDOR_DOMAINS_EXTRA: frozenset[str] = frozenset({
    'gargle.com',
    'officite.com',
    'mydentalmail.com',
    'dentalqore.com',
    'progressivedental.com',
})

ENRICH_PROFILE = EnrichProfile(
    poc_title_markers_js=r"\b(?:Dr\.?|DDS|DMD|D\.D\.S\.?|D\.M\.D\.?)\b",
    jsonld_person_types=("person", "dentist", "physician"),
    practice_name_words=frozenset({
        "dental", "dentistry", "smiles", "orthodontics",
        "clinic", "office", "practice",
    }),
    internal_link_gate_js=r"(contact|about|team|staff|get-in-touch|our-team|meet|providers|doctors|dentist|dr-)",
    contact_link_pattern=r"/(contact|get-in-touch)",
    team_link_pattern=r"/(team|staff|providers|doctors|our-doctor|meet|about)",
)

# National + multi-state dental DSOs — applies everywhere a dental
# campaign runs. Florida-only or Texas-only chains go in campaigns/
# <c>/overrides.py as DSO_TITLE_REGEX_EXTRA.
DSO_TITLE_REGEX = re.compile(
    r'\b('
    r'Aspen Dental|Heartland Dental|Pacific Dental|Smile Direct|SmileDirectClub|'
    r'Western Dental|Great Expressions|Sage Dental|Affordable Dentures|Affordable Care|'
    r'Gentle Dental|Comfort Dental|Monarch Dental|Kool Smiles|Mint Dentistry|'
    r'Dental Depot|Castle Dental|Birner|Jefferson Dental|ClearChoice|Perfect Teeth|'
    r'Smile Brands|Bright Now|Merit Dental|Midwest Dental|Mondovi Dental|'
    r'Smile Generation|'
    r'Dental Care Alliance|North American Dental|NADG|Tend Dental|'
    r'Benevis|MB2 Dental|42 North Dental|InterDent|Smile Doctors|'
    r'My Dentist Group|Aspida Dental|'
    r'Ideal Dental|Rose Dental Group|Advanced Dental Care of|'
    r'Signature Smiles|Coast Dental Smilecare|Smilecare|Westwind Dental|'
    r'The Smile Design'
    r')\b', re.I,
)

DSO_EMAIL_DOMAINS: set[str] = {
    'nadentalgroup.com',
    'mb2dental.com',
    'mydentistgroup.com',
    'aspidamail.com',
    'smilegeneration.com',
    'smilegen.com',
    'thesmiledesign.com',
    'aspendental.com',
    'heartlanddental.com',
    'pdsdental.com',
    'gargle.com',
    'rola.com',
    'mydentalmail.com',
}

# Vertical-generic descriptors that look like brand prefixes but are
# pure category words. City/neighborhood names live in locations/<loc>.yaml.
GEOGRAPHIC_PREFIXES_GENERIC: set[str] = {
    'family dental', 'general dental', 'cosmetic dental', 'modern dental',
    'advanced dental', 'gentle dental',
}

INDEPENDENT_FILTERS = {
    'max_rating_exclusive': 5.0,
    'min_pain_categories':  1,
    'exclude_chains':       True,
}

# ─────────────────────────────────────────────────────────────────────────────
# OSINT enrichment — see outreach/docs/2026-05-07-osint-enrichment-design.md
# ─────────────────────────────────────────────────────────────────────────────
OSINT_ENABLED = True
OSINT_SOURCES = ["whois", "deep_site_crawl", "serp"]
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
    "/leadership", "/our-doctors", "/dentists",
    "/contact", "/contact-us",
]

OSINT_INDUSTRY_TERMS = ["dentist", "DDS", "DMD", "dental practice"]
```

- [ ] **Step A12.2: Sanity-check by importing**

```bash
python -c "import sys; sys.path.insert(0, 'outreach'); import importlib.util as u; s=u.spec_from_file_location('v', 'outreach/verticals/dentist/config.py'); m=u.module_from_spec(s); s.loader.exec_module(m); assert m.PAIN_WEIGHTS['calls_unanswered']==5; print('ok')"
```

Expected: `ok`.

- [ ] **Step A12.3: Commit**

```bash
git add outreach/verticals/dentist/config.py
git commit -m "feat(outreach): add verticals/dentist/config.py"
```

---

### Task A13: Author `verticals/dentist/query_templates.txt` and README

**Files:**
- Create: `outreach/verticals/dentist/query_templates.txt`
- Create: `outreach/verticals/dentist/README.md`

Templates derived from the existing hand-written `pipelines/dental_sunbelt/queries/austin.txt`.

- [ ] **Step A13.1: Create the templates file**

Create `outreach/verticals/dentist/query_templates.txt`:

```
{vertical_keyword} in {neighborhood} {city} {state}
{vertical_keyword} clinic in {city} {state}
```

- [ ] **Step A13.2: Create the README**

Create `outreach/verticals/dentist/README.md`:

```markdown
# Dentist vertical

Targets independent dental practices for Silverthread Labs Voice AI
+ Agentic AI services. Pain weighting prioritizes call coverage,
booking friction, and follow-up — the categories STL's product
directly addresses.

## Default vertical_keyword

`dentist` — set per-city in `locations/<loc>.yaml` if a market uses
a different industry term.

## Query templates

See `query_templates.txt`. Placeholders: `{vertical_keyword}`,
`{city}`, `{state}`, `{neighborhood}`. Lines containing
`{neighborhood}` are expanded once per neighborhood in
`locations/<loc>.yaml`; lines without it emit once per city.

## Adding a dental campaign

1. Author or pick a location: `outreach/locations/<loc>.yaml`
2. Create the campaign dir: `outreach/campaigns/dentist_<loc>/`
3. Write `campaign.yaml`:
   ```yaml
   vertical: dentist
   location: <loc>
   slug: dentist_<loc>
   ```
4. Generate queries: `python outreach/lib/render_queries.py dentist_<loc>`
5. Scrape Google Maps; persist NDJSON to `raw/<city>.json`.
6. Run the pipeline: `python outreach/lib/cli/analyze.py dentist_<loc>` etc.
```

- [ ] **Step A13.3: Commit**

```bash
git add outreach/verticals/dentist/query_templates.txt outreach/verticals/dentist/README.md
git commit -m "feat(outreach): add dentist query templates and README"
```

---

### Task A14: Author `verticals/software/config.py`

**Files:**
- Create: `outreach/verticals/software/config.py`

Vertical template extracted from `pipelines/software_ua/config.py`. Note the Ezly-specific weighting/services stay in the vertical default here because no other software campaign exists yet; a future `software_houston` would inherit them. If a campaign wants different weights it sets them in `overrides.py`.

The UA-specific outsourcer list (EPAM, GlobalLogic, etc.) moves to `campaigns/software_ua/overrides.py` as `DSO_TITLE_REGEX_EXTRA` since those are regional. The global big-IT list (Accenture, Capgemini, IBM) stays in the vertical default because it applies everywhere.

- [ ] **Step A14.1: Create the file**

Create `outreach/verticals/software/config.py`:

```python
"""Software / digital-agency vertical — shared template.

Default weighting tuned for Ezly's AI communication assistant ICP
(small/mid agencies). Campaigns can override PAIN_WEIGHTS and
SERVICE_MAP in their overrides.py if pitching a different product.

Region-specific outsourcer brand lists (UA: EPAM, GlobalLogic; etc.)
go in campaigns/<c>/overrides.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_OUTREACH_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_OUTREACH_ROOT) not in sys.path:
    sys.path.insert(0, str(_OUTREACH_ROOT))

from lib.enrichers.website_crawl import EnrichProfile

PAIN_WEIGHTS: dict[str, int] = {
    'frontline_communication':     5,
    'followup_dropped':            5,
    'calls_unanswered':            4,
    'deadline_missed':             2,
    'scope_drift':                 2,
    'service_quality_in_session':  1,
    'delivery_quality':            1,
    'hidden_subcontracting':       1,
    'booking_friction':            1,
    'billing_or_intake_errors':    1,
}

SERVICE_MAP: dict[str, tuple[str, str]] = {
    'frontline_communication':     ('Ezly — AI Communication Assistant (tone + personalization)',     'getezly.com/home'),
    'followup_dropped':            ('Ezly — AI Communication Assistant (faster client follow-up)',    'getezly.com/home'),
    'calls_unanswered':            ('Ezly — AI Communication Assistant (never miss a reply)',         'getezly.com/home'),
    'deadline_missed':             ('Ezly — AI Communication Assistant (expectation-setting replies)','getezly.com/home'),
    'scope_drift':                 ('Ezly — AI Communication Assistant (proposal generator)',         'getezly.com/home'),
    'service_quality_in_session':  ('Ezly — AI Communication Assistant (client-comms layer)',         'getezly.com/home'),
    'delivery_quality':            ('Ezly — AI Communication Assistant (client-comms layer)',         'getezly.com/home'),
    'hidden_subcontracting':       ('Ezly — AI Communication Assistant (client-comms layer)',         'getezly.com/home'),
    'booking_friction':            ('Ezly — AI Communication Assistant (proposal generator)',         'getezly.com/home'),
    'billing_or_intake_errors':    ('Ezly — AI Communication Assistant (proposal generator)',         'getezly.com/home'),
}

VENDOR_DOMAINS_EXTRA: frozenset[str] = frozenset({
    'clutch.co',
    'goodfirms.co',
    'designrush.com',
    'manifest.com',
    'sortlist.com',
})

ENRICH_PROFILE = EnrichProfile(
    poc_title_markers_js=r"\b(?:CEO|CTO|COO|CFO|Founder|Co-?Founder|Owner|Principal|Partner|Managing Director|Director)\b",
    jsonld_person_types=("person",),
    practice_name_words=frozenset({
        "software", "digital", "agency", "studio", "lab", "labs",
        "technologies", "tech", "solutions", "systems", "consulting",
        "interactive", "creative",
    }),
    internal_link_gate_js=r"(contact|about|team|leadership|founders|management|people|company|who-we-are)",
    contact_link_pattern=r"/(contact|contact-us|get-in-touch|hello)",
    team_link_pattern=r"/(team|about|leadership|founders|management|people|company|who-we-are)",
)

# Global big-IT outsourcers and SaaS giants — never Ezly buyers regardless
# of region. Regional outsourcers (EPAM, SoftServe for UA; TCS, Wipro for IN)
# go in the campaign's overrides.py.
DSO_TITLE_REGEX = re.compile(
    r'\b('
    r'Accenture|Capgemini|Cognizant|HCL|IBM|Microsoft|Google|Oracle|SAP|'
    r'Deloitte|EY|PwC|KPMG|McKinsey|BCG|Bain'
    r')\b', re.I,
)

DSO_EMAIL_DOMAINS: set[str] = {
    'accenture.com',
    'capgemini.com',
    'cognizant.com',
    'hcl.com',
    'ibm.com',
    'microsoft.com',
    'google.com',
    'oracle.com',
    'sap.com',
    'deloitte.com',
    'ey.com',
    'pwc.com',
    'kpmg.com',
}

GEOGRAPHIC_PREFIXES_GENERIC: set[str] = {
    'web studio', 'web design', 'design studio', 'digital agency',
    'software development', 'software company', 'it company',
}

INDEPENDENT_FILTERS = {
    'max_rating_exclusive': 5.0,
    'min_pain_categories':  1,
    'exclude_chains':       True,
}

OSINT_ENABLED = True
OSINT_SOURCES = ["whois", "deep_site_crawl", "serp"]
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
    "linkedin_url_poc":     'site:linkedin.com/in "{poc_name}" "{city}" software OR CEO OR founder',
    "linkedin_url_company": 'site:linkedin.com/company "{business_name}" "{city}"',
    "social_urls":          '"{business_name}" "{city}" linkedin OR instagram OR facebook',
    "news_mentions":        '"{business_name}" "{city}" news OR press OR launch',
}

OSINT_DEEP_CRAWL_PATHS = [
    "/about", "/about-us", "/team", "/our-team", "/leadership",
    "/founders", "/management", "/people", "/company",
    "/contact", "/contact-us", "/hello",
]

OSINT_INDUSTRY_TERMS = ["software", "digital agency", "web development", "design studio", "outsourcing"]
```

- [ ] **Step A14.2: Sanity-check the import**

```bash
python -c "import importlib.util as u; s=u.spec_from_file_location('v','outreach/verticals/software/config.py'); m=u.module_from_spec(s); s.loader.exec_module(m); assert m.PAIN_WEIGHTS['frontline_communication']==5; print('ok')"
```

Expected: `ok`.

- [ ] **Step A14.3: Commit**

```bash
git add outreach/verticals/software/config.py
git commit -m "feat(outreach): add verticals/software/config.py"
```

---

### Task A15: Author `verticals/software/query_templates.txt` and README

**Files:**
- Create: `outreach/verticals/software/query_templates.txt`
- Create: `outreach/verticals/software/README.md`

- [ ] **Step A15.1: Create the templates file**

Create `outreach/verticals/software/query_templates.txt`:

```
software agency in {city}
digital agency in {city}
software development company in {city}
design studio in {city}
web development company in {city}
```

- [ ] **Step A15.2: Create the README**

Create `outreach/verticals/software/README.md`:

```markdown
# Software / digital-agency vertical

Targets small-to-mid software, digital, and design agencies for Ezly
(AI reply assistant for client communication). Pain weighting
prioritizes communication-quality signals: tone, response speed,
follow-up.

## Default vertical_keyword

`software agency` — set per-city in `locations/<loc>.yaml` if a
market uses a different industry term.

## Honest fit notes

Ezly's ICP is solo freelancers on Upwork/Fiverr. The lists this
vertical scrapes (small/mid agencies) skew weaker than dental
gold sets (F1 ~0.78 vs ~0.85) because Google Maps reviews for B2B
software shops discuss project-delivery pain, not response-speed
pain. Pipeline proceeds anyway.

## Adding a software campaign

1. Author or pick a location: `outreach/locations/<loc>.yaml`
2. Create the campaign dir: `outreach/campaigns/software_<loc>/`
3. Write `campaign.yaml` (`vertical: software`, `location: <loc>`)
4. Optional: add `overrides.py` with regional outsourcer brand list
   (e.g. `DSO_TITLE_REGEX_EXTRA` for EPAM/GlobalLogic in UA).
5. Generate queries, scrape, run the pipeline.
```

- [ ] **Step A15.3: Commit**

```bash
git add outreach/verticals/software/query_templates.txt outreach/verticals/software/README.md
git commit -m "feat(outreach): add software query templates and README"
```

---

### Task A16: Author `verticals/cosmetic_surgery/`

**Files:**
- Create: `outreach/verticals/cosmetic_surgery/config.py`
- Create: `outreach/verticals/cosmetic_surgery/query_templates.txt`
- Create: `outreach/verticals/cosmetic_surgery/README.md`

Values from `pipelines/cosmetic_surgeons_dallas/config.py` minus the Dallas metro data.

- [ ] **Step A16.1: Create config.py**

Create `outreach/verticals/cosmetic_surgery/config.py`:

```python
"""Cosmetic / plastic surgery vertical — shared template.

Pain taxonomy unchanged from dental (vertical-agnostic STL hierarchy).
National chain list here; regional dermatology DSOs go in
campaigns/<c>/overrides.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_OUTREACH_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_OUTREACH_ROOT) not in sys.path:
    sys.path.insert(0, str(_OUTREACH_ROOT))

from lib.enrichers.website_crawl import EnrichProfile

PAIN_WEIGHTS: dict[str, int] = {
    'calls_unanswered':            5,
    'booking_friction':            4,
    'followup_dropped':            4,
    'billing_or_intake_errors':    4,
    'frontline_communication':     2,
    'service_quality_in_session':  1,
}

SERVICE_MAP: dict[str, tuple[str, str]] = {
    'calls_unanswered':            ('Voice AI Agents (Inbound Coverage)',          'silverthreadlabs.com/services/voice-agents'),
    'booking_friction':            ('Voice AI Booking + Agentic Self-Service',     'silverthreadlabs.com/services/voice-agents'),
    'followup_dropped':            ('Agentic AI Systems (Autonomous Follow-up)',   'silverthreadlabs.com/services/agentic-ai'),
    'billing_or_intake_errors':    ('Workflow Automation + Systems Integration',   'silverthreadlabs.com/services/workflow-automation'),
    'frontline_communication':     ('Voice AI + Agentic CRM Outreach',             'silverthreadlabs.com/services/voice-agents'),
    'service_quality_in_session':  ('Automation Audit',                            'silverthreadlabs.com/audit'),
}

VENDOR_DOMAINS_EXTRA: frozenset[str] = frozenset({
    'rosemontmedia.com',
    'influxmarketing.com',
    'studioiii.com',
})

ENRICH_PROFILE = EnrichProfile(
    poc_title_markers_js=r"\b(?:Dr\.?|MD|M\.D\.?|D\.O\.?|DO|FACS|F\.A\.C\.S\.?)\b",
    jsonld_person_types=("person", "physician"),
    practice_name_words=frozenset({
        "plastic", "cosmetic", "surgery", "surgical",
        "aesthetics", "aesthetic", "medspa", "facial",
        "clinic", "institute", "center",
    }),
    internal_link_gate_js=r"(contact|about|team|staff|providers|surgeons|doctors|meet|our-team|dr-|practice)",
    contact_link_pattern=r"/(contact|get-in-touch|consultation|reach-us)",
    team_link_pattern=r"/(team|staff|providers|doctors|surgeons|meet|about|our-(?:doctor|surgeon|team))",
)

# National cosmetic / plastic surgery chains. Regional dermatology DSOs
# (Westlake Dermatology in TX, etc.) go in campaigns/<c>/overrides.py.
DSO_TITLE_REGEX = re.compile(
    r'\b('
    r'Sono Bello|SonoBello|'
    r'LaserAway|Laser Away|'
    r'Ideal Image|'
    r'Skinney Medspa|'
    r'Athena Cosmetic|'
    r'Bosley|Hair Club|'
    r'Plastic Surgery Group of'
    r')\b', re.I,
)

DSO_EMAIL_DOMAINS: set[str] = {
    'sonobello.com',
    'laseraway.com',
    'idealimage.com',
    'bosley.com',
    'hairclub.com',
}

GEOGRAPHIC_PREFIXES_GENERIC: set[str] = {
    'advanced cosmetic', 'modern cosmetic', 'premier plastic',
    'advanced plastic', 'modern plastic', 'aesthetic',
    'family cosmetic',
}

INDEPENDENT_FILTERS = {
    'max_rating_exclusive': 5.0,
    'min_pain_categories':  1,
    'exclude_chains':       True,
}

# OSINT not yet wired for this vertical — disabled to avoid the OSINT_*
# fields being absent triggering require_attr errors downstream.
OSINT_ENABLED = False
OSINT_SOURCES = []
OSINT_FIELDS_DESIRED = []
OSINT_CONFIDENCE_THRESHOLD = 0.85
OSINT_HANDOFF_FIELDS = []
OSINT_SERP_QUERIES = {}
OSINT_DEEP_CRAWL_PATHS = []
OSINT_INDUSTRY_TERMS = []
```

- [ ] **Step A16.2: Create query_templates.txt**

Create `outreach/verticals/cosmetic_surgery/query_templates.txt`:

```
cosmetic surgeon in {city} {state}
plastic surgeon in {city} {state}
medspa in {city} {state}
aesthetic clinic in {city} {state}
```

- [ ] **Step A16.3: Create README.md**

Create `outreach/verticals/cosmetic_surgery/README.md`:

```markdown
# Cosmetic / Plastic Surgery vertical

Targets independent cosmetic + plastic surgery practices and medspas
for Silverthread Labs Voice AI + Agentic AI services.

## Default vertical_keyword

`cosmetic surgeon` — varies per template line; `query_templates.txt`
also covers `plastic surgeon`, `medspa`, and `aesthetic clinic`.

## Adding a cosmetic-surgery campaign

1. Author or pick a location.
2. Create `campaigns/cosmetic_surgery_<loc>/campaign.yaml`.
3. If the location has regional dermatology DSOs (USDP, Westlake
   Dermatology in TX), add them to `overrides.py` as
   `DSO_TITLE_REGEX_EXTRA`.
```

- [ ] **Step A16.4: Sanity-check**

```bash
python -c "import importlib.util as u; s=u.spec_from_file_location('v','outreach/verticals/cosmetic_surgery/config.py'); m=u.module_from_spec(s); s.loader.exec_module(m); assert m.PAIN_WEIGHTS['calls_unanswered']==5; print('ok')"
```

Expected: `ok`.

- [ ] **Step A16.5: Commit**

```bash
git add outreach/verticals/cosmetic_surgery/
git commit -m "feat(outreach): add cosmetic_surgery vertical"
```

---

### Task A17: Author `verticals/retail/`

**Files:**
- Create: `outreach/verticals/retail/config.py`
- Create: `outreach/verticals/retail/query_templates.txt`
- Create: `outreach/verticals/retail/README.md`

Values from `pipelines/retail_toronto/config.py` minus Toronto-specific chains/malls (those move to `campaigns/retail_toronto/overrides.py`).

- [ ] **Step A17.1: Create config.py**

Create `outreach/verticals/retail/config.py`:

```python
"""Retail vertical — shared template.

Pain taxonomy unchanged from dental (vertical-agnostic STL hierarchy);
fit on retail is unproven. Treat retail campaigns as exploratory.

National retail chains here; regional/country-specific chains
(Canadian Tire, Loblaws, Toronto mall properties) go in
campaigns/<c>/overrides.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_OUTREACH_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_OUTREACH_ROOT) not in sys.path:
    sys.path.insert(0, str(_OUTREACH_ROOT))

from lib.enrichers.website_crawl import EnrichProfile

PAIN_WEIGHTS: dict[str, int] = {
    'calls_unanswered':            5,
    'booking_friction':            4,
    'followup_dropped':            4,
    'billing_or_intake_errors':    4,
    'frontline_communication':     2,
    'service_quality_in_session':  1,
}

SERVICE_MAP: dict[str, tuple[str, str]] = {
    'calls_unanswered':            ('Voice AI Agents (Inbound Coverage)',          'silverthreadlabs.com/services/voice-agents'),
    'booking_friction':            ('Voice AI Booking + Agentic Self-Service',     'silverthreadlabs.com/services/voice-agents'),
    'followup_dropped':            ('Agentic AI Systems (Autonomous Follow-up)',   'silverthreadlabs.com/services/agentic-ai'),
    'billing_or_intake_errors':    ('Workflow Automation + Systems Integration',   'silverthreadlabs.com/services/workflow-automation'),
    'frontline_communication':     ('Voice AI + Agentic CRM Outreach',             'silverthreadlabs.com/services/voice-agents'),
    'service_quality_in_session':  ('Automation Audit',                            'silverthreadlabs.com/audit'),
}

VENDOR_DOMAINS_EXTRA: frozenset[str] = frozenset({
    'lightspeedhq.com',
    'shoplazza.com',
    'bigcartel.com',
})

ENRICH_PROFILE = EnrichProfile(
    poc_title_markers_js=r"\b(?:Owner|Founder|Co-?Founder|Manager|Store Manager|General Manager|Buyer|Director|President)\b",
    jsonld_person_types=("person",),
    practice_name_words=frozenset({
        "shop", "store", "boutique", "market", "retail",
        "co", "company", "inc", "ltd",
    }),
    internal_link_gate_js=r"(contact|about|team|staff|our-story|story|owner|founder|meet|locations)",
    contact_link_pattern=r"/(contact|get-in-touch|reach-us)",
    team_link_pattern=r"/(team|staff|about|our-story|story|owner|founder|meet|people)",
)

# Cross-border national retail chains. Country-specific chains
# (Canadian Tire, Loblaws, Target's Australia push) live in
# campaigns/<c>/overrides.py.
DSO_TITLE_REGEX = re.compile(
    r'\b('
    r'Walmart|Costco|IKEA|Best Buy|Staples|'
    r'H&M|Zara|Uniqlo|Old Navy|Gap|Banana Republic|'
    r'Lululemon|Nike|Adidas|ALDO|Foot Locker|Champs Sports|'
    r'Urban Outfitters|Anthropologie|Free People|MUJI|'
    r'Sephora|MAC|Bath & Body Works|Lush|The Body Shop|'
    r'Apple Store|Microsoft Store|'
    r'Williams[- ]Sonoma|Pottery Barn|West Elm|Crate & Barrel'
    r')\b', re.I,
)

DSO_EMAIL_DOMAINS: set[str] = {
    'walmart.com',
    'costco.com',
    'ikea.com',
    'lululemon.com',
    'nike.com',
    'adidas.com',
    'sephora.com',
    'apple.com',
}

GEOGRAPHIC_PREFIXES_GENERIC: set[str] = set()

INDEPENDENT_FILTERS = {
    'max_rating_exclusive': 5.0,
    'min_pain_categories':  1,
    'exclude_chains':       True,
}

OSINT_ENABLED = False
OSINT_SOURCES = []
OSINT_FIELDS_DESIRED = []
OSINT_CONFIDENCE_THRESHOLD = 0.85
OSINT_HANDOFF_FIELDS = []
OSINT_SERP_QUERIES = {}
OSINT_DEEP_CRAWL_PATHS = []
OSINT_INDUSTRY_TERMS = []
```

- [ ] **Step A17.2: Create query_templates.txt**

Create `outreach/verticals/retail/query_templates.txt`:

```
boutique in {neighborhood} {city}
shop in {neighborhood} {city}
independent retailer in {city}
specialty store in {city}
```

- [ ] **Step A17.3: Create README.md**

Create `outreach/verticals/retail/README.md`:

```markdown
# Retail vertical — exploratory

Targets small-to-medium independent retail. STL's product (voice
agents + workflow automation) is built for phone-heavy service
businesses; fit on retail is unproven.

## Default vertical_keyword

`boutique` (template-specific — see `query_templates.txt`).

## Adding a retail campaign

Country-specific national chains (Canadian Tire, Loblaws, Apple Stores
in CA) belong in `campaigns/<c>/overrides.py` as
`DSO_TITLE_REGEX_EXTRA`. Mall property listings should be flagged the
same way so the analyze step excludes them from the buyer set.
```

- [ ] **Step A17.4: Sanity-check**

```bash
python -c "import importlib.util as u; s=u.spec_from_file_location('v','outreach/verticals/retail/config.py'); m=u.module_from_spec(s); s.loader.exec_module(m); assert m.PAIN_WEIGHTS['calls_unanswered']==5; print('ok')"
```

Expected: `ok`.

- [ ] **Step A17.5: Commit**

```bash
git add outreach/verticals/retail/
git commit -m "feat(outreach): add retail vertical"
```

---

### Task A18: Equivalence test — new loader matches old pipeline configs

This is the **gate** for Phase B. If this fails, the migration is wrong.

**Files:**
- Create: `outreach/lib/equivalence_test.py`

- [ ] **Step A18.1: Write the equivalence test**

Create `outreach/lib/equivalence_test.py`:

```python
"""Phase-A gate test: the new loader output must match each existing
pipelines/<x>/config.py module on every field the CLI scripts read.

Skipped when run after Phase B (the old pipelines/ dirs go away).
"""
from __future__ import annotations

import importlib.util as iu
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.campaign_config import load_campaign


# (campaign_slug_new, old_pipeline_dir) — only campaigns that exist in
# pipelines/ today. Once Phase B/C move them, this list goes empty
# and the test stops running (see setUpClass below).
MIGRATIONS = [
    ('dentist_sunbelt',           'dental_sunbelt'),
    ('software_ua',               'software_ua'),
    ('cosmetic_surgeons_dallas',  'cosmetic_surgeons_dallas'),
    ('retail_toronto',            'retail_toronto'),
]


def _load_old(pipeline_name: str):
    path = Path(__file__).resolve().parent.parent / 'pipelines' / pipeline_name / 'config.py'
    spec = iu.spec_from_file_location(f'old_{pipeline_name}', path)
    mod = iu.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestNewLoaderMatchesOldConfigs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        outreach_root = Path(__file__).resolve().parent.parent
        if not (outreach_root / 'pipelines').is_dir():
            raise unittest.SkipTest('pipelines/ already removed — phase B done')
        if not (outreach_root / 'campaigns').is_dir():
            raise unittest.SkipTest('campaigns/ not built yet — phase A incomplete')

    def _assert_equivalent(self, new, old, *, has_overrides=False):
        self.assertEqual(new.pain_weights, old.PAIN_WEIGHTS,
                         msg='PAIN_WEIGHTS diverge')
        self.assertEqual(new.service_map, old.SERVICE_MAP,
                         msg='SERVICE_MAP diverge')
        self.assertEqual(
            new.dso_email_domains,
            set(getattr(old, 'DSO_EMAIL_DOMAINS', set())),
            msg='DSO_EMAIL_DOMAINS diverge',
        )
        self.assertEqual(
            new.vendor_domains_extra,
            frozenset(getattr(old, 'VENDOR_DOMAINS_EXTRA', frozenset())),
            msg='VENDOR_DOMAINS_EXTRA diverge',
        )
        self.assertEqual(
            new.metros, getattr(old, 'METROS', []),
            msg='METROS diverge',
        )
        self.assertEqual(
            {m: set(c) for m, c in new.metro_area_codes.items()},
            {m: set(c) for m, c in getattr(old, 'METRO_AREA_CODES', {}).items()},
            msg='METRO_AREA_CODES diverge',
        )
        self.assertEqual(
            new.geographic_prefixes,
            set(getattr(old, 'GEOGRAPHIC_PREFIXES', set())),
            msg='GEOGRAPHIC_PREFIXES diverge (union of vertical generic + location must equal old)',
        )
        # ENRICH_PROFILE is a dataclass — compare field-by-field.
        old_profile = getattr(old, 'ENRICH_PROFILE', None)
        if old_profile is not None:
            self.assertEqual(new.enrich_profile, old_profile)
        # DSO_TITLE_REGEX: ensure every match the old regex finds is also
        # matched by the new (the new may match more — campaign extras
        # broaden coverage; we don't insist on strict equality).
        old_re = getattr(old, 'DSO_TITLE_REGEX', None)
        if old_re is not None:
            for sample in self._regex_samples_for_pipeline(old):
                if old_re.search(sample):
                    self.assertIsNotNone(
                        new.dso_title_regex.search(sample),
                        msg=f'new DSO regex missed {sample!r}',
                    )

    def _regex_samples_for_pipeline(self, old):
        """Pull a few illustrative strings from the old regex itself by
        extracting word-shape alternatives. Not exhaustive — meant as a
        smoke test."""
        out: list[str] = []
        for alt in re.findall(r'[A-Za-z][A-Za-z &]+', old.DSO_TITLE_REGEX.pattern):
            alt = alt.strip()
            if 4 <= len(alt) <= 30:
                out.append(alt)
        return out[:8]

    def test_each_migration_is_equivalent(self):
        outreach_root = Path(__file__).resolve().parent.parent
        for new_slug, old_name in MIGRATIONS:
            with self.subTest(slug=new_slug):
                old = _load_old(old_name)
                # Skip slugs whose campaign.yaml doesn't exist yet — A18
                # runs before B/C finish migrating each campaign.
                if not (outreach_root / 'campaigns' / new_slug / 'campaign.yaml').exists():
                    self.skipTest(f'campaign {new_slug} not yet built')
                new = load_campaign(new_slug)
                self._assert_equivalent(new, old)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step A18.2: Run the test now**

```bash
python outreach/lib/equivalence_test.py
```

Expected: all subTests SKIP with `campaign … not yet built` because Phase B/C haven't created any `campaigns/<slug>/campaign.yaml` files yet. The test infrastructure verifies (a) the new loader can be imported without exploding, (b) the old configs still load.

If you see a non-skip failure here, the loader is broken — fix before moving on.

- [ ] **Step A18.3: Commit**

```bash
git add outreach/lib/equivalence_test.py
git commit -m "test(outreach): add Phase-A gate equivalence test"
```

---

### Task A19: Run the full Phase A test suite

- [ ] **Step A19.1: Run every test under outreach/lib + outreach/scripts**

```bash
for t in $(find outreach/lib outreach/scripts outreach/tests -name 'test_*.py' -o -name '*_tests.py' -o -name 'equivalence_test.py' 2>/dev/null); do
  echo "=== $t ==="
  python "$t" || echo "FAILED: $t"
done
```

Expected: every existing test still passes. New `campaign_config_tests.py`, `render_queries_tests.py`, and `equivalence_test.py` all pass (or skip cleanly).

- [ ] **Step A19.2: If any failure, debug; otherwise move to Phase B**

No commit — this step is verification only.

---

## Phase B — Migrate `dental_sunbelt` end-to-end (canonical example)

Phase B is the most expensive single phase because every import surface flips. It produces the template that Phase C copies for the remaining campaigns.

---

### Task B1: Create `campaigns/dentist_sunbelt/campaign.yaml`

Note campaign rename: `dental_sunbelt` → `dentist_sunbelt` so the campaign vertical name matches `verticals/dentist/`.

**Files:**
- Create: `outreach/campaigns/dentist_sunbelt/campaign.yaml`

- [ ] **Step B1.1: Make the directory and file**

```bash
mkdir -p outreach/campaigns/dentist_sunbelt
```

Create `outreach/campaigns/dentist_sunbelt/campaign.yaml`:

```yaml
vertical: dentist
location: sunbelt
slug: dentist_sunbelt
display_name: Dental Sunbelt
created: 2026-04-25
status: active
```

- [ ] **Step B1.2: Verify the new loader works against the new campaign**

```bash
python -c "import sys; sys.path.insert(0,'outreach'); from lib.campaign_config import load_campaign; c=load_campaign('dentist_sunbelt'); print('vertical=', c.vertical, 'metros=', c.metros, 'pain[calls]=', c.pain_weights['calls_unanswered'])"
```

Expected: `vertical= dentist metros= ['austin', 'phoenix', 'tampa'] pain[calls]= 5`.

- [ ] **Step B1.3: Run the equivalence test — `dentist_sunbelt` subTest should now PASS**

```bash
python outreach/lib/equivalence_test.py
```

Expected: `dentist_sunbelt` no longer skipped; other 3 still skip; result `OK`. If equivalence fails, fix the YAML/vertical/loader before proceeding.

- [ ] **Step B1.4: Commit**

```bash
git add outreach/campaigns/dentist_sunbelt/campaign.yaml
git commit -m "feat(outreach): add campaigns/dentist_sunbelt/campaign.yaml"
```

---

### Task B2: Move scripts/ → lib/cli/ with `git mv`

This is the big bang for import paths. It happens in one commit so the codebase is consistent.

**Files:**
- Move: all of `outreach/scripts/` → `outreach/lib/cli/`

- [ ] **Step B2.1: Create lib/cli/ and move files**

```bash
mkdir -p outreach/lib/cli/tests
git mv outreach/scripts/__init__.py        outreach/lib/cli/__init__.py
git mv outreach/scripts/_common.py         outreach/lib/cli/_common.py
git mv outreach/scripts/analyze.py         outreach/lib/cli/analyze.py
git mv outreach/scripts/enrich.py          outreach/lib/cli/enrich.py
git mv outreach/scripts/handoff.py         outreach/lib/cli/handoff.py
git mv outreach/scripts/validate.py        outreach/lib/cli/validate.py
git mv outreach/scripts/merge_classifications.py    outreach/lib/cli/merge_classifications.py
git mv outreach/scripts/merge_crawl_into_master.py  outreach/lib/cli/merge_crawl_into_master.py
git mv outreach/scripts/merge_osint_into_master.py  outreach/lib/cli/merge_osint_into_master.py
git mv outreach/scripts/osint_enrich.py    outreach/lib/cli/osint_enrich.py
git mv outreach/scripts/owner_lookup.py    outreach/lib/cli/owner_lookup.py
git mv outreach/scripts/push_campaign.py   outreach/lib/cli/push_campaign.py
git mv outreach/scripts/push_leads.py      outreach/lib/cli/push_leads.py
git mv outreach/scripts/tests/__init__.py                       outreach/lib/cli/tests/__init__.py
git mv outreach/scripts/tests/test_analyze.py                   outreach/lib/cli/tests/test_analyze.py
git mv outreach/scripts/tests/test_common.py                    outreach/lib/cli/tests/test_common.py
git mv outreach/scripts/tests/test_merge_classifications.py     outreach/lib/cli/tests/test_merge_classifications.py
git mv outreach/scripts/tests/test_merge_crawl_into_master.py   outreach/lib/cli/tests/test_merge_crawl_into_master.py
git mv outreach/scripts/tests/test_merge_osint_into_master.py   outreach/lib/cli/tests/test_merge_osint_into_master.py
git mv outreach/scripts/tests/test_osint_enrich.py              outreach/lib/cli/tests/test_osint_enrich.py
git mv outreach/scripts/tests/test_owner_lookup.py              outreach/lib/cli/tests/test_owner_lookup.py
git mv outreach/scripts/tests/test_push_campaign.py             outreach/lib/cli/tests/test_push_campaign.py
git mv outreach/scripts/tests/test_push_leads.py                outreach/lib/cli/tests/test_push_leads.py
rmdir outreach/scripts/tests outreach/scripts 2>/dev/null || true
```

Verify:

```bash
ls outreach/scripts 2>&1 | head -3
```

Expected: `ls: cannot access 'outreach/scripts': No such file or directory`.

- [ ] **Step B2.2: Do NOT commit yet** — imports are broken; the next step fixes them.

---

### Task B3: Rewrite imports across `lib/cli/`

Every file in `lib/cli/` (and `lib/cli/tests/`) needs `from scripts.X` → `from lib.cli.X` and any literal string `'scripts.'` → `'lib.cli.'`. The `OUTREACH_ROOT / 'pipelines'` path strings also need to flip to `'campaigns'`.

**Files:**
- Modify: every file in `outreach/lib/cli/` and `outreach/lib/cli/tests/`

- [ ] **Step B3.1: Update `lib/cli/_common.py`**

Replace the body of `outreach/lib/cli/_common.py` with this (the only meaningful change is `pipelines` → `campaigns`; also drop `load_pipeline_config` legacy import path):

```python
"""
Shared CLI helpers for outreach/lib/cli/.

Each stage script (enrich, validate, handoff, …) takes a `<pipeline>`
positional arg (kept for back-compat — the value resolves to
`campaigns/<name>/`). The helpers below load the merged CampaignConfig
(via `lib.campaign_config.load_campaign`) and resolve paths under
`campaigns/<name>/{raw,enrichment,outputs}/`.

Concurrency: every script wraps its main work in `pipeline_lock(...)`,
which acquires an exclusive `.lock` file under the campaign directory.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

OUTREACH_ROOT = Path(__file__).resolve().parent.parent.parent

if str(OUTREACH_ROOT) not in sys.path:
    sys.path.insert(0, str(OUTREACH_ROOT))


def load_dotenv(path: Path | None = None) -> None:
    """Load a .env file into os.environ; do not override existing values."""
    env_file = path or OUTREACH_ROOT / '.env'
    if not env_file.exists():
        return
    with env_file.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def load_pipeline_config(pipeline_name: str):
    """Load merged CampaignConfig for `pipeline_name` (resolves to
    campaigns/<pipeline_name>/). Exits 2 with a clear stderr message
    if the campaign doesn't exist."""
    from lib.campaign_config import load_campaign
    campaign_dir = OUTREACH_ROOT / 'campaigns' / pipeline_name
    if not campaign_dir.is_dir():
        sys.stderr.write(
            f"error: campaign not found: {campaign_dir}\n"
        )
        sys.exit(2)
    try:
        return load_campaign(pipeline_name)
    except (FileNotFoundError, ValueError) as e:
        sys.stderr.write(f"error: failed to load campaign {pipeline_name!r}: {e}\n")
        sys.exit(2)


def pipeline_dir(pipeline_name: str) -> Path:
    return OUTREACH_ROOT / 'campaigns' / pipeline_name


def add_pipeline_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        'pipeline',
        help='campaign name, e.g. dentist_sunbelt — resolved against outreach/campaigns/<name>/',
    )


def require_attr(cfg, name: str, pipeline: str) -> object:
    """Look up `name` on the merged CampaignConfig. Names follow the
    legacy module-attribute style (PAIN_WEIGHTS, DSO_TITLE_REGEX, …);
    we translate them to the dataclass field names."""
    _MAPPING = {
        'PAIN_WEIGHTS':         'pain_weights',
        'SERVICE_MAP':          'service_map',
        'DSO_TITLE_REGEX':      'dso_title_regex',
        'DSO_EMAIL_DOMAINS':    'dso_email_domains',
        'GEOGRAPHIC_PREFIXES':  'geographic_prefixes',
        'METROS':               'metros',
        'METRO_AREA_CODES':     'metro_area_codes',
        'ENRICH_PROFILE':       'enrich_profile',
        'VENDOR_DOMAINS_EXTRA': 'vendor_domains_extra',
        'INDEPENDENT_FILTERS':  'independent_filters',
        'OSINT_ENABLED':        'osint_enabled',
        'OSINT_SOURCES':        'osint_sources',
        'OSINT_FIELDS_DESIRED': 'osint_fields_desired',
        'OSINT_CONFIDENCE_THRESHOLD': 'osint_confidence_threshold',
        'OSINT_HANDOFF_FIELDS': 'osint_handoff_fields',
        'OSINT_SERP_QUERIES':   'osint_serp_queries',
        'OSINT_DEEP_CRAWL_PATHS': 'osint_deep_crawl_paths',
        'OSINT_INDUSTRY_TERMS': 'osint_industry_terms',
        'VERTICAL':             'vertical',
    }
    field = _MAPPING.get(name)
    if field is None or not hasattr(cfg, field):
        sys.stderr.write(
            f"error: campaign {pipeline} does not define {name}\n"
        )
        sys.exit(2)
    return getattr(cfg, field)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@contextmanager
def pipeline_lock(pipeline_name: str, stage: str):
    """Acquire an exclusive .lock under campaigns/<pipeline_name>/.
    Same protocol as before, just rooted in campaigns/."""
    lockfile = pipeline_dir(pipeline_name) / '.lock'
    lockfile.parent.mkdir(parents=True, exist_ok=True)

    if lockfile.exists():
        try:
            holder = json.loads(lockfile.read_text())
        except (json.JSONDecodeError, OSError):
            sys.stderr.write(f"warn: corrupt lockfile {lockfile}; reclaiming\n")
            lockfile.unlink(missing_ok=True)
        else:
            holder_pid = holder.get('pid', 0)
            if _pid_alive(holder_pid):
                sys.stderr.write(
                    f"error: pipeline {pipeline_name!r} is locked by pid "
                    f"{holder_pid} (stage {holder.get('stage')!r}, "
                    f"since {holder.get('since')}).\n"
                    f"if that process is no longer running, delete {lockfile}\n"
                )
                sys.exit(2)
            sys.stderr.write(
                f"warn: stale lockfile {lockfile} (pid {holder_pid} not alive); reclaiming\n"
            )
            lockfile.unlink(missing_ok=True)

    payload = {
        'pid': os.getpid(),
        'stage': stage,
        'since': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    lockfile.write_text(json.dumps(payload))
    try:
        yield
    finally:
        try:
            current = json.loads(lockfile.read_text())
            if current.get('pid') == os.getpid():
                lockfile.unlink(missing_ok=True)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
```

- [ ] **Step B3.2: Update imports in every other file under `lib/cli/`**

For each file below, do a one-shot Edit per file. The mechanical change is:
- `from scripts._common` → `from lib.cli._common`
- `from scripts.validate` → `from lib.cli.validate`
- `from scripts.analyze` → `from lib.cli.analyze`
- `from scripts.merge_crawl_into_master` → `from lib.cli.merge_crawl_into_master`
- `from scripts.push_campaign` → `from lib.cli.push_campaign`
- Any literal string `'pipelines'` (in path constructions) → `'campaigns'`
- Any literal string `pipelines/` (in error messages, --help text) → `campaigns/`

Files to touch:

```
outreach/lib/cli/analyze.py
outreach/lib/cli/enrich.py
outreach/lib/cli/validate.py
outreach/lib/cli/handoff.py
outreach/lib/cli/merge_classifications.py
outreach/lib/cli/merge_crawl_into_master.py
outreach/lib/cli/merge_osint_into_master.py
outreach/lib/cli/osint_enrich.py
outreach/lib/cli/owner_lookup.py
outreach/lib/cli/push_campaign.py
outreach/lib/cli/push_leads.py
```

In `merge_classifications.py:_pipeline_from_path`, change:

```python
if 'pipelines' in parts:
    i = parts.index('pipelines')
```

to:

```python
if 'campaigns' in parts:
    i = parts.index('campaigns')
```

In `push_campaign.py:_vertical_from_config`, replace the function body. Old:

```python
def _vertical_from_config(cfg) -> str:
    if hasattr(cfg, 'VERTICAL'):
        return cfg.VERTICAL
    doc = (cfg.__doc__ or '').strip().split('\n')[0].strip()
    if doc:
        return doc.rstrip('.')
    return ''
```

New (the merged config carries `.vertical` directly):

```python
def _vertical_from_config(cfg) -> str:
    """Vertical name from merged CampaignConfig."""
    return getattr(cfg, 'vertical', '')
```

Run a sanity grep to confirm no stragglers:

```bash
grep -nR --include='*.py' '^from scripts\|^import scripts' outreach/lib outreach/campaigns 2>/dev/null
```

Expected: no output.

- [ ] **Step B3.3: Update test imports**

For each file under `outreach/lib/cli/tests/`, replace:
- `from scripts._common` → `from lib.cli._common`
- `from scripts.X` → `from lib.cli.X`
- `'scripts._common.OUTREACH_ROOT'` (in `patch` calls) → `'lib.cli._common.OUTREACH_ROOT'`
- `'pipelines'` (in test fixture mkdir paths) → `'campaigns'`
- `sys.path.insert(0, str(Path(__file__).parent.parent.parent))` → `sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))` (one extra `.parent` because the test now lives at `outreach/lib/cli/tests/` not `outreach/scripts/tests/`)

Files to touch:

```
outreach/lib/cli/tests/test_analyze.py
outreach/lib/cli/tests/test_common.py
outreach/lib/cli/tests/test_merge_classifications.py
outreach/lib/cli/tests/test_merge_crawl_into_master.py
outreach/lib/cli/tests/test_merge_osint_into_master.py
outreach/lib/cli/tests/test_osint_enrich.py
outreach/lib/cli/tests/test_owner_lookup.py
outreach/lib/cli/tests/test_push_campaign.py
outreach/lib/cli/tests/test_push_leads.py
```

Sanity grep:

```bash
grep -nR --include='*.py' 'from scripts\|patch.*scripts\._common' outreach/lib/cli/tests 2>/dev/null
```

Expected: no output.

- [ ] **Step B3.4: Update `push_leads.py` consumers of CampaignConfig fields**

`push_leads.py` reads `cfg.METROS` and `cfg.VERTICAL` via attribute access — convert to dataclass fields. In `outreach/lib/cli/push_leads.py`, find:

```python
metros = getattr(cfg, 'METROS', [])
metro = metros[0] if metros else ''
vertical = _vertical_from_config(cfg)
```

Replace with:

```python
metros = cfg.metros
metro = metros[0] if metros else ''
vertical = cfg.vertical
```

Same change in `outreach/lib/cli/analyze.py` (`metros = getattr(cfg, 'METROS', [])` → `metros = cfg.metros`).

Same change in `outreach/lib/cli/push_campaign.py`.

Sanity grep:

```bash
grep -nR --include='*.py' "getattr(cfg, 'METROS'" outreach/lib/cli 2>/dev/null
```

Expected: no output.

- [ ] **Step B3.5: Run the migrated test suite**

```bash
for t in $(find outreach/lib/cli/tests -name 'test_*.py'); do
  echo "=== $t ==="
  python "$t" || echo "FAILED: $t"
done
```

Expected: every test passes. If a test fails, the cause is almost always one of:
- Missed import rewrite (regrep).
- Test fixture builds `pipelines/test_vertical/` and `pipeline_lock` looks for `campaigns/test_vertical/` (fix: fixture path).
- Test patches `'scripts._common.OUTREACH_ROOT'` but module now lives at `lib.cli._common` (fix: patch target).

Fix and rerun until green. Do not commit until every test passes.

- [ ] **Step B3.6: Commit the migration**

```bash
git add -A outreach/lib/cli outreach/scripts
git commit -m "refactor(outreach): move scripts/ to lib/cli/; campaigns/ as new pipeline root"
```

---

### Task B4: Move `pipelines/dental_sunbelt/` data into `campaigns/dentist_sunbelt/`

**Files:**
- Move: `outreach/pipelines/dental_sunbelt/{queries,raw,enrichment,outputs,eval}` → `outreach/campaigns/dentist_sunbelt/`

- [ ] **Step B4.1: Move the data folders with `git mv`**

```bash
git mv outreach/pipelines/dental_sunbelt/queries     outreach/campaigns/dentist_sunbelt/queries
git mv outreach/pipelines/dental_sunbelt/raw         outreach/campaigns/dentist_sunbelt/raw
git mv outreach/pipelines/dental_sunbelt/enrichment  outreach/campaigns/dentist_sunbelt/enrichment
git mv outreach/pipelines/dental_sunbelt/outputs     outreach/campaigns/dentist_sunbelt/outputs
git mv outreach/pipelines/dental_sunbelt/eval        outreach/campaigns/dentist_sunbelt/eval
```

- [ ] **Step B4.2: Delete the old `config.py` and `__init__.py`**

```bash
git rm outreach/pipelines/dental_sunbelt/config.py
git rm outreach/pipelines/dental_sunbelt/__init__.py
```

If `outreach/pipelines/dental_sunbelt/` is now empty:

```bash
rmdir outreach/pipelines/dental_sunbelt 2>/dev/null || true
```

- [ ] **Step B4.3: Smoke-test the analyze CLI against the migrated data**

```bash
python outreach/lib/cli/analyze.py dentist_sunbelt --output-date 2026-05-25-smoke --force
```

Expected: completes without error; writes `outreach/campaigns/dentist_sunbelt/outputs/2026-05-25-smoke/master.json`.

- [ ] **Step B4.4: Field-level diff against the most recent existing master**

```bash
python - <<'PY'
import json
from pathlib import Path
base = Path('outreach/campaigns/dentist_sunbelt/outputs')
dates = sorted(p.name for p in base.iterdir() if p.is_dir() and p.name != '2026-05-25-smoke')
prev = base / dates[-1] / 'master.json'
new = base / '2026-05-25-smoke' / 'master.json'
a = {l['place_id']: l for l in json.loads(prev.read_text())}
b = {l['place_id']: l for l in json.loads(new.read_text())}
missing_in_new = set(a) - set(b)
extra_in_new   = set(b) - set(a)
print(f'prev={prev.name} new=2026-05-25-smoke leads_prev={len(a)} leads_new={len(b)}')
print(f'missing_in_new={len(missing_in_new)}  extra_in_new={len(extra_in_new)}')
diffs = 0
for pid in sorted(set(a) & set(b)):
    for k in ('quality_score', 'tier', 'is_chain_or_dso', 'chain_reason', 'metro', 'pain_breadth'):
        if a[pid].get(k) != b[pid].get(k):
            diffs += 1
            if diffs <= 5:
                print(f'  {pid} {k}: {a[pid].get(k)!r} -> {b[pid].get(k)!r}')
print(f'total field diffs over (quality_score, tier, chain, metro, pain_breadth): {diffs}')
PY
```

Expected: `missing_in_new=0`, `extra_in_new=0`, `total field diffs … : 0`.

If diffs > 0: the migration changed behavior. Investigate (most likely cause: a GEOGRAPHIC_PREFIXES entry didn't make it across; check `cfg.geographic_prefixes` vs the old `GEOGRAPHIC_PREFIXES`).

- [ ] **Step B4.5: Delete the smoke output**

```bash
rm -rf outreach/campaigns/dentist_sunbelt/outputs/2026-05-25-smoke
```

- [ ] **Step B4.6: Commit**

```bash
git add -A outreach/campaigns/dentist_sunbelt outreach/pipelines
git commit -m "refactor(outreach): migrate dental_sunbelt → campaigns/dentist_sunbelt"
```

---

### Task B5: Update `metro` field on existing master.json for renamed campaign

The `dental_sunbelt` → `dentist_sunbelt` rename does NOT change the `metro` field on leads (metro values are `austin`/`phoenix`/`tampa` city names). No data fix-up needed. This step is purely a verification.

- [ ] **Step B5.1: Confirm no master rows reference the old campaign slug**

```bash
grep -lR 'dental_sunbelt' outreach/campaigns/dentist_sunbelt/outputs 2>/dev/null
```

Expected: no output.

If matches appear, hand-inspect — they're likely benign (e.g. a stale comment in a sidecar). No code action; note in PR description.

---

### Task B6: Run the equivalence test + every other test

- [ ] **Step B6.1: Run all tests**

```bash
for t in $(find outreach/lib outreach/tests -name 'test_*.py' -o -name '*_tests.py' -o -name 'equivalence_test.py' 2>/dev/null); do
  echo "=== $t ==="
  python "$t" || echo "FAILED: $t"
done
```

Expected: every test passes. `equivalence_test.py` should now run `dentist_sunbelt` (not skip) and pass; the other 3 still skip.

- [ ] **Step B6.2: If green, no commit** — verification only.

---

## Phase C — Migrate remaining 3 campaigns

The pattern from Phase B repeats. Each campaign needs:
1. `git mv pipelines/<old> campaigns/<new>` for data folders.
2. New `campaign.yaml`.
3. New `overrides.py` if the old `config.py` carried regional chain lists / Ezly-style PAIN_WEIGHTS tweaks.
4. Delete the old `config.py`.
5. Equivalence-test, then field-diff master.json.

---

### Task C1: Migrate `software_ua` (with overrides + nested scripts/)

**Files:**
- Create: `outreach/campaigns/software_ua/campaign.yaml`
- Create: `outreach/campaigns/software_ua/overrides.py`
- Create: `outreach/campaigns/software_ua/README.md`
- Move: `outreach/pipelines/software_ua/{raw,enrichment,outputs,_archive}` → `outreach/campaigns/software_ua/`
- Move: the 4 custom scripts → `outreach/campaigns/software_ua/scripts/`
- Delete: `outreach/pipelines/software_ua/config.py`, `__init__.py`, `queries/` (empty)

- [ ] **Step C1.1: Make the campaign directory**

```bash
mkdir -p outreach/campaigns/software_ua/scripts
```

- [ ] **Step C1.2: Move data folders**

```bash
git mv outreach/pipelines/software_ua/raw         outreach/campaigns/software_ua/raw
git mv outreach/pipelines/software_ua/enrichment  outreach/campaigns/software_ua/enrichment
git mv outreach/pipelines/software_ua/outputs     outreach/campaigns/software_ua/outputs
git mv outreach/pipelines/software_ua/_archive    outreach/campaigns/software_ua/_archive
# queries/ is empty in software_ua (queries live elsewhere); skip if absent
git mv outreach/pipelines/software_ua/queries     outreach/campaigns/software_ua/queries 2>/dev/null || true
```

- [ ] **Step C1.3: Move the 4 custom scripts**

```bash
git mv outreach/pipelines/software_ua/build_classify_batches.py outreach/campaigns/software_ua/scripts/build_classify_batches.py
git mv outreach/pipelines/software_ua/build_enrich_queue.py     outreach/campaigns/software_ua/scripts/build_enrich_queue.py
git mv outreach/pipelines/software_ua/merge_batches.py          outreach/campaigns/software_ua/scripts/merge_batches.py
git mv outreach/pipelines/software_ua/retry_via_curl.py         outreach/campaigns/software_ua/scripts/retry_via_curl.py
```

- [ ] **Step C1.4: Update path strings in the moved scripts**

In each of the 4 files, replace the literal string:

```python
ROOT = Path("outreach/pipelines/software_ua")
```

with:

```python
ROOT = Path("outreach/campaigns/software_ua")
```

Sanity grep:

```bash
grep -nR --include='*.py' 'pipelines/software_ua' outreach 2>/dev/null
```

Expected: no output.

- [ ] **Step C1.5: Write `campaign.yaml`**

Create `outreach/campaigns/software_ua/campaign.yaml`:

```yaml
vertical: software
location: ua
slug: software_ua
display_name: Software UA
created: 2026-05-22
status: active
```

- [ ] **Step C1.6: Write `overrides.py`**

Create `outreach/campaigns/software_ua/overrides.py`:

```python
"""Software UA — campaign-specific overrides on top of verticals/software/config.py.

Adds regional UA outsourcer brand lists and ensures the
software vertical's defaults still apply elsewhere. Pain weighting
already matches Ezly's pitch in the vertical default; this file
only adds region-specific signal.

Honest fit note: Ezly's ICP is solo freelancers on Upwork/Fiverr.
This list is small/mid UA agencies. F1 will skew lower than
dental gold (~0.78) because B2B software reviews discuss
project-delivery pain, not response-speed pain.
"""
from __future__ import annotations

import re

# UA-based and adjacent enterprise outsourcers — never Ezly buyers
# (BD orgs, sales teams, procurement). Layered on top of the
# vertical's global big-IT regex (Accenture, IBM, etc.).
DSO_TITLE_REGEX_EXTRA = re.compile(
    r'\b('
    r'EPAM|GlobalLogic|SoftServe|Luxoft|Ciklum|N-?iX|Sigma Software|'
    r'Intellias|ELEKS|Miratech|Infopulse|DataArt|Daxx|Beetroot|'
    r'Astound Commerce|Edvantis|Symphony Solutions|Innovecs|Plexteq|'
    r'TEAM International|AltexSoft|Provectus|Devoteam|'
    r'Wipro|Infosys|TCS|Tata Consultancy|'
    r'Wix\.com|Grammarly|MacPaw|GitLab|JetBrains|Reply'
    r')\b', re.I,
)

DSO_EMAIL_DOMAINS_EXTRA = {
    'epam.com',
    'globallogic.com',
    'softserveinc.com',
    'luxoft.com',
    'ciklum.com',
    'n-ix.com',
    'sigma.software',
    'intellias.com',
    'eleks.com',
    'miratech.com',
    'infopulse.com',
    'dataart.com',
    'daxx.com',
    'beetroot.se',
    'astoundcommerce.com',
    'innovecs.com',
    'symphony-solutions.eu',
    'wipro.com',
    'infosys.com',
    'tcs.com',
    'wix.com',
    'grammarly.com',
    'macpaw.com',
    'gitlab.com',
    'jetbrains.com',
}
```

- [ ] **Step C1.7: Write README.md**

Create `outreach/campaigns/software_ua/README.md`:

```markdown
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
```

- [ ] **Step C1.8: Delete the old config.py + __init__.py**

```bash
git rm outreach/pipelines/software_ua/config.py
git rm outreach/pipelines/software_ua/__init__.py
rmdir outreach/pipelines/software_ua 2>/dev/null || true
```

- [ ] **Step C1.9: Equivalence test passes for `software_ua`**

```bash
python outreach/lib/equivalence_test.py
```

Expected: `dentist_sunbelt` and `software_ua` subTests pass; other 2 skip; result `OK`.

If `software_ua` fails: likely cause is the vertical's default `DSO_TITLE_REGEX` plus the override doesn't match the old config's regex on some sample. Inspect with:

```bash
python - <<'PY'
import sys; sys.path.insert(0,'outreach')
from lib.campaign_config import load_campaign
import importlib.util as u
s=u.spec_from_file_location('old','outreach/pipelines/software_ua/config.py')
m=u.module_from_spec(s); s.loader.exec_module(m)
new=load_campaign('software_ua')
old=m.DSO_TITLE_REGEX
import re
# Print the alternations from the old regex that the new misses:
for alt in re.findall(r'[A-Za-z][A-Za-z0-9. \-]+', old.pattern):
    alt=alt.strip()
    if 3<=len(alt)<=30 and old.search(alt) and not new.dso_title_regex.search(alt):
        print('MISSING:', alt)
PY
```

Add any missing tokens to vertical default or `DSO_TITLE_REGEX_EXTRA`.

- [ ] **Step C1.10: Smoke test analyze + diff master.json**

```bash
python outreach/lib/cli/analyze.py software_ua --output-date 2026-05-25-smoke --force
```

Then run the same diff script as Task B4.4 but pointed at `software_ua`. Expected: 0 missing/extra/diff.

```bash
rm -rf outreach/campaigns/software_ua/outputs/2026-05-25-smoke
```

- [ ] **Step C1.11: Commit**

```bash
git add -A outreach/campaigns/software_ua outreach/pipelines
git commit -m "refactor(outreach): migrate software_ua → campaigns/software_ua"
```

---

### Task C2: Migrate `cosmetic_surgeons_dallas`

**Files:**
- Create: `outreach/campaigns/cosmetic_surgeons_dallas/campaign.yaml`
- Create: `outreach/campaigns/cosmetic_surgeons_dallas/overrides.py` (carries the dermatology DSO list)
- Move: data folders
- Delete: old `config.py`, `__init__.py`

- [ ] **Step C2.1: Make the campaign directory**

```bash
mkdir -p outreach/campaigns/cosmetic_surgeons_dallas
```

- [ ] **Step C2.2: Move data folders**

```bash
git mv outreach/pipelines/cosmetic_surgeons_dallas/queries     outreach/campaigns/cosmetic_surgeons_dallas/queries 2>/dev/null || true
git mv outreach/pipelines/cosmetic_surgeons_dallas/raw         outreach/campaigns/cosmetic_surgeons_dallas/raw 2>/dev/null || true
git mv outreach/pipelines/cosmetic_surgeons_dallas/enrichment  outreach/campaigns/cosmetic_surgeons_dallas/enrichment 2>/dev/null || true
git mv outreach/pipelines/cosmetic_surgeons_dallas/outputs     outreach/campaigns/cosmetic_surgeons_dallas/outputs 2>/dev/null || true
```

- [ ] **Step C2.3: Write campaign.yaml**

Create `outreach/campaigns/cosmetic_surgeons_dallas/campaign.yaml`:

```yaml
vertical: cosmetic_surgery
location: dallas
slug: cosmetic_surgeons_dallas
display_name: Cosmetic Surgeons Dallas
created: 2026-05-02
status: exploratory
```

- [ ] **Step C2.4: Write overrides.py with the regional dermatology DSO list**

Create `outreach/campaigns/cosmetic_surgeons_dallas/overrides.py`:

```python
"""Cosmetic Surgeons Dallas — regional dermatology DSO overrides."""
from __future__ import annotations

import re

# Texas-heavy dermatology DSOs that the national list in
# verticals/cosmetic_surgery/config.py doesn't cover.
DSO_TITLE_REGEX_EXTRA = re.compile(
    r'\b('
    r'US Dermatology Partners|USDP|'
    r'Schweiger Dermatology|'
    r'Forefront Dermatology|'
    r'Pinnacle Dermatology|'
    r'Epiphany Dermatology|'
    r'Westlake Dermatology'
    r')\b', re.I,
)

DSO_EMAIL_DOMAINS_EXTRA = {
    'usdermatologypartners.com',
    'schweigerderm.com',
    'forefrontdermatology.com',
    'pinnacleskin.com',
    'epiphanydermatology.com',
    'westlakedermatology.com',
}
```

- [ ] **Step C2.5: Delete old config**

```bash
git rm outreach/pipelines/cosmetic_surgeons_dallas/config.py
git rm outreach/pipelines/cosmetic_surgeons_dallas/__init__.py
rmdir outreach/pipelines/cosmetic_surgeons_dallas 2>/dev/null || true
```

- [ ] **Step C2.6: Equivalence test + diff smoke-master if there are raw rows**

```bash
python outreach/lib/equivalence_test.py
```

Expected: 3 of 4 subTests pass (still excluding retail_toronto), result `OK`.

If `cosmetic_surgeons_dallas/raw/` is non-empty, run the analyze smoke + diff per Task B4.4. Otherwise note in PR description that the campaign has no data yet (this matches the original docstring "exploratory pipeline").

- [ ] **Step C2.7: Commit**

```bash
git add -A outreach/campaigns/cosmetic_surgeons_dallas outreach/pipelines
git commit -m "refactor(outreach): migrate cosmetic_surgeons_dallas"
```

---

### Task C3: Migrate `retail_toronto`

**Files:**
- Create: `outreach/campaigns/retail_toronto/campaign.yaml`
- Create: `outreach/campaigns/retail_toronto/overrides.py` (regional retail + mall lists)
- Move: data folders
- Delete: old `config.py`, `__init__.py`

- [ ] **Step C3.1: Make the campaign directory**

```bash
mkdir -p outreach/campaigns/retail_toronto
```

- [ ] **Step C3.2: Move data folders**

```bash
git mv outreach/pipelines/retail_toronto/queries     outreach/campaigns/retail_toronto/queries 2>/dev/null || true
git mv outreach/pipelines/retail_toronto/raw         outreach/campaigns/retail_toronto/raw 2>/dev/null || true
git mv outreach/pipelines/retail_toronto/enrichment  outreach/campaigns/retail_toronto/enrichment 2>/dev/null || true
git mv outreach/pipelines/retail_toronto/outputs     outreach/campaigns/retail_toronto/outputs 2>/dev/null || true
```

- [ ] **Step C3.3: Write campaign.yaml**

Create `outreach/campaigns/retail_toronto/campaign.yaml`:

```yaml
vertical: retail
location: toronto
slug: retail_toronto
display_name: Retail Toronto
created: 2026-05-07
status: exploratory
```

- [ ] **Step C3.4: Write overrides.py with Canadian retail + Toronto mall lists**

Create `outreach/campaigns/retail_toronto/overrides.py`:

```python
"""Retail Toronto — Canadian + GTA-specific chains and mall properties."""
from __future__ import annotations

import re

DSO_TITLE_REGEX_EXTRA = re.compile(
    r'(?:\b(?:'
    # Canadian national retail chains
    r'Canadian Tire|Hudson\'?s Bay|The Bay|Winners|HomeSense|Marshalls|'
    r'Home Depot|Lowe\'?s|RONA|'
    r'Dollarama|Dollar Tree|Dollar General|Giant Tiger|'
    r'Loblaws|No Frills|Real Canadian Superstore|Metro|Sobeys|FreshCo|Food Basics|'
    r'Shoppers Drug Mart|Rexall|Pharmasave|'
    r'Mark\'?s|Sport Chek|Atmosphere|'
    r'Arc\'?teryx|'
    r'Roots|Reitmans|Penningtons|Bluenotes|Garage|Suzy Shier|Le Château|'
    r'Aritzia|'
    r'Once Upon A Child|Plato\'?s Closet|Value Village|Salvation Army|'
    r'Stitches|Kith|CHANEL|Chanel|gravitypope|Fj.llr.ven|'
    r'Indigo|Chapters|Coles|The Source|'
    r'Leon\'?s|The Brick|Structube|EQ3|'
    r'Kitchen Stuff Plus|HomeSense|Pier 1|'
    r'Target|Nordstrom|Saks Fifth Avenue|Holt Renfrew|'
    # Toronto-area mall properties
    r'Yorkdale Shopping Centre|Yorkville Village|CF Toronto Eaton Centre|'
    r'CF Shops at Don Mills|Bayview Village|North York Centre|Designer Row|'
    r'Scarborough Town Centre|Sherway Gardens|Fairview Mall|Square One|'
    r'Eaton Centre|Pacific Mall'
    r')\b)'
    r'|(?:\bsize\?)',
    re.I,
)

DSO_EMAIL_DOMAINS_EXTRA = {
    'walmart.ca',
    'costco.ca',
    'canadiantire.ca',
    'thebay.com', 'hbc.com',
    'winners.ca', 'homesense.ca', 'marshalls.ca',
    'homedepot.ca', 'lowes.ca', 'rona.ca',
    'bestbuy.ca',
    'dollarama.com',
    'loblaws.ca', 'metro.ca', 'sobeys.com',
    'shoppersdrugmart.ca', 'rexall.ca',
    'arcteryx.com',
    'roots.com', 'reitmans.com',
    'sephora.ca',
    'indigo.ca', 'chapters.ca',
    'leons.ca', 'thebrick.com',
    'cadillacfairview.com',
    'oxfordproperties.com',
}
```

- [ ] **Step C3.5: Delete old config**

```bash
git rm outreach/pipelines/retail_toronto/config.py
git rm outreach/pipelines/retail_toronto/__init__.py
rmdir outreach/pipelines/retail_toronto 2>/dev/null || true
```

- [ ] **Step C3.6: Equivalence test + optional smoke**

```bash
python outreach/lib/equivalence_test.py
```

Expected: all 4 subTests pass, result `OK`.

If `retail_toronto/raw/` has data, run the analyze + diff per Task B4.4.

- [ ] **Step C3.7: Commit**

```bash
git add -A outreach/campaigns/retail_toronto outreach/pipelines
git commit -m "refactor(outreach): migrate retail_toronto"
```

---

### Task C4: Handle `insurance_sf` (empty campaign)

The current `outreach/pipelines/insurance_sf/` exists but contains no `config.py` and no `raw/`. Decision: delete.

**Files:**
- Delete: `outreach/pipelines/insurance_sf/`

- [ ] **Step C4.1: Confirm the dir is dead**

```bash
ls outreach/pipelines/insurance_sf/
```

If anything other than an empty `__init__.py` appears, surface to the user before deleting.

- [ ] **Step C4.2: Delete the dir**

```bash
git rm -rf outreach/pipelines/insurance_sf
```

- [ ] **Step C4.3: Commit**

```bash
git commit -m "chore(outreach): remove dead insurance_sf pipeline (no config, no data)"
```

---

### Task C5: Remove the now-empty `pipelines/` tree

- [ ] **Step C5.1: Check remaining contents**

```bash
find outreach/pipelines -type f 2>/dev/null
```

Expected: only `outreach/pipelines/__init__.py` (or nothing).

- [ ] **Step C5.2: Delete the leftover**

```bash
git rm -f outreach/pipelines/__init__.py 2>/dev/null || true
rmdir outreach/pipelines 2>/dev/null || true
```

- [ ] **Step C5.3: Verify pipelines/ is gone**

```bash
ls outreach/pipelines 2>&1 | head -2
```

Expected: `No such file or directory`.

- [ ] **Step C5.4: Run full test suite**

```bash
for t in $(find outreach/lib outreach/tests outreach/campaigns -name 'test_*.py' -o -name '*_tests.py' 2>/dev/null); do
  echo "=== $t ==="
  python "$t" || echo "FAILED: $t"
done
```

Expected: all tests pass. `equivalence_test.py` now SKIPs (pipelines/ removed — see its setUpClass).

- [ ] **Step C5.5: Commit**

```bash
git add -A outreach
git commit -m "chore(outreach): remove pipelines/ tree (fully migrated to campaigns/)"
```

---

### Task C6: Delete the empty `lib/scrapers/` stub

- [ ] **Step C6.1: Confirm it's empty**

```bash
ls -la outreach/lib/scrapers/
```

Expected: only `__init__.py` (empty file).

- [ ] **Step C6.2: Delete**

```bash
git rm -rf outreach/lib/scrapers
```

- [ ] **Step C6.3: Commit**

```bash
git commit -m "chore(outreach): remove empty lib/scrapers/ stub"
```

---

### Task C7: Delete the equivalence test (its gate role is done)

After Phase B+C the old `pipelines/` dir is gone, so `equivalence_test.py` only skips. Remove it.

- [ ] **Step C7.1: Delete the test**

```bash
git rm outreach/lib/equivalence_test.py
```

- [ ] **Step C7.2: Commit**

```bash
git commit -m "chore(outreach): remove Phase-A equivalence test (gate satisfied)"
```

---

## Phase D — Documentation + skill updates

---

### Task D1: Rewrite `outreach/CLAUDE.md`

**Files:**
- Modify: `outreach/CLAUDE.md`

- [ ] **Step D1.1: Replace the file contents**

Write `outreach/CLAUDE.md`:

```markdown
# Outreach pipeline — agent rules

Lead-generation pipeline. See `outreach/README.md` for architecture,
daily-driver commands, and how to add a campaign.

## Repo shape

- `lib/` — industry-agnostic code. No vertical knobs, no hardcoded
  category names. Includes `lib/cli/` (CLI entry points for every
  pipeline stage) and `lib/campaign_config.py` (the merging loader).
- `verticals/<v>/config.py` — vertical template: pain weights,
  service map, DSO regex for vertical-wide chains, enrich profile,
  OSINT templates. Identical across every campaign in that vertical.
- `verticals/<v>/query_templates.txt` — placeholder query lines
  expanded by `lib/render_queries.py`.
- `locations/<loc>.yaml` — pure location data: cities, area codes,
  geographic prefixes (city/neighborhood names), country, locale.
- `campaigns/<v>_<loc>/campaign.yaml` — names the vertical + location.
- `campaigns/<v>_<loc>/overrides.py` — OPTIONAL per-campaign tweaks:
  PAIN_WEIGHTS override, DSO_TITLE_REGEX_EXTRA for regional chains,
  etc.
- `campaigns/<v>_<loc>/raw/` — raw scrape NDJSONs. **Immutable.**
- `campaigns/<v>_<loc>/enrichment/` — append-only sidecars (crawl,
  pain_classifications, osint, owner_lookups).
- `campaigns/<v>_<loc>/outputs/<date>/` — one folder per delivery.
- `silverthread/pain_categories.md` — STL-derived pain hierarchy
  (vertical-agnostic) consumed by the pain-classifier subagent.

To add a campaign:

1. Pick or author a location: `outreach/locations/<loc>.yaml`.
2. Pick a vertical (or copy `verticals/dentist/` to create a new one).
3. Create `outreach/campaigns/<v>_<loc>/campaign.yaml`:
   ```yaml
   vertical: <v>
   location: <loc>
   slug: <v>_<loc>
   ```
4. Generate queries: `python outreach/lib/render_queries.py <v>_<loc>`
5. Drop raw scrape NDJSONs into `campaigns/<v>_<loc>/raw/`.
6. Run the pipeline:
   `python outreach/lib/cli/analyze.py <v>_<loc>` etc.

If the campaign needs a regional chain list or tweaked PAIN_WEIGHTS,
create `campaigns/<v>_<loc>/overrides.py` with the appropriate
`DSO_TITLE_REGEX_EXTRA` / `DSO_EMAIL_DOMAINS_EXTRA` / `PAIN_WEIGHTS`
attributes — the loader merges them on top of the vertical defaults.

## Rules

### 1. Never drop rows or field values

- Keep every row even if unreachable today. Channel mix changes;
  deletion is irreversible work loss. Deduping by canonical identity
  (`place_id`) is fine — same row, not row removal.
- Add fields, never replace. Bad values get a sibling flag with reason
  (`email_invalid: true`, `email_invalid_reason: "smtp_bounce_550"`),
  never stripped. Every added field carries provenance: `<field>_source`
  and `<field>_added_at`.
- "Filter" means subset view in a new file, never mutation of the
  master.
- Scope: raw scrapes, hand-curated decision files, append-only
  sidecars. Re-running the analyzer over recomputable ranked files is
  fine.

### 2. Persist scraper output to `gmapsdata/` or `campaigns/<name>/raw/`, never `/tmp`

`/tmp` is auto-cleaned by systemd-tmpfiles. Re-scraping is expensive
and may yield different data due to listing churn. The raw JSON is
the most valuable artifact in the pipeline.

### 3. Read both review fields from the gosom scraper

Gosom output has `user_reviews` (~10% of captured reviews) and
`user_reviews_extended` (the `-extra-reviews` payload, ~90%). Reading
only `user_reviews` drops most of the pain signal. Merge both and
dedupe by `(reviewer_name, description[:120])`.

### 4. Crawler parallelism uses a session pool, not round-robin

Use `queue.Queue` to lease browser sessions per task. See
`lib/enrichers/website_crawl.py`.

### 5. Validators guard at boundaries, not downstream

`lib/validators/` rejects known false-positive classes. New
false-positive class? Add a guard + test there, not downstream.

### 6. Chain detection: split vertical-wide vs region-specific

- Vertical-wide brands → `verticals/<v>/config.py:DSO_TITLE_REGEX`.
- Region-specific brands → `campaigns/<c>/overrides.py:DSO_TITLE_REGEX_EXTRA`.
- Vertical-generic descriptors ("family dental") →
  `verticals/<v>/config.py:GEOGRAPHIC_PREFIXES_GENERIC`.
- City/neighborhood names → `locations/<loc>.yaml`.

The loader unions all of the above; tests live in
`lib/campaign_config_tests.py`.

## Workflow

- TDD for new logic. Project TDD rules: `outreach/TDD-RULES.md`.
- Run tests before declaring done:
  ```bash
  for t in $(find outreach/lib outreach/tests -name 'test_*.py' -o -name '*_tests.py' 2>/dev/null); do python "$t"; done
  ```
```

- [ ] **Step D1.2: Commit**

```bash
git add outreach/CLAUDE.md
git commit -m "docs(outreach): rewrite CLAUDE.md for verticals/locations/campaigns layout"
```

---

### Task D2: Rewrite `outreach/README.md`

**Files:**
- Modify: `outreach/README.md`

- [ ] **Step D2.1: Read the current README to preserve any business context**

```bash
head -80 outreach/README.md
```

Identify any sections worth keeping verbatim (project intent, sales context, contacts).

- [ ] **Step D2.2: Rewrite README.md**

Update the top half (Architecture + Daily Drivers + Adding a Campaign sections). Keep any business-context blocks that don't reference paths. Critical path changes to apply throughout:

- `outreach/pipelines/<name>/` → `outreach/campaigns/<name>/`
- `outreach/scripts/<x>.py` → `outreach/lib/cli/<x>.py`
- `outreach/pipelines/<name>/config.py` → `outreach/verticals/<v>/config.py` (+ optional `outreach/campaigns/<name>/overrides.py`)
- "copy `pipelines/dental_sunbelt/`" → "create `campaigns/dentist_<loc>/campaign.yaml`"

Sample replacement block (insert in place of the architecture diagram and daily-driver section):

````markdown
## Architecture

```
outreach/
├── verticals/<v>/         vertical template — pain weights, services, enrich profile
├── locations/<loc>.yaml   pure location data — cities, area codes
├── campaigns/<v>_<loc>/   run instance — raw, enrichment, outputs, optional overrides
├── lib/                   industry-agnostic code
│   └── cli/               CLI entry points (analyze, enrich, validate, handoff, …)
├── silverthread/          STL reference (pain taxonomy, services)
└── docs/
```

## Daily drivers

| Stage     | Command |
|-----------|---------|
| analyze   | `python outreach/lib/cli/analyze.py <campaign>` |
| enrich    | `python outreach/lib/cli/enrich.py <campaign>` |
| classify  | dispatch pain-classifier subagent → `python outreach/lib/cli/merge_classifications.py …` |
| osint     | `python outreach/lib/cli/osint_enrich.py <campaign>` |
| validate  | `python outreach/lib/cli/validate.py <campaign>` |
| handoff   | `python outreach/lib/cli/handoff.py <campaign>` |
| push      | `python outreach/lib/cli/push_leads.py <campaign>` |

## Adding a campaign

```bash
# 1. Pick / author a location
$EDITOR outreach/locations/myloc.yaml

# 2. Pick a vertical (or copy verticals/dentist/ to bootstrap a new one)

# 3. Create the campaign
mkdir -p outreach/campaigns/dentist_myloc
cat > outreach/campaigns/dentist_myloc/campaign.yaml <<EOF
vertical: dentist
location: myloc
slug: dentist_myloc
EOF

# 4. (optional) overrides.py for regional chains / tuned weights

# 5. Generate queries
python outreach/lib/render_queries.py dentist_myloc

# 6. Drop raw NDJSONs into outreach/campaigns/dentist_myloc/raw/

# 7. Run the pipeline
python outreach/lib/cli/analyze.py dentist_myloc
```
````

- [ ] **Step D2.3: Sanity grep — no remaining `pipelines/` references**

```bash
grep -n 'pipelines/' outreach/README.md
```

Expected: no output.

- [ ] **Step D2.4: Commit**

```bash
git add outreach/README.md
git commit -m "docs(outreach): rewrite README for new layout"
```

---

### Task D3: Update `outreach/TODO.md`

**Files:**
- Modify: `outreach/TODO.md`

- [ ] **Step D3.1: Replace path references**

In `outreach/TODO.md`, replace any of:
- `outreach/pipelines/<x>/config.py` → `outreach/verticals/<v>/config.py`
- `outreach/scripts/<x>.py` → `outreach/lib/cli/<x>.py`
- `pipelines/<x>/` → `campaigns/<x>/`

Sanity grep:

```bash
grep -n 'pipelines/\|scripts/' outreach/TODO.md
```

Expected: only references that remain are inside historical context blocks that are explicitly framed as "before restructure".

- [ ] **Step D3.2: Commit**

```bash
git add outreach/TODO.md
git commit -m "docs(outreach): update TODO.md paths"
```

---

### Task D4: Update `.claude/skills/outreach/SKILL.md`

**Files:**
- Modify: `.claude/skills/outreach/SKILL.md`

- [ ] **Step D4.1: Replace path references throughout**

Run the same find-replace pattern as Task D3 on `.claude/skills/outreach/SKILL.md`. Specifically:
- All `outreach/scripts/*.py` references → `outreach/lib/cli/*.py`.
- All `outreach/pipelines/<name>/` references → `outreach/campaigns/<name>/`.
- The test-find command in any debugging section:
  ```bash
  for t in $(find outreach/lib outreach/tests -name 'test_*.py' -o -name '*_tests.py' 2>/dev/null); do python "$t"; done
  ```
- Any "copy `pipelines/dental_sunbelt/`" instructions → the new "create `campaigns/<v>_<l>/campaign.yaml`" flow from D1.

- [ ] **Step D4.2: Sanity grep**

```bash
grep -n 'outreach/scripts\|outreach/pipelines' .claude/skills/outreach/SKILL.md
```

Expected: no output.

- [ ] **Step D4.3: Commit**

```bash
git add .claude/skills/outreach/SKILL.md
git commit -m "docs(outreach): update skill SKILL.md for new layout"
```

---

### Task D5: Update `outreach/docs/architecture.md`

**Files:**
- Modify: `outreach/docs/architecture.md`

- [ ] **Step D5.1: Replace path references**

Same find-replace pattern as Task D3.

- [ ] **Step D5.2: Sanity grep**

```bash
grep -n 'outreach/scripts\|outreach/pipelines' outreach/docs/architecture.md
```

Expected: no output, OR remaining references are clearly historical (e.g. "previously the layout was …").

- [ ] **Step D5.3: Commit**

```bash
git add outreach/docs/architecture.md
git commit -m "docs(outreach): update architecture.md paths"
```

---

## Phase E — Final verification

---

### Task E1: Full test sweep

- [ ] **Step E1.1: Run every test in the new layout**

```bash
FAIL=0
for t in $(find outreach/lib outreach/tests -name 'test_*.py' -o -name '*_tests.py' 2>/dev/null); do
  echo "=== $t ==="
  python "$t" || { FAIL=1; echo "FAILED: $t"; }
done
echo "---"
echo "result: $([ $FAIL -eq 0 ] && echo PASS || echo FAIL)"
```

Expected: `result: PASS`.

- [ ] **Step E1.2: Run software_ua's custom scripts in dry-run mode**

Each of the 4 software_ua scripts should at least parse / import without crashing. The first runs that touch real data are guarded by file existence:

```bash
python -c "import importlib.util as u, sys; sys.path.insert(0,'outreach')
for f in [
  'outreach/campaigns/software_ua/scripts/build_classify_batches.py',
  'outreach/campaigns/software_ua/scripts/build_enrich_queue.py',
  'outreach/campaigns/software_ua/scripts/merge_batches.py',
  'outreach/campaigns/software_ua/scripts/retry_via_curl.py',
]:
  s=u.spec_from_file_location('m',f); m=u.module_from_spec(s); s.loader.exec_module(m); print('ok', f)"
```

Expected: 4 `ok` lines. Any `FileNotFoundError` on the data paths means the script was importing data at module load (look for `json.load(...)` at top level) — those scripts need to wrap top-level data reads in `if __name__ == '__main__':` or `main()`.

- [ ] **Step E1.3: Smoke-test render_queries against dentist_sunbelt**

```bash
python - <<'PY'
import sys; sys.path.insert(0, 'outreach')
from lib.campaign_config import load_campaign
from lib.render_queries import render_for_campaign
from pathlib import Path
import yaml

cfg = load_campaign('dentist_sunbelt')
loc = yaml.safe_load(open(f'outreach/locations/{cfg.location}.yaml'))
metros = [c['name'] for c in loc['cities']]
cities_state = {c['name']: c.get('state','') for c in loc['cities']}
neighborhoods = {c['name']: c.get('neighborhoods') or [] for c in loc['cities']}
cities_keyword = {c['name']: 'dentist' for c in loc['cities']}
templates = Path(f'outreach/verticals/{cfg.vertical}/query_templates.txt').read_text()

out_dir = Path('/tmp/render_smoke_dentist_sunbelt')
out_dir.mkdir(exist_ok=True)
render_for_campaign(
    templates,
    {'metros': metros, 'neighborhoods': neighborhoods,
     'cities_state': cities_state, 'cities_vertical_keyword': cities_keyword},
    out_dir,
    vertical_keyword='dentist',
)
for f in sorted(out_dir.glob('*.txt')):
    print(f.name, '->', len(f.read_text().splitlines()), 'lines')
PY
```

Expected: 3 files (austin/phoenix/tampa), each with a positive line count. If any city produces 0 lines, debug `render_for_campaign` against that city's neighborhoods.

- [ ] **Step E1.4: Diff-comparison vs existing hand-written queries**

```bash
diff <(sort /tmp/render_smoke_dentist_sunbelt/austin.txt) \
     <(sort outreach/campaigns/dentist_sunbelt/queries/austin.txt)
```

Expected: minimal diff (formatting differences acceptable; the substantive lines should appear in both). If lines are missing from the rendered output, expand the dentist `query_templates.txt` or the sunbelt neighborhoods list. This is iterative — note in PR description what was tuned.

- [ ] **Step E1.5: No commit — verification only**

---

### Task E2: Sanity-grep for stragglers

- [ ] **Step E2.1: No code references `outreach/scripts/` or `outreach/pipelines/`**

```bash
grep -nR --include='*.py' 'outreach/scripts\|outreach/pipelines\|from scripts\|import scripts' outreach 2>/dev/null
```

Expected: no output.

- [ ] **Step E2.2: No docs reference the old paths**

```bash
grep -nR --include='*.md' 'outreach/scripts/\|outreach/pipelines/' outreach .claude/skills/outreach 2>/dev/null
```

Expected: no output, OR remaining lines are in `outreach/docs/2026-05-07-osint-enrichment-*.md` (historical design docs — leave alone).

- [ ] **Step E2.3: `pipelines/` and `scripts/` directories do not exist**

```bash
ls outreach/pipelines outreach/scripts 2>&1
```

Expected: both report `No such file or directory`.

- [ ] **Step E2.4: No commit — verification only**

---

### Task E3: Open the PR

- [ ] **Step E3.1: Push the branch**

```bash
git push -u origin feat/osint-enrichment
```

(Assuming this work is on the same branch; if a new branch was used, substitute its name.)

- [ ] **Step E3.2: Create the PR with `gh`**

```bash
gh pr create --title "refactor(outreach): decompose pipelines/ into verticals/locations/campaigns" \
  --body "$(cat <<'EOF'
## Summary

Splits the monolithic `outreach/pipelines/<vertical>_<location>/` layout into three concerns:

- `verticals/<v>/` — shared template per vertical (pain weights, services, enrich profile, vertical-wide DSO regex, OSINT templates)
- `locations/<loc>.yaml` — pure location data (cities, area codes, neighborhoods)
- `campaigns/<v>_<loc>/` — run instance (raw, enrichment, outputs, optional `overrides.py` for regional tweaks)

Also collapses `outreach/scripts/` into `outreach/lib/cli/` so there is one home for shared code.

A new `lib/campaign_config.py` merges vertical + location + overrides at runtime into a `CampaignConfig` dataclass that CLI scripts consume in place of the old `pipelines/<name>/config.py` modules. The migration is field-level identical — verified by running `analyze.py` against existing raw NDJSONs and diffing master.json before/after (0 diffs).

## Test plan

- [ ] `for t in $(find outreach/lib outreach/tests -name 'test_*.py' -o -name '*_tests.py'); do python "$t"; done` → all green
- [ ] Smoke-test the migrated `dentist_sunbelt` end-to-end: analyze → master.json diff against previous output → 0 field diffs on `(quality_score, tier, is_chain_or_dso, chain_reason, metro, pain_breadth)`
- [ ] Smoke-test `software_ua` analyze + diff → 0 field diffs
- [ ] Render queries via new `lib/render_queries.py` → diff vs hand-written queries acceptable
- [ ] `gh pr checks` → CI green
EOF
)" --draft
```

Expected: PR URL printed.

- [ ] **Step E3.3: Verify the PR is in draft state**

```bash
gh pr view --json isDraft -q .isDraft
```

Expected: `true`.

---

## Self-Review

**Spec coverage:** every section of the original audit is implemented by a task:
- Pipeline configs (5 files): split across Tasks A8–A11 (locations), A12, A14, A16, A17 (verticals), C1–C4 (campaign overrides).
- `outreach/scripts/*.py` (12 files): Task B2 (`git mv`), B3 (imports).
- `outreach/lib/*.py` audit: confirmed by the absence of moves — only `lib/scrapers/` deleted (Task C6).
- `software_ua/*` custom scripts: Task C1 moves them as-is with path string update.
- Data folders: Task B4 (dentist_sunbelt), Task C1–C3 (others).
- `silverthread/`: explicitly NOT moved (preserved as vertical-agnostic reference).
- `CLAUDE.md`, `README.md`, `TODO.md`, skill SKILL.md, architecture.md: Tasks D1–D5.
- Migration ordering (Phase A → B → C → D → E): enforced by task numbering.
- Two open decisions (overrides.py format, CLI arg name): resolved up front in the header.
- Concrete schema examples: present in the architecture section and Task B1 / Task C1.

**Placeholder scan:** no TODO/TBD/"implement later"/"similar to Task N"/"add validation" strings present. Every step contains actual code, an actual command, or an actual edit instruction with explicit before/after.

**Type consistency check:** field names on `CampaignConfig` (`pain_weights`, `service_map`, `dso_title_regex`, `dso_email_domains`, `geographic_prefixes`, `metros`, `metro_area_codes`, `enrich_profile`, `vendor_domains_extra`, `independent_filters`, `osint_*`) appear identically in:
- the dataclass definition (Task A1)
- the merge function (Task A6)
- the `require_attr` mapping in `_common.py` (Task B3.1)
- the equivalence test assertions (Task A18)
- the consumer rewrites in `push_leads.py`, `analyze.py`, `push_campaign.py` (Task B3.4)

Method/helper names are consistent: `_read_campaign_yaml`, `_read_location_yaml`, `_load_python_module`, `_load_python_module_optional`, `_concat_regex`, `_union_sets`, `_overlay_dict`, `_merge`, `load_campaign`, `render_for_campaign` are each defined once and referenced by the same name everywhere.

---

## Execution Handoff

Plan complete and saved to `outreach/docs/2026-05-25-restructure-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration. Uses `superpowers:subagent-driven-development`.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?
