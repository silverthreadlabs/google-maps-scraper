"""Run OSINT enrichment for a pipeline.

Inspects each lead's gaps against `OSINT_FIELDS_DESIRED`, runs
enrichers (whois → deep_site_crawl → serp) in two waves, batches
binding judgments through the `osint-binder` subagent, writes
`enrichment/osint/<date>.json`.

Resumable: leads already in the sidecar are skipped.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.enrichers.whois_lookup import lookup_domain
from lib.enrichers.deep_site_crawl import crawl_domain
from lib.enrichers.serp import run_serp_query_with_fallback


def detect_gaps(lead: dict, fields_desired: list[str]) -> list[str]:
    """Return the subset of `fields_desired` that are missing/empty on `lead`.
    Treats None, empty string, and empty list/dict as missing."""
    gaps: list[str] = []
    for f in fields_desired:
        v = lead.get(f)
        if v is None or v == '' or v == [] or v == {}:
            gaps.append(f)
    return gaps


def _new_field_record() -> dict:
    return {
        'candidates': [],
        'selected_index': None,
        'selected_confidence': None,
        'skipped_reason': None,
    }


def _new_candidate(value, source, *, query=None, snippet=None) -> dict:
    return {
        'value': value, 'source': source,
        'query': query, 'snippet': snippet,
        'judge_verdict': None, 'judge_confidence': None, 'judge_reasoning': None,
    }


def _domain_from_website(url: str | None) -> str | None:
    if not url:
        return None
    p = urlparse(url if '://' in url else f'http://{url}')
    return p.netloc.lower() or None


def enrich_lead(lead: dict, cfg, already_crawled: set[str]) -> dict:
    """Run two-wave enrichment for a single lead. Returns sidecar record."""
    fields_desired = list(getattr(cfg, 'OSINT_FIELDS_DESIRED', []))
    sources = set(getattr(cfg, 'OSINT_SOURCES', []))
    industry_terms = getattr(cfg, 'OSINT_INDUSTRY_TERMS', [])
    serp_queries = getattr(cfg, 'OSINT_SERP_QUERIES', {})
    deep_paths = getattr(cfg, 'OSINT_DEEP_CRAWL_PATHS', [])

    record = {
        'place_id': lead.get('place_id'),
        'domain': lead.get('domain') or _domain_from_website(lead.get('website')),
        'enriched_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'fields': {f: _new_field_record() for f in fields_desired},
        'errors': [],
    }

    gaps = detect_gaps(lead, fields_desired)
    if not gaps:
        return record

    # Wave 1: discovery
    discovered_poc_name = lead.get('poc_name')

    if 'whois' in sources and record['domain']:
        try:
            w = lookup_domain(record['domain'])
            if w['status'] == 'ok':
                if 'poc_name' in gaps and w['registrant_name']:
                    record['fields']['poc_name']['candidates'].append(
                        _new_candidate(w['registrant_name'], 'whois'))
                if 'poc_email' in gaps and w['registrant_email']:
                    record['fields']['poc_email']['candidates'].append(
                        _new_candidate(w['registrant_email'], 'whois'))
                discovered_poc_name = discovered_poc_name or w['registrant_name']
        except Exception as e:
            record['errors'].append(f'whois: {e!r}')

    if 'deep_site_crawl' in sources and record['domain']:
        try:
            d = crawl_domain(record['domain'], deep_paths, already_crawled)
            for p in d['persons']:
                src = p.get('source', 'deep_site_crawl')
                if 'poc_name' in gaps and p.get('name'):
                    record['fields']['poc_name']['candidates'].append(
                        _new_candidate(p['name'], src))
                if 'poc_email' in gaps and p.get('email'):
                    record['fields']['poc_email']['candidates'].append(
                        _new_candidate(p['email'], src))
                if 'poc_role' in gaps and p.get('role'):
                    record['fields']['poc_role']['candidates'].append(
                        _new_candidate(p['role'], src))
                discovered_poc_name = discovered_poc_name or p.get('name')
        except Exception as e:
            record['errors'].append(f'deep_site_crawl: {e!r}')

    # Wave 2: SERP
    if 'serp' in sources:
        for field, template in serp_queries.items():
            if field not in gaps:
                continue
            if '{poc_name}' in template and not discovered_poc_name:
                record['fields'][field]['skipped_reason'] = 'no_poc_name_known'
                continue
            query = template.format(
                poc_name=discovered_poc_name or '',
                city=lead.get('city', ''),
                business_name=lead.get('business_name', ''),
                industry_term=industry_terms[0] if industry_terms else '',
            )
            try:
                serp = run_serp_query_with_fallback(query, fetch_fn=_serp_fetch_fn(cfg))
                if serp['status'] == 'blocked':
                    record['fields'][field]['skipped_reason'] = 'serp_blocked'
                    continue
                for r in serp['results'][:10]:
                    record['fields'][field]['candidates'].append(
                        _new_candidate(r['url'], f'serp_{serp["engine"]}',
                                       query=query, snippet=r.get('snippet', '')))
                if not record['fields'][field]['candidates']:
                    record['fields'][field]['skipped_reason'] = 'no_results'
            except Exception as e:
                record['errors'].append(f'serp[{field}]: {e!r}')

    return record


def _serp_fetch_fn(cfg):
    """Return a fetch_fn(url)->html|None backed by the website_crawl pool.

    SERP serializes per engine — only one Chromium session at a time hits
    duckduckgo / bing / google to avoid burst-shaped captcha triggers
    (CLAUDE.md rule 4: session pool, not round-robin).

    Tests should patch `scripts.osint_enrich.run_serp_query_with_fallback`
    directly so the returned callable is never invoked in tests.
    """
    from lib.enrichers.website_crawl import lease_single_session

    def fetch_fn(url: str) -> str | None:
        with lease_single_session(session_prefix='osint-serp') as session:
            try:
                return session.fetch(url, wait='networkidle', jitter=(2.0, 5.0))
            except Exception:
                return None
    return fetch_fn


def wire_deep_site_fetch(cfg) -> None:
    """Monkey-patch `lib.enrichers.deep_site_crawl.fetch_url` with a
    pool-backed implementation. Called by `main()` before processing leads."""
    from lib.enrichers import deep_site_crawl
    from lib.enrichers.website_crawl import lease_single_session

    def fetch(url: str) -> str | None:
        with lease_single_session(session_prefix='osint-deep') as session:
            try:
                return session.fetch(url, wait='networkidle', jitter=(0.5, 2.0))
            except Exception:
                return None

    deep_site_crawl.fetch_url = fetch


import json


def load_processed_place_ids(sidecar_path: Path) -> set[str]:
    if not sidecar_path.exists():
        return set()
    try:
        data = json.loads(sidecar_path.read_text())
    except json.JSONDecodeError:
        return set()
    return {r['place_id'] for r in data if r.get('place_id')}


def append_sidecar_record(sidecar_path: Path, record: dict) -> None:
    """Atomic append: read full file, append, write tmp, rename."""
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    if sidecar_path.exists():
        try:
            existing = json.loads(sidecar_path.read_text())
        except json.JSONDecodeError:
            existing = []
    else:
        existing = []
    existing.append(record)
    tmp = sidecar_path.with_suffix(sidecar_path.suffix + '.tmp')
    tmp.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    tmp.replace(sidecar_path)
