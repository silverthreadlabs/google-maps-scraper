"""Canonical resolution of lead fields from the real gosom/master schema.

The OSINT SERP templates (`{business_name}`, `{city}`), the osint-binder
input context, and the handoff contact logic all need a business name, a
city, and a known POC name. The master schema does **not** store those under
those literal keys — they live under `title`, `metro`/`address`, and
`owner_name`/`pocs[]`. Reading the literal keys yields empty strings on every
real lead (0/326), which silently malforms SERP queries and skips the POC
LinkedIn search.

Centralizing the mapping here means every read-site agrees (DRY, per
CLAUDE.md) and a future schema change is a single edit with one test file.
All resolvers are pure, tolerate missing/None/blank values, and never raise.
"""
from __future__ import annotations

import re

# A comma-part that looks like a US "<ST> <ZIP>" tail, e.g. "TX 75235" or
# "TX 75232-1725". Used to locate the city as the part immediately before it.
_STATE_ZIP_RE = re.compile(r'^[A-Za-z]{2}\s+\d{5}(?:-\d{4})?$')


def resolve_business_name(lead: dict) -> str:
    """Business name for searches/handoff: `business_name`, else `title`."""
    for key in ('business_name', 'title'):
        value = (lead.get(key) or '').strip()
        if value:
            return value
    return ''


def resolve_city(lead: dict) -> str:
    """City for searches: explicit `city`, else parsed from `address`, else a
    humanized `metro` slug. Address parsing returns the true municipality
    (e.g. Terrell), which beats the metro slug for disambiguation."""
    explicit = (lead.get('city') or '').strip()
    if explicit:
        return explicit
    from_address = _city_from_address(lead.get('address'))
    if from_address:
        return from_address
    return _humanize_metro(lead.get('metro'))


def _city_from_address(address: str | None) -> str:
    """Extract the city from a '<street>, <city>, <ST ZIP>, <country>' string.
    Anchors on the state+ZIP part; falls back to the second comma-part (which
    covers most international formats where the postal code isn't a US ZIP)."""
    if not address:
        return ''
    parts = [p.strip() for p in address.split(',') if p.strip()]
    for i, part in enumerate(parts):
        if i >= 1 and _STATE_ZIP_RE.match(part):
            return parts[i - 1]
    return parts[1] if len(parts) >= 2 else ''


def _humanize_metro(metro: str | None) -> str:
    """Turn a metro slug into a search-friendly city ('san_francisco' →
    'San Francisco'). A weak last resort — prefer address parsing."""
    if not metro:
        return ''
    return metro.replace('_', ' ').replace('-', ' ').strip().title()


def resolve_poc_name(lead: dict) -> str:
    """Known POC name: explicit `poc_name`, else `owner_name`, else the primary
    POC in `pocs[]` (decision_makers moves the primary to index 0 and flags
    it), else the first named POC. Empty string when no name is known."""
    for key in ('poc_name', 'owner_name'):
        value = (lead.get(key) or '').strip()
        if value:
            return value
    pocs = lead.get('pocs') or []
    primary = next(
        (p for p in pocs
         if isinstance(p, dict) and p.get('primary') and (p.get('name') or '').strip()),
        None,
    )
    if primary:
        return primary['name'].strip()
    for p in pocs:
        if isinstance(p, dict) and (p.get('name') or '').strip():
            return p['name'].strip()
    return ''
