"""
URL normalization — strips tracking parameters from URLs before handoff.

Sales feedback (2026-04-25): the handoff CSV had ugly URLs like
`https://www.example.com/?sc_cid=GBP%3AO%3AGP%3A782%3AOrganic_Search...`
that came from Google Maps' tracking parameters. Strip these at handoff
time. Original URL is preserved separately in audit columns.

Removes:
  - utm_*               (Google Analytics)
  - sc_cid              (GBP source-cid)
  - y_source            (Yext)
  - _vsrefdom           (visit source)
  - gclid, fbclid       (ad click IDs)
  - mc_*                (Mailchimp)
  - ref, source         (generic referral)
  - hl, authuser, rclk  (Google Maps internals)

Lowercases the host. Removes trailing slash on path-only URLs. Preserves
original path, query that isn't tracking, and fragment.
"""
from __future__ import annotations

from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

# Param names that are pure tracking — drop them.
TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'utm_id',
    'sc_cid', 'y_source', '_vsrefdom',
    'gclid', 'fbclid', 'msclkid', 'dclid', 'gbraid', 'wbraid',
    'mc_cid', 'mc_eid',
    'ref', 'source', 'campaign',
    # Google Maps internal params
    'hl', 'authuser', 'rclk', 'entry',
    # Yelp / common analytics
    'osq', 'override_cta',
}


def normalize_url(url: str | None) -> str | None:
    """Return a cleaned URL, or None if input is None/empty/unparseable."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url:
        return None
    try:
        p = urlparse(url)
    except Exception:
        return url

    if not p.scheme or not p.netloc:
        # Not a valid absolute URL — return as-is, conservative.
        return url

    netloc = p.netloc.lower()
    path = p.path or ''

    # Filter query params first so we know if any survive.
    if p.query:
        kept = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                if k.lower() not in TRACKING_PARAMS]
        new_query = urlencode(kept)
    else:
        new_query = ''

    # Strip trailing slash:
    #   - on bare-host URLs (path == '/')
    #   - on multi-segment paths when there is no query/fragment
    if path == '/':
        path = ''
    elif path.endswith('/') and len(path) > 1 and not new_query and not p.fragment:
        path = path.rstrip('/')

    return urlunparse((p.scheme, netloc, path, p.params, new_query, p.fragment))
