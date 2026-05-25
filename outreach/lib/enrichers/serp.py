"""SERP enricher for OSINT.

Fetches search-engine results pages via agent-browser; never visits
the URLs the SERP returns directly. Engine fallback: DDG → Bing →
Google. Per CLAUDE.md rule 4, the orchestrator's session pool drives
the actual fetches; this module contains the parsers and the
fallback ladder.
"""
from __future__ import annotations

from bs4 import BeautifulSoup
from urllib.parse import quote_plus


def parse_google_results(html: str) -> list[dict]:
    """Parse Google SERP HTML into [{url, title, snippet}].
    Resilient to minor markup changes; relies on `<div class="g">` and
    `<div class="VwiC3b">` (current as of 2026-05). If Google changes
    the markup, update both the locator and the test fixture in lockstep.
    """
    soup = BeautifulSoup(html, 'html.parser')
    out: list[dict] = []
    for g in soup.select('div.g'):
        a = g.find('a', href=True)
        if not a:
            continue
        url = a['href']
        title_el = g.find('h3')
        snippet_el = g.select_one('div.VwiC3b')
        out.append({
            'url': url,
            'title': title_el.get_text(strip=True) if title_el else '',
            'snippet': snippet_el.get_text(' ', strip=True) if snippet_el else '',
        })
    return out


def parse_bing_results(html: str) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    out: list[dict] = []
    for li in soup.select('li.b_algo'):
        a = li.find('a', href=True)
        if not a:
            continue
        snippet_el = li.find('p')
        out.append({
            'url': a['href'],
            'title': a.get_text(strip=True),
            'snippet': snippet_el.get_text(' ', strip=True) if snippet_el else '',
        })
    return out


def parse_ddg_results(html: str) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    out: list[dict] = []
    for r in soup.select('div.result'):
        a = r.select_one('a.result__a')
        snippet_el = r.select_one('a.result__snippet, .result__snippet')
        if not a or 'href' not in a.attrs:
            continue
        out.append({
            'url': a['href'],
            'title': a.get_text(strip=True),
            'snippet': snippet_el.get_text(' ', strip=True) if snippet_el else '',
        })
    return out


_BLOCK_MARKERS = {
    'google': (
        'unusual traffic',
        'recaptcha',
        'detected unusual traffic',
        'captcha-form',
    ),
    'bing': (
        'access denied',
        'verify you are a human',
    ),
    'ddg': (
        'anomaly detected',
        'rate limit',
    ),
}

# Signals that indicate blocking regardless of engine (e.g. proxied captcha pages)
_COMMON_BLOCK_MARKERS = (
    'captcha-form',
    'unusual traffic',
    'recaptcha',
)


def is_blocked(engine: str, html: str) -> bool:
    """True if the SERP HTML looks like a captcha / rate-limit page."""
    if not html:
        return False
    h = html.lower()
    engine_markers = _BLOCK_MARKERS.get(engine, ())
    return any(n.lower() in h for n in engine_markers) or any(
        n.lower() in h for n in _COMMON_BLOCK_MARKERS
    )


_ENGINE_URLS = {
    'ddg': 'https://html.duckduckgo.com/html/?q={q}',
    'bing': 'https://www.bing.com/search?q={q}',
    'google': 'https://www.google.com/search?q={q}',
}
_ENGINE_PARSERS = {
    'ddg': parse_ddg_results,
    'bing': parse_bing_results,
    'google': parse_google_results,
}
_FALLBACK_ORDER = ('ddg', 'bing', 'google')


def run_serp_query_with_fallback(query: str, *, fetch_fn) -> dict:
    """Try each engine in priority order; return on first non-blocked result."""
    for engine in _FALLBACK_ORDER:
        url = _ENGINE_URLS[engine].format(q=quote_plus(query))
        html = fetch_fn(url)
        if html is None:
            continue
        if is_blocked(engine, html):
            continue
        results = _ENGINE_PARSERS[engine](html)
        return {
            'engine': engine,
            'query': query,
            'results': results,
            'status': 'ok',
        }
    return {
        'engine': None,
        'query': query,
        'results': [],
        'status': 'blocked',
    }
