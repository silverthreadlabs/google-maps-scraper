"""
Crawl dental-lead websites with agent-browser to extract emails + socials.
Handles JS-rendered sites and Cloudflare-protected pages that blocked urllib.

Input:  dentists_local_independents.json  (top-N leads)
Output: dental_email_enrichment.json       (url -> emails + socials + errors)
        Also merges discovered emails+socials back into the ranked file.
"""
import json
import subprocess
import sys
import re
import time
from pathlib import Path

RANKED = Path('/home/fassihhaider/Work/google-maps-scraper/gmapsdata/dentists_local_independents.json')
OUT = Path('/home/fassihhaider/Work/google-maps-scraper/gmapsdata/dental_email_enrichment.json')

TOP_N = 50
PER_URL_TIMEOUT = 60   # seconds
CONTACT_RE = re.compile(r'/(contact|contacts|about|team|staff|our-team|meet-|get-in-touch)', re.I)

EXTRACT_JS = r"""
(() => {
  const html = document.documentElement.outerHTML;
  const REJECT = /(\.png|\.jpg|\.jpeg|\.svg|\.gif|\.webp|\.woff|\.woff2|\.ttf|\.eot|\.ico|\.css|\.js|\.json|\.xml|@sentry|@keen|@example|@2x|@3x|wixpress|cloudflare|@u\.|@s\.|@v\.|@w\.|@a\.|@b\.)/i;
  const emails = [...new Set((html.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g) || [])
    .filter(e => !REJECT.test(e)).map(e => e.toLowerCase()))];
  const mailtos = [...new Set(Array.from(document.querySelectorAll('a[href^="mailto:"]'))
    .map(a => { try { return decodeURIComponent(a.href.replace(/^mailto:/,'').split('?')[0]).toLowerCase(); } catch(e){ return ''; } })
    .filter(Boolean))];
  const socials = [...new Set(Array.from(document.querySelectorAll('a[href]')).map(a => a.href)
    .filter(h => /(facebook\.com|instagram\.com|linkedin\.com|twitter\.com|x\.com|yelp\.com|tiktok\.com|youtube\.com)/i.test(h))
    .filter(h => !/sharer|share\?|intent\/|home\?|login|signup|\/ads/i.test(h)))];
  const internal = [...new Set(Array.from(document.querySelectorAll('a[href]')).map(a => a.href)
    .filter(h => { try { return new URL(h).origin === location.origin; } catch(e){ return false; } })
    .filter(h => /(contact|about|team|staff|get-in-touch)/i.test(h)))];
  return JSON.stringify({
    url: location.href,
    title: document.title,
    hasCloudflareChallenge: /Just a moment|challenge-platform|cf-chl|Cloudflare/i.test(document.title + ' ' + html.slice(0, 2000)),
    emails, mailtos, socials, internal,
  });
})()
"""


def ab(*args, timeout=PER_URL_TIMEOUT, input_text=None):
    """Run an agent-browser command with timeout."""
    try:
        proc = subprocess.run(
            ['agent-browser', *args],
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, '', 'timeout'


def parse_eval_output(raw):
    """agent-browser returns a quoted JSON string (possibly with leading markers). Strip and parse."""
    if not raw:
        return None
    # Take last non-empty line (agent-browser prefixes with status lines)
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if line.startswith('"') and line.endswith('"'):
            try:
                return json.loads(json.loads(line))
            except Exception:
                continue
        if line.startswith('{'):
            try:
                return json.loads(line)
            except Exception:
                continue
    return None


def crawl_url(website, lead_title):
    """Open site, extract from homepage, follow a contact page if no email."""
    result = {
        'website': website,
        'title': lead_title,
        'pages': [],
        'emails': [],
        'socials': [],
        'errors': [],
        'hit403': False,
        'cloudflare_blocked': False,
    }
    if not website:
        result['errors'].append('no_website')
        return result

    url = website if website.startswith('http') else 'https://' + website

    # 1) Homepage
    rc, out, err = ab('open', url)
    if rc != 0:
        result['errors'].append(f'open_fail: {err[:200]}')
        if '403' in (err + out):
            result['hit403'] = True
        return result
    ab('wait', '--load', 'networkidle', timeout=30)

    rc, out, err = ab('eval', '--stdin', input_text=EXTRACT_JS)
    data = parse_eval_output(out)
    if data:
        result['pages'].append({'url': data.get('url'), 'status': 'ok', 'title': data.get('title')})
        if data.get('hasCloudflareChallenge'):
            # Wait longer and retry
            time.sleep(8)
            ab('wait', '--load', 'networkidle', timeout=20)
            rc2, out2, _ = ab('eval', '--stdin', input_text=EXTRACT_JS)
            data2 = parse_eval_output(out2)
            if data2 and not data2.get('hasCloudflareChallenge'):
                data = data2
            else:
                result['cloudflare_blocked'] = True
        emails = set(data.get('emails') or []) | set(data.get('mailtos') or [])
        result['emails'].extend(emails)
        result['socials'].extend(data.get('socials') or [])
        internal = data.get('internal') or []
    else:
        result['errors'].append(f'eval_fail_home: {err[:200]}')
        internal = []

    # 2) If no emails yet, try one contact-like internal page
    if not result['emails'] and internal:
        contact_link = next((h for h in internal if CONTACT_RE.search(h)), None)
        if contact_link:
            rc, out, err = ab('open', contact_link)
            if rc == 0:
                ab('wait', '--load', 'networkidle', timeout=20)
                rc2, out2, _ = ab('eval', '--stdin', input_text=EXTRACT_JS)
                d2 = parse_eval_output(out2)
                if d2:
                    result['pages'].append({'url': d2.get('url'), 'status': 'ok'})
                    result['emails'].extend((d2.get('emails') or []) + (d2.get('mailtos') or []))
                    result['socials'].extend(d2.get('socials') or [])

    # Dedupe
    result['emails'] = sorted(set(result['emails']))
    result['socials'] = sorted(set(result['socials']))
    return result


def main():
    with open(RANKED) as f:
        leads = json.load(f)

    top = leads[:TOP_N]
    targets = [l for l in top if not l.get('emails')]
    print(f"Top {TOP_N} local independents: {len(top)} total, {len(targets)} need email enrichment\n")

    results = []
    for i, lead in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {lead['title'][:60]}", flush=True)
        r = crawl_url(lead.get('website'), lead['title'])
        r['lead_title'] = lead['title']
        results.append(r)
        status = 'OK' if r['emails'] else ('CF-BLOCKED' if r['cloudflare_blocked']
                 else '403' if r['hit403']
                 else 'NO-EMAIL' if r['pages'] else 'ERROR')
        emails_str = ', '.join(r['emails'][:3]) or '-'
        socials_n = len(r['socials'])
        print(f"    -> {status}  emails: {emails_str}  socials: {socials_n}  errors: {len(r['errors'])}")

    # Save enrichment file
    with open(OUT, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Merge back into ranked file
    by_title = {r['lead_title']: r for r in results}
    for lead in leads:
        if lead['title'] in by_title and not lead.get('emails'):
            r = by_title[lead['title']]
            if r['emails']:
                lead['emails'] = r['emails']
                lead['emails_source'] = 'agent_browser_crawl'
            if r['socials']:
                lead['socials'] = r['socials']
            if r['hit403']:
                lead['hit403'] = True
            if r['cloudflare_blocked']:
                lead['cloudflare_blocked'] = True

    with open(RANKED, 'w') as f:
        json.dump(leads, f, indent=2, ensure_ascii=False)

    # Summary
    found = sum(1 for r in results if r['emails'])
    cf = sum(1 for r in results if r['cloudflare_blocked'])
    blocked_403 = sum(1 for r in results if r['hit403'])
    empty = sum(1 for r in results if not r['emails'] and not r['cloudflare_blocked'] and not r['hit403'] and r['pages'])
    errors = sum(1 for r in results if r['errors'] and not r['pages'])
    print(f"\n==== Summary ====")
    print(f"  Crawled          : {len(results)}")
    print(f"  Found emails     : {found}")
    print(f"  Cloudflare-blocked: {cf}")
    print(f"  403 errors       : {blocked_403}")
    print(f"  No email on site : {empty}")
    print(f"  Network/other err: {errors}")
    print(f"\n  Enrichment file  -> {OUT}")
    print(f"  Ranked file updated: {RANKED}")


if __name__ == '__main__':
    main()
