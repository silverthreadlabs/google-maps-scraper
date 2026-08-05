"""Shared POC / channel helpers for the people-enrichment stages.

The unified `decision-makers` stage (and its deprecated `owner-lookup` /
`contacts` aliases) all speak the same `pocs[]` shape:

    {name, role, email, socials: [url, ...], url, confidence, primary,
     source, added_at}

`socials` is a flat, reach-priority-ordered list (LinkedIn first) holding
every platform we can reach the person on; `email` is kept separate. These
helpers collect channels off a researched-person dict, normalize identity for
deduping, designate the primary decision-maker, project the owner scalars off
that primary, and merge re-found people (augment-never-drop, CLAUDE.md rule 1).
"""
from __future__ import annotations

import re

# Channel keys on a researched-person dict, collected into the POC's flat
# `socials` list in reach-priority order. Email is its own field, not a social.
CHANNEL_KEYS = ('linkedin', 'twitter', 'x', 'instagram', 'facebook')

# Roles that mark someone as the primary decision-maker / ICP buyer when no
# explicit `primary: true` flag is present.
_PRIMARY_ROLE_RE = re.compile(
    r'\b(founder|co-?founder|owner|ceo|chief\s+executive|'
    r'managing\s+(director|partner)|principal|proprietor)\b',
    re.IGNORECASE,
)


def norm_name(s: str | None) -> str:
    return ' '.join((s or '').lower().split())


def norm_url(u: str | None) -> str:
    u = (u or '').strip().lower().rstrip('/')
    for p in ('https://', 'http://', 'www.'):
        u = u.replace(p, '')
    return u


def channels_from_person(person: dict) -> list[str]:
    """Collect every channel URL off a person dict into a deduped, ordered
    list (CHANNEL_KEYS first, then any freeform `socials`)."""
    out: list[str] = []
    for key in CHANNEL_KEYS:
        v = (person.get(key) or '').strip()
        if v and v not in out:
            out.append(v)
    for v in person.get('socials') or []:
        v = (v or '').strip()
        if v and v not in out:
            out.append(v)
    return out


def _coerce_confidence(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def poc_from_person(person: dict, *, source: str, now_iso: str) -> dict:
    """Build a `pocs[]` entry from a researched-person dict. Accepts either
    `role` or (owner-style) `title`."""
    return {
        'name': (person.get('name') or '').strip(),
        'role': person.get('role') or person.get('title') or None,
        'email': (person.get('email') or '').strip() or None,
        'socials': channels_from_person(person),
        'url': person.get('url') or None,
        'confidence': _coerce_confidence(person.get('confidence')),
        'primary': bool(person.get('primary')),
        'source': source,
        'added_at': now_iso,
    }


def is_primary_role(role: str | None) -> bool:
    return bool(role) and bool(_PRIMARY_ROLE_RE.search(role))


def pick_primary_index(pocs: list[dict]) -> int | None:
    """Designate the primary decision-maker:
    explicit `primary: true` -> first role-keyword match -> first POC."""
    if not pocs:
        return None
    for i, p in enumerate(pocs):
        if p.get('primary'):
            return i
    for i, p in enumerate(pocs):
        if is_primary_role(p.get('role')):
            return i
    return 0


def _first_linkedin(socials: list[str] | None) -> str:
    for s in socials or []:
        if 'linkedin.com' in s.lower():
            return s
    return ''


def owner_scalars_from_poc(poc: dict) -> dict:
    """Project a primary POC down to the owner_* scalar mirror."""
    return {
        'name': poc.get('name') or '',
        'title': poc.get('role') or '',
        'linkedin': _first_linkedin(poc.get('socials')),
    }


def find_matching_poc(poc: dict, pocs: list[dict]) -> dict | None:
    """Return an existing POC that is the same person as `poc` (by normalized
    name, or by a shared LinkedIn URL), else None."""
    nkey = norm_name(poc.get('name'))
    li_keys = {norm_url(s) for s in (poc.get('socials') or []) if 'linkedin.com' in s.lower()}
    for existing in pocs:
        if nkey and norm_name(existing.get('name')) == nkey:
            return existing
        for s in existing.get('socials') or []:
            if 'linkedin.com' in s.lower() and norm_url(s) in li_keys:
                return existing
    return None


def union_pocs(existing: list[dict] | None, incoming: list[dict] | None) -> list[dict]:
    """Merge `incoming` POCs into `existing` without dropping anyone
    (CLAUDE.md rule 1). Re-found people have their channels merged in place;
    genuinely new people are appended. Returns the merged list."""
    merged = [dict(p) for p in (existing or []) if isinstance(p, dict)]
    for inc in incoming or []:
        if not isinstance(inc, dict):
            continue
        match = find_matching_poc(inc, merged)
        if match is None:
            merged.append(dict(inc))
        else:
            merge_channels_into_poc(match, inc)
    return merged


def merge_channels_into_poc(existing: dict, incoming: dict) -> None:
    """Augment `existing` POC in place with anything new on `incoming`
    (CLAUDE.md rule 1 — never drop). Adds missing socials, fills empty
    email/url/role, ORs the primary flag, keeps the higher confidence."""
    socials = list(existing.get('socials') or [])
    for s in incoming.get('socials') or []:
        if s and s not in socials:
            socials.append(s)
    existing['socials'] = socials
    for field in ('email', 'url', 'role'):
        if not existing.get(field) and incoming.get(field):
            existing[field] = incoming[field]
    if incoming.get('primary'):
        existing['primary'] = True
    ec, ic = existing.get('confidence'), incoming.get('confidence')
    if ic is not None and (ec is None or ic > ec):
        existing['confidence'] = ic
