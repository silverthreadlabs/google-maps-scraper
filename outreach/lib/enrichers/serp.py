"""SERP enricher for OSINT.

Fetches search-engine results pages via agent-browser; never visits
the URLs the SERP returns directly. Engine fallback: DDG → Bing →
Google. Per CLAUDE.md rule 4, the orchestrator's session pool drives
the actual fetches; this module contains the parsers and the
fallback ladder.
"""
from __future__ import annotations

from bs4 import BeautifulSoup


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
