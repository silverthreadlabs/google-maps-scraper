#!/usr/bin/env python3
"""Curl-based retry for the recoverable subset of the crawl retry queue.

Targets sites that gosom's headless browser couldn't reach. Uses requests
with a realistic browser UA + accept headers, follows redirects, ignores
cert errors. Won't solve real Cloudflare JS challenges (those need a real
browser), but catches:

  - Sites that 403'd the headless UA but serve plain HTML to a real-looking client
  - Cert-error sites (--insecure equivalent)
  - Transient timeouts

For each recovered page, extracts emails matching common patterns. Writes
results to `enrichment/website_crawl_curl_retry.json` for downstream merge.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ROOT = Path("outreach/campaigns/software_ua")
QUEUE = ROOT / "enrichment/playwright_retry_queue.json"
OUT = ROOT / "enrichment/website_crawl_curl_retry.json"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/121.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,uk;q=0.8,ru;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
# Skip obvious noise
BAD_EMAIL_PATTERNS = (
    'sentry.', 'wixpress.', 'shopify.', 'cloudflare.', 'example.', 'yourdomain.',
    'sentry-next.', '.png', '.jpg', '.gif', '.svg', 'noreply',
)


def is_real_email(em: str) -> bool:
    em_lower = em.lower()
    for p in BAD_EMAIL_PATTERNS:
        if p in em_lower:
            return False
    return True


def fetch(url: str, timeout: int = 12) -> tuple[int | None, str | None, str | None]:
    """Return (status_code, text, error). Either (code, text, None) or (None, None, error)."""
    try:
        sess = requests.Session()
        retries = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
        sess.mount("https://", HTTPAdapter(max_retries=retries))
        sess.mount("http://", HTTPAdapter(max_retries=retries))
        r = sess.get(url, headers=HEADERS, timeout=timeout, verify=False, allow_redirects=True)
        return r.status_code, r.text, None
    except requests.exceptions.SSLError as e:
        return None, None, f"ssl: {e}"[:100]
    except requests.exceptions.ConnectionError as e:
        return None, None, f"conn: {e}"[:100]
    except requests.exceptions.Timeout as e:
        return None, None, f"timeout: {e}"[:100]
    except Exception as e:
        return None, None, f"other: {type(e).__name__}: {e}"[:100]


def extract_contact_links(html: str, base_url: str) -> list[str]:
    """Find /contact /about /team style links on the page."""
    base = urlparse(base_url)
    found: list[str] = []
    for m in re.finditer(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE):
        link = m.group(1)
        if not re.search(r'/(contact|about|team|company|hello|get-in-touch)', link, re.IGNORECASE):
            continue
        if link.startswith('http'):
            url = link
        elif link.startswith('//'):
            url = f"{base.scheme}:{link}"
        elif link.startswith('/'):
            url = f"{base.scheme}://{base.netloc}{link}"
        else:
            continue
        if url not in found and url != base_url:
            found.append(url)
        if len(found) >= 4:
            break
    return found


def crawl_site(entry: dict) -> dict:
    url = entry["website"].strip()
    title = entry["lead_title"]
    result = {"lead_title": title, "website": url, "metro": entry.get("metro")}

    code, html, err = fetch(url)
    if err or not html:
        result.update({"status": "still_failing", "error": err or f"http_{code}"})
        return result

    if code and code >= 400:
        result.update({"status": "still_failing", "error": f"http_{code}"})
        return result

    # Detect Cloudflare challenge response (status 403/503 with "cf-error", "challenge", etc.)
    if ("Just a moment" in html and "cloudflare" in html.lower()) or \
       ("cf-error" in html) or \
       ("Checking your browser" in html and "cloudflare" in html.lower()):
        result.update({"status": "still_cloudflare", "error": "cloudflare_challenge"})
        return result

    emails_main = sorted({e for e in EMAIL_RE.findall(html) if is_real_email(e)})
    contact_links = extract_contact_links(html, url)

    emails_extra: list[str] = []
    pages_visited = [url]
    for link in contact_links[:3]:
        code2, html2, err2 = fetch(link, timeout=10)
        if html2 and not err2 and (not code2 or code2 < 400):
            pages_visited.append(link)
            for em in EMAIL_RE.findall(html2):
                if is_real_email(em) and em not in emails_main:
                    emails_extra.append(em)

    all_emails = sorted(set(emails_main) | set(emails_extra))
    result.update({
        "status": "ok" if all_emails else "no_email_found",
        "emails": all_emails,
        "pages_visited": pages_visited,
    })
    return result


def main() -> None:
    queue = json.loads(QUEUE.read_text())
    print(f"Retry queue size: {len(queue)}")

    results: list[dict] = []
    stats = {"ok": 0, "no_email": 0, "still_failing": 0, "still_cloudflare": 0}
    for i, entry in enumerate(queue, 1):
        r = crawl_site(entry)
        results.append(r)
        if r["status"] == "ok":
            stats["ok"] += 1
            marker = f"✓ {len(r['emails'])} email(s)"
        elif r["status"] == "no_email_found":
            stats["no_email"] += 1
            marker = "ø no email"
        elif r["status"] == "still_cloudflare":
            stats["still_cloudflare"] += 1
            marker = "✗ cloudflare"
        else:
            stats["still_failing"] += 1
            marker = f"✗ {r.get('error','?')}"
        print(f"[{i:>2}/{len(queue)}] {marker:<30} {entry['lead_title'][:35]:<35} {entry['website'][:50]}")

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nSummary: {stats}")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
