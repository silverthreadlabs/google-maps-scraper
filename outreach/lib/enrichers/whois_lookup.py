"""WHOIS lookup for OSINT enrichment.

Returns registrant fields if the registrar exposes them; emits a clean
miss (status='redacted') for privacy-protected domains, or
status='error' for transport/parse failures.

Per outreach/CLAUDE.md rule 1, the caller is responsible for sibling
provenance; this module just returns the raw lookup result.
"""
from __future__ import annotations

import whois  # python-whois


def lookup_domain(domain: str) -> dict:
    """Look up `domain` and return a normalized dict.

    Keys: registrant_name, registrant_email, registrant_org, status.
    `status` is one of 'ok', 'redacted', 'error'.
    """
    rec = whois.whois(domain)
    name = _first(getattr(rec, 'name', None))
    email = _first(getattr(rec, 'emails', None))
    org = _first(getattr(rec, 'org', None))
    return {
        'registrant_name': name,
        'registrant_email': email,
        'registrant_org': org,
        'status': 'ok',
    }


def _first(value):
    """python-whois sometimes returns a list, sometimes a string."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value
