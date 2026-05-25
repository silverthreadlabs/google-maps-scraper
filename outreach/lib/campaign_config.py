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

import yaml

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


def load_campaign(campaign_slug: str) -> CampaignConfig:
    """Load + merge the three config sources for `campaign_slug`.

    Caller passes the slug (directory name under campaigns/), e.g.
    'dentist_sunbelt'. Returns a fully-merged CampaignConfig.
    """
    raise NotImplementedError('filled in by subsequent tasks')
