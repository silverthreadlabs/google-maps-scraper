"""
Chain / DSO detection — industry-agnostic.

Combines four signals to flag a practice as a multi-location operator (DSO,
chain, or franchise) rather than an independent:

    1. Title regex      — known DSO brands ("Aspen Dental", "Coast Dental", ...)
    2. Email domain     — sub-brands often route through corporate domain
                          (info@<location>@nadentalgroup.com → NADG)
    3. Shared hostname  — 2+ practices on same web hostname = same operator
    4. Brand prefix     — first-2-token prefix repeats 3+ times in dataset
                          (auto-detect, with a geographic-prefix guard)

Each signal is industry-agnostic. The lists/regexes themselves are vertical-
specific and supplied by `outreach/pipelines/<vertical>/config.py`.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


@dataclass
class ChainResult:
    is_chain: bool
    reason: str | None         # 'known_dso' | 'dso_email_domain:<host>' | 'shared_hostname_<host>_<n>x' | 'brand_repeats_<n>x_in_dataset' | None


def extract_hostname(url: str | None) -> str:
    if not url:
        return ''
    m = re.match(r'https?://([^/?#]+)', url, re.I)
    if not m:
        return ''
    h = m.group(1).lower()
    return h[4:] if h.startswith('www.') else h


def extract_brand_prefix(title: str) -> str:
    """First-2-token prefix as a brand key. 'Coast Dental - Brandon' → 'coast dental'."""
    if not title:
        return ''
    split = re.split(r'\s+[-–—]\s+| of |,|\|', title, maxsplit=1)
    lead = split[0].strip()
    tokens = lead.split()
    if len(tokens) >= 2:
        return ' '.join(tokens[:2]).lower()
    return lead.lower()


def email_domain_is_dso(emails: list[str], dso_email_domains: set[str]) -> str | None:
    """Return the first DSO domain found in `emails`, or None."""
    for em in emails or []:
        if not isinstance(em, str) or '@' not in em:
            continue
        domain = em.split('@', 1)[1].strip().lower()
        if domain in dso_email_domains:
            return domain
    return None


class ChainDetector:
    """Stateful detector — needs the full dataset to compute repeat counts.

    Args:
        title_dso_regex: compiled regex matching known-DSO names in titles.
        dso_email_domains: set of hostnames where any-email-on-this-domain ⇒ chain.
        geographic_prefixes: set of 2-token brand prefixes that look like brands
            but are city/neighborhood names (e.g. 'round rock', 'south austin').
            Excluded from auto-chain detection to avoid false positives.
        shared_hostname_min_repeats: a hostname appearing N+ times = chain.
        brand_prefix_min_repeats: a brand prefix appearing N+ times = chain
            (unless it's in `geographic_prefixes`).
    """

    def __init__(
        self,
        title_dso_regex: re.Pattern,
        dso_email_domains: set[str],
        geographic_prefixes: set[str] | None = None,
        shared_hostname_min_repeats: int = 2,
        brand_prefix_min_repeats: int = 3,
    ):
        self.title_dso_regex = title_dso_regex
        self.dso_email_domains = dso_email_domains
        self.geographic_prefixes = geographic_prefixes or set()
        self.shared_hostname_min_repeats = shared_hostname_min_repeats
        self.brand_prefix_min_repeats = brand_prefix_min_repeats

        self._chain_hosts: set[str] = set()
        self._auto_chain_brands: set[str] = set()
        self._host_counts: Counter = Counter()
        self._brand_counts: Counter = Counter()

    def fit(self, leads: list[dict]) -> None:
        """Compute dataset-level counts. Call once before `classify_one`.

        Each lead dict needs at minimum 'title', 'website' (or 'web_site') keys.
        """
        host_counts = Counter(extract_hostname(l.get('website') or l.get('web_site') or '') for l in leads)
        host_counts.pop('', None)
        self._host_counts = host_counts
        self._chain_hosts = {h for h, n in host_counts.items() if n >= self.shared_hostname_min_repeats}

        brand_counts = Counter(extract_brand_prefix(l.get('title', '')) for l in leads)
        self._brand_counts = brand_counts
        self._auto_chain_brands = {
            b for b, n in brand_counts.items()
            if n >= self.brand_prefix_min_repeats and b not in self.geographic_prefixes
        }

    def classify_one(self, title: str, website: str | None, emails: list[str]) -> ChainResult:
        """Decide if a single lead is a chain. Call after `fit`."""
        host = extract_hostname(website)
        brand = extract_brand_prefix(title)

        if self.title_dso_regex.search(title or ''):
            return ChainResult(is_chain=True, reason='known_dso')

        dso_email = email_domain_is_dso(emails, self.dso_email_domains)
        if dso_email:
            return ChainResult(is_chain=True, reason=f'dso_email_domain:{dso_email}')

        if host and host in self._chain_hosts:
            return ChainResult(is_chain=True, reason=f'shared_hostname_{host}_{self._host_counts[host]}x')

        if brand in self._auto_chain_brands:
            return ChainResult(is_chain=True, reason=f'brand_repeats_{self._brand_counts[brand]}x_in_dataset')

        return ChainResult(is_chain=False, reason=None)
