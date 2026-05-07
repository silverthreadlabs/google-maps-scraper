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
    """Production-time fetch wiring. Tests should patch
    `scripts.osint_enrich.run_serp_query_with_fallback` directly so the
    returned callable is never invoked in tests. The orchestrator's CLI
    hooks it up to the agent-browser session pool (Task 17)."""
    def fetch_fn(url: str) -> str | None:
        raise NotImplementedError(
            'serp fetch fn not wired — tests must patch run_serp_query_with_fallback'
        )
    return fetch_fn
