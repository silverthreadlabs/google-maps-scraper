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

import importlib.util

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
    locale: str = ''
    country: str = ''

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
        return re.compile(r'(?!)')
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
        locale=location.get('locale', ''),
        country=location.get('country', ''),

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
        osint_fields_desired=list(dict.fromkeys(
            list(getattr(vertical, 'OSINT_FIELDS_DESIRED', []))
            + (list(getattr(o, 'OSINT_FIELDS_DESIRED', []) or []) if o else [])
        )),
        osint_confidence_threshold=float(
            getattr(vertical, 'OSINT_CONFIDENCE_THRESHOLD', 0.85)
        ),
        osint_handoff_fields=list(getattr(vertical, 'OSINT_HANDOFF_FIELDS', [])),
        osint_serp_queries=_overlay_dict(
            getattr(vertical, 'OSINT_SERP_QUERIES', {}),
            getattr(o, 'OSINT_SERP_QUERIES', None) if o else None,
        ),
        osint_deep_crawl_paths=list(
            getattr(vertical, 'OSINT_DEEP_CRAWL_PATHS', [])
        ),
        osint_industry_terms=list(dict.fromkeys(
            list(getattr(vertical, 'OSINT_INDUSTRY_TERMS', []))
            + (list(getattr(o, 'OSINT_INDUSTRY_TERMS', []) or []) if o else [])
        )),
    )
