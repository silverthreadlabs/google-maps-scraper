"""Deep-site crawl for OSINT enrichment.

Extends website_crawl.py with /about, /team, /leadership, /contact
fetches plus JSON-LD/schema.org parsing. Returns POC candidates and
email candidates with provenance hooks the orchestrator wires up.
"""
from __future__ import annotations

import json
import re
from typing import Iterable
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from lib.validators.poc import validate_poc

_JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)

_HEADING_PATTERNS = re.compile(
    r'^(?:meet|about|contact|why)\s+((?:dr\.?\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})',
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')


# ---------------------------------------------------------------------------
# JSON-LD extraction
# ---------------------------------------------------------------------------

def extract_jsonld_persons(html: str) -> list[dict]:
    """Walk JSON-LD blocks; emit one dict per Person we find.

    Keys: name (str|None), role (str|None), email (str|None), source (str).
    `source` is always 'deep_site_crawl_jsonld'.
    """
    persons: list[dict] = []
    for block in _JSONLD_RE.findall(html):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        for node in _walk_jsonld(data):
            if not isinstance(node, dict):
                continue
            t = node.get('@type')
            is_person = t == 'Person' or (isinstance(t, list) and 'Person' in t)
            if is_person:
                persons.append({
                    'name': node.get('name'),
                    'role': node.get('jobTitle') or node.get('role'),
                    'email': node.get('email'),
                    'source': 'deep_site_crawl_jsonld',
                })
    seen: set[tuple] = set()
    out: list[dict] = []
    for p in persons:
        key = (p.get('name'), p.get('email'))
        if key in seen or key == (None, None):
            continue
        seen.add(key)
        out.append(p)
    return out


def _walk_jsonld(node) -> Iterable:
    """Recursively yield every dict / list element under a JSON-LD root."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk_jsonld(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_jsonld(v)


# ---------------------------------------------------------------------------
# Heading-proximity extraction
# ---------------------------------------------------------------------------

def extract_heading_proximity_persons(html: str) -> list[dict]:
    """Find <h*> headings naming a person (Dr.|Meet|About|Contact patterns),
    capture role + email from the same section."""
    soup = BeautifulSoup(html, 'html.parser')
    persons: list[dict] = []
    for heading in soup.find_all(re.compile(r'^h[1-6]$')):
        text = heading.get_text(strip=True)
        m = _HEADING_PATTERNS.match(text)
        if not m:
            continue
        name_candidate = m.group(1)
        section = heading.find_parent(['section', 'div', 'article']) or heading.parent
        section_text = section.get_text(' ', strip=True) if section else ''
        emails = _EMAIL_RE.findall(section_text)
        role = None
        sib = heading.find_next_sibling()
        if sib:
            role_text = sib.get_text(strip=True)
            if 0 < len(role_text) <= 60:
                role = role_text
        if not _is_valid_name(name_candidate):
            continue
        persons.append({
            'name': name_candidate.strip(),
            'role': role,
            'email': emails[0] if emails else None,
            'source': 'deep_site_crawl_heading',
        })
    seen: set[tuple] = set()
    out: list[dict] = []
    for p in persons:
        key = (p['name'], p.get('email'))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _is_valid_name(candidate: str) -> bool:
    """Delegate to poc_validator.validate_poc which takes a single name string."""
    valid, _ = validate_poc(candidate)
    return valid


# ---------------------------------------------------------------------------
# Fetch-path planning
# ---------------------------------------------------------------------------

def plan_fetch_paths(domain: str, paths: list[str], already_crawled: set[str]) -> list[str]:
    """Return absolute URLs to fetch; skip any whose normalized form is in
    `already_crawled` (typically loaded from website_crawl.json)."""
    normalized_done = {_norm_url(u) for u in already_crawled}
    out: list[str] = []
    for p in paths:
        url = f'https://{domain}{p}'
        if _norm_url(url) in normalized_done:
            continue
        out.append(url)
    return out


def _norm_url(url: str) -> str:
    """Lower-case host, drop scheme, strip trailing slash."""
    p = urlparse(url if '://' in url else f'http://{url}')
    host = p.netloc.lower()
    path = p.path.rstrip('/').lower()
    return f'{host}{path}'


# ---------------------------------------------------------------------------
# Top-level driver
# ---------------------------------------------------------------------------

def fetch_url(url: str) -> str | None:
    """Fetch a URL via agent-browser (reuses website_crawl's session pool
    pattern). Returns HTML or None on 4xx/5xx/error.

    The orchestrator passes a session-leasing callable; this default
    is overridden in production. Tests monkey-patch this function.
    """
    raise NotImplementedError(
        'fetch_url is provided by the orchestrator; tests must monkey-patch'
    )


def crawl_domain(
    domain: str,
    paths: list[str],
    already_crawled: set[str],
) -> dict:
    """Fetch each planned path, aggregate persons + emails across pages."""
    plan = plan_fetch_paths(domain, paths, already_crawled)
    persons: list[dict] = []
    pages_attempted = 0
    pages_with_data = 0
    for url in plan:
        pages_attempted += 1
        html = fetch_url(url)
        if not html:
            continue
        page_persons = extract_jsonld_persons(html) + extract_heading_proximity_persons(html)
        if page_persons:
            pages_with_data += 1
        for p in page_persons:
            p = {**p, 'source_url': url}
            persons.append(p)
    return {
        'persons': _dedupe_persons(persons),
        'pages_attempted': pages_attempted,
        'pages_with_data': pages_with_data,
    }


def _dedupe_persons(persons: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for p in persons:
        key = (p.get('name'), p.get('email'))
        if key in seen or key == (None, None):
            continue
        seen.add(key)
        out.append(p)
    return out
