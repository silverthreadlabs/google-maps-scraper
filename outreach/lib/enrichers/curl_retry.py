"""Plain-HTTP retry for the recoverable part of a website-crawl retry queue.

The agent-browser crawl fails on some sites for reasons a plain HTTP client
with a realistic User-Agent does not hit:

  - the site serves 403 to the headless UA but plain HTML to a normal client
  - the certificate is broken, so the browser refuses to open the page
  - the first fetch timed out because the site was slow, not down

This module retries those. It cannot solve a real Cloudflare JS challenge —
that needs a real browser — but it still attempts those rows, because some
`cloudflare_blocked` results are ordinary 403s on the headless UA.

Generalized from `campaigns/software_ua/scripts/retry_via_curl.py`, which was
hardcoded to one campaign and carried its own substring email blocklist. Email
filtering here goes through the shared `validate_email` instead (CLAUDE.md
rule 5), so every artifact class the validator learns applies here too.

Standard library only. `requests` is not a project dependency.
"""
from __future__ import annotations

import gzip
import re
import socket
import ssl
import time
import urllib.error
import urllib.request
import zlib
from typing import Callable, Iterable
from urllib.parse import urlparse

from lib.chain_detection import extract_hostname
from lib.enrichers.website_crawl import filter_valid_emails

# Statuses a plain HTTP client has a real chance of recovering.
RECOVERABLE_STATUSES = frozenset({'open_error', 'timeout', 'extract_failed'})
# Attempted too, but a real JS challenge will not yield. Marked `low_odds`.
LOW_ODDS_STATUSES = frozenset({'cloudflare_blocked'})

UA = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/121.0.0.0 Safari/537.36')
HEADERS = {
    'User-Agent': UA,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'DNT': '1',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
}

EMAIL_CANDIDATE_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
CONTACT_PATH_RE = re.compile(
    r'/(contact|about|team|company|our-story|meet|staff|get-in-touch)', re.I)
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)

MAX_CONTACT_LINKS = 4
MAX_BYTES = 1_000_000
# A socket timeout bounds one read() call, not the whole response. A server
# that sends one byte just inside the timeout keeps the connection alive for
# as long as it likes. One hvac_tampa host held a worker past 120 s that way.
# So the read loop also carries a wall-clock deadline.
READ_DEADLINE_S = 20.0


def select_candidates(retry_rows: Iterable[dict]) -> list[dict]:
    """Pick the rows worth refetching, deduped by hostname.

    Rows we already reached (`ok`, `no_email_found`) are not candidates —
    refetching them changes nothing. Each returned row carries `low_odds`
    so the caller can report the two classes apart.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for row in retry_rows or []:
        status = row.get('status') or ''
        if status not in RECOVERABLE_STATUSES and status not in LOW_ODDS_STATUSES:
            continue
        host = extract_hostname(row.get('website') or '')
        if not host or host in seen:
            continue
        seen.add(host)
        out.append({**row, 'low_odds': status in LOW_ODDS_STATUSES})
    return out


def is_cloudflare_challenge(html: str | None) -> bool:
    """True when the body is an interstitial challenge rather than the site.

    Keyed on the challenge markers, not on the word "cloudflare" — a normal
    page may mention the CDN in its footer.
    """
    if not html:
        return False
    low = html.lower()
    if 'cf-error' in low:
        return True
    if 'just a moment' in low and 'cloudflare' in low:
        return True
    if 'checking your browser' in low and 'cloudflare' in low:
        return True
    return False


def extract_contact_links(html: str | None, base_url: str) -> list[str]:
    """Absolute URLs of contact/about/team pages linked from `html`."""
    if not html:
        return []
    base = urlparse(base_url)
    found: list[str] = []
    for m in HREF_RE.finditer(html):
        link = m.group(1).strip()
        if link.lower().startswith(('mailto:', 'tel:', 'javascript:')):
            continue
        if not CONTACT_PATH_RE.search(link):
            continue
        if link.startswith('http'):
            url = link
        elif link.startswith('//'):
            url = f'{base.scheme}:{link}'
        elif link.startswith('/'):
            url = f'{base.scheme}://{base.netloc}{link}'
        else:
            continue
        if url.rstrip('/') == base_url.rstrip('/') or url in found:
            continue
        found.append(url)
        if len(found) >= MAX_CONTACT_LINKS:
            break
    return found


def emails_from_html(
    html: str | None,
    *,
    extra_vendor_domains: frozenset[str] = frozenset(),
) -> list[str]:
    """Email addresses in `html`, filtered by the shared validator."""
    if not html:
        return []
    return filter_valid_emails(
        EMAIL_CANDIDATE_RE.findall(html),
        extra_vendor_domains=extra_vendor_domains,
    )


def read_bounded(
    fp,
    *,
    max_bytes: int = MAX_BYTES,
    deadline: float | None = None,
    chunk: int = 65536,
    clock: Callable[[], float] = time.monotonic,
) -> bytes:
    """Read up to `max_bytes` from `fp`, stopping at `deadline`.

    Returns whatever arrived before the limit. A partial page is still worth
    scanning for an email address, so a truncated read is not an error.
    """
    buf = bytearray()
    while len(buf) < max_bytes:
        if deadline is not None and clock() >= deadline:
            break
        block = fp.read(min(chunk, max_bytes - len(buf)))
        if not block:
            break
        buf.extend(block)
    return bytes(buf)


def _decode(raw: bytes, encoding: str | None) -> str:
    if encoding == 'gzip':
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    elif encoding == 'deflate':
        try:
            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
        except zlib.error:
            pass
    return raw.decode('utf-8', errors='replace')


def fetch(url: str, *, timeout: int = 12) -> tuple[int | None, str | None, str | None]:
    """Fetch `url`. Return (status_code, html, error).

    Broken certificates are accepted on purpose. We read public marketing
    pages, so a bad certificate is a reason the browser failed, not a threat
    to us. Nothing is sent to these hosts.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers=HEADERS)
    deadline = time.monotonic() + READ_DEADLINE_S
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = read_bounded(resp, deadline=deadline)
            return resp.status, _decode(raw, resp.headers.get('Content-Encoding')), None
    except urllib.error.HTTPError as e:
        try:
            body = _decode(read_bounded(e, deadline=deadline),
                           e.headers.get('Content-Encoding'))
        except Exception:  # noqa: BLE001
            body = None
        return e.code, body, None if body else f'http_{e.code}'
    except urllib.error.URLError as e:
        return None, None, f'url: {e.reason}'[:120]
    except (TimeoutError, socket.timeout, ssl.SSLError) as e:
        return None, None, f'{type(e).__name__}: {e}'[:120]
    except Exception as e:  # noqa: BLE001 - one bad host must not stop the run
        return None, None, f'other: {type(e).__name__}: {e}'[:120]


def _blank_row(entry: dict, status: str, error: str) -> dict:
    return {
        'lead_title': entry.get('lead_title'),
        'website': (entry.get('website') or '').strip(),
        'metro': entry.get('metro'),
        'quality_score': entry.get('quality_score'),
        'prior_status': entry.get('status'),
        'emails': [], 'socials': [], 'pocs': [], 'pages': [],
        'status': status, 'errors': [error],
    }


def _child(entry: dict, extra_vendor_domains: frozenset[str], q) -> None:
    try:
        q.put(retry_one(entry, extra_vendor_domains=extra_vendor_domains))
    except Exception as e:  # noqa: BLE001
        q.put(_blank_row(entry, 'still_failing', f'child: {type(e).__name__}: {e}'[:120]))


def retry_one_guarded(
    entry: dict,
    *,
    extra_vendor_domains: frozenset[str] = frozenset(),
    hard_timeout: float = 45.0,
) -> dict:
    """`retry_one` with a hard wall-clock kill.

    A socket timeout bounds one read. It does not bound name resolution or the
    TLS handshake, and two hvac_tampa hosts held a worker open indefinitely
    inside those. Only a separate process can be killed, so each host gets one.
    """
    import multiprocessing as mp

    ctx = mp.get_context('fork')
    q = ctx.Queue()
    p = ctx.Process(target=_child, args=(entry, extra_vendor_domains, q), daemon=True)
    p.start()
    p.join(hard_timeout)
    if p.is_alive():
        p.terminate()
        p.join(5)
        if p.is_alive():
            p.kill()
        return _blank_row(entry, 'still_failing', f'hard_timeout_{int(hard_timeout)}s')
    try:
        return q.get_nowait()
    except Exception:  # noqa: BLE001 - child died before putting a row
        return _blank_row(entry, 'still_failing', 'child_died')


def retry_one(
    entry: dict,
    *,
    extra_vendor_domains: frozenset[str] = frozenset(),
) -> dict:
    """Refetch one candidate. Returns a row shaped like a website_crawl row."""
    url = (entry.get('website') or '').strip()
    result = {
        'lead_title': entry.get('lead_title'),
        'website': url,
        'metro': entry.get('metro'),
        'quality_score': entry.get('quality_score'),
        'prior_status': entry.get('status'),
        'emails': [],
        'socials': [],
        'pocs': [],
        'pages': [],
    }
    code, html, err = fetch(url)
    if err or not html:
        result['status'] = 'still_failing'
        result['errors'] = [err or f'http_{code}']
        return result
    if is_cloudflare_challenge(html):
        result['status'] = 'still_cloudflare'
        result['errors'] = ['cloudflare_challenge']
        return result
    if code and code >= 400:
        result['status'] = 'still_failing'
        result['errors'] = [f'http_{code}']
        return result

    emails = emails_from_html(html, extra_vendor_domains=extra_vendor_domains)
    pages = [url]
    for link in extract_contact_links(html, url)[:3]:
        code2, html2, err2 = fetch(link, timeout=10)
        if err2 or not html2 or (code2 and code2 >= 400):
            continue
        pages.append(link)
        for em in emails_from_html(html2, extra_vendor_domains=extra_vendor_domains):
            if em.lower() not in {e.lower() for e in emails}:
                emails.append(em)

    result['emails'] = emails
    result['pages'] = [{'url': u, 'title': ''} for u in pages]
    result['status'] = 'ok' if emails else 'no_email_found'
    return result
