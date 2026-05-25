"""WHOIS lookup for OSINT enrichment.

Returns registrant fields if the registrar exposes them; emits a clean
miss (status='redacted') for privacy-protected domains, or
status='error' for transport/parse failures.

Per outreach/CLAUDE.md rule 1, the caller is responsible for sibling
provenance; this module just returns the raw lookup result.
"""
from __future__ import annotations

import whois  # python-whois

_REDACTION_MARKERS = (
    'REDACTED', 'redacted',
    'Privacy', 'privacy',
    'Withheld for Privacy',
    'WhoisGuard',
    'Domains By Proxy',
    'Contact Privacy Inc',
    'Perfect Privacy',
)
_PRIVACY_EMAIL_DOMAINS = (
    'withheldforprivacy.com', 'whoisguard.com', 'domainsbyproxy.com',
    'contactprivacy.com', 'privacyguardian.org',
)


def lookup_domain(domain: str) -> dict:
    """Look up `domain` and return a normalized dict.

    Keys: registrant_name, registrant_email, registrant_org, status.
    `status` is one of 'ok', 'redacted', 'error'.
    """
    try:
        rec = whois.whois(domain)
    except Exception:
        return {
            'registrant_name': None,
            'registrant_email': None,
            'registrant_org': None,
            'status': 'error',
        }
    name = _first(getattr(rec, 'name', None))
    email = _first(getattr(rec, 'emails', None))
    org = _first(getattr(rec, 'org', None))
    if _is_redacted(name, email, org):
        return {
            'registrant_name': None,
            'registrant_email': None,
            'registrant_org': None,
            'status': 'redacted',
        }
    return {
        'registrant_name': name,
        'registrant_email': email,
        'registrant_org': org,
        'status': 'ok',
    }


def _is_redacted(name, email, org) -> bool:
    if name is None and email is None and org is None:
        return True
    for v in (name, org):
        if v and any(m in v for m in _REDACTION_MARKERS):
            return True
    if email:
        host = email.split('@', 1)[-1].lower() if '@' in email else ''
        if any(host.endswith(d) for d in _PRIVACY_EMAIL_DOMAINS):
            return True
        if name is None and email.lower().startswith(('abuse@', 'proxy@')):
            return True
    return False


def _first(value):
    """python-whois sometimes returns a list, sometimes a string."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value
