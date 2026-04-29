"""
Parallel enrichment crawler: emails, socials, person-of-contact (doctor), POC socials.

Input:  dentists_crawl_queue.json   (133 ranked leads, no email yet)
Output: dental_enrichment.json     (per-lead enriched payload, written atomically)
        dental_retry_queue.json    (failures to retry with Playwright MCP)

Resumable: rerunning skips leads already in dental_enrichment.json.
Parallel: spawns N agent-browser sessions, distributes leads via a thread pool.

Usage: python3 crawl_dental_full.py [workers]   # default 4
"""
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path('/home/fassihhaider/Work/google-maps-scraper/gmapsdata')
QUEUE = ROOT / 'dentists_crawl_queue.json'
ENRICH = ROOT / 'dental_enrichment.json'
RETRY = ROOT / 'dental_retry_queue.json'

PER_CMD_TIMEOUT = 45
NETWORK_IDLE_TIMEOUT = 25
DEFAULT_WORKERS = 4

EXTRACT_JS = r"""
(() => {
  const html = document.documentElement.outerHTML;
  const REJECT = /(\.png|\.jpg|\.jpeg|\.svg|\.gif|\.webp|\.woff|\.woff2|\.ttf|\.eot|\.ico|\.css|\.js|\.json|\.xml|@sentry|@keen|@example|@2x|@3x|wixpress|cloudflare|@u\.|@s\.|@v\.|@w\.|@a\.|@b\.|@rola\.com|@wix\.com|@wixsite\.com|@squarespace\.com|@godaddy\.com|@duda\.co|@weebly\.com|@webflow\.io|@webflow\.com|@yelp\.com|@google\.com|@facebook\.com|@instagram\.com|@youtube\.com|@gmpg\.org|@schema\.org|@w3\.org|@sentry\.io|@datadoghq\.com|@hubspot\.com|@mailchimp\.com|@constantcontact\.com|@noreply|@no-reply|@donotreply|@do-not-reply|@yourdomain\.com|@domain\.com|@email\.com|@yoursite\.com|sample@|test@|demo@|placeholder@|email@email|john\.doe@|jane\.doe@)/i;
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
    .filter(h => /(contact|about|team|staff|get-in-touch|our-team|meet|providers|doctors|dentist|dr-)/i.test(h)))];

  const ldPersons = [];
  document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
    try {
      const data = JSON.parse(s.textContent);
      const items = Array.isArray(data) ? data : [data];
      const visit = (n) => {
        if (!n || typeof n !== 'object') return;
        const type = (n['@type'] || '').toString().toLowerCase();
        if (type.includes('person') || type.includes('dentist') || type.includes('physician')) {
          ldPersons.push({
            name: n.name || null,
            jobTitle: n.jobTitle || n.honorificPrefix || null,
            email: n.email || null,
            sameAs: Array.isArray(n.sameAs) ? n.sameAs : (n.sameAs ? [n.sameAs] : []),
            url: n.url || null,
          });
        }
        if (n['@graph']) n['@graph'].forEach(visit);
        for (const k of Object.keys(n)) {
          if (typeof n[k] === 'object') visit(n[k]);
        }
      };
      items.forEach(visit);
    } catch (e) {}
  });

  // Doctor headings: h1-h4 with Dr. / DDS / DMD
  const drMarker = /\b(?:Dr\.?|DDS|DMD|D\.D\.S\.?|D\.M\.D\.?)\b/i;
  // Match "First Last", "First M Last", "First M. Last", "Last-Hyphen Last"
  const drNameRe = /(?:Dr\.?\s+)?([A-Z][a-zA-Z'’-]{1,}(?:\s+[A-Z]\.?)?\s+[A-Z][a-zA-Z'’-]{1,})/;
  const drHeadings = [];
  document.querySelectorAll('h1, h2, h3, h4, .doctor-name, .team-member-name').forEach(h => {
    const t = (h.textContent || '').replace(/\s+/g, ' ').trim();
    if (t.length > 90 || t.length < 5) return;
    if (drMarker.test(t)) {
      const m = t.match(drNameRe);
      drHeadings.push({ tag: h.tagName.toLowerCase(), text: t, name: m ? m[1] : null });
    }
  });

  const drAlts = [];
  document.querySelectorAll('img[alt]').forEach(img => {
    const a = (img.alt || '').trim();
    if (a.length > 100 || a.length < 4) return;
    if (drMarker.test(a)) {
      const m = a.match(drNameRe);
      drAlts.push({ alt: a, name: m ? m[1] : null });
    }
  });

  return JSON.stringify({
    url: location.href,
    title: document.title,
    hasCloudflareChallenge: /Just a moment|challenge-platform|cf-chl|Cloudflare/i.test(document.title + ' ' + html.slice(0, 2000)),
    emails, mailtos, socials, internal,
    ldPersons, drHeadings, drAlts,
  });
})()
"""


def ab(*args, timeout=PER_CMD_TIMEOUT, input_text=None, session=None):
    cmd = ['agent-browser']
    if session:
        cmd += ['--session', session]
    cmd += list(args)
    try:
        proc = subprocess.run(cmd, input=input_text, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, '', 'timeout'


def parse_eval_output(raw):
    if not raw:
        return None
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


def looks_like_practice_name(name, lead_title):
    """Filter out json_ld 'Person' entries that are actually the practice itself."""
    if not name or ' ' not in name:
        return True
    n = name.lower()
    t = (lead_title or '').lower()
    practice_words = {'dental', 'dentistry', 'smiles', 'orthodontics', 'clinic', 'office', 'practice'}
    if any(w in n for w in practice_words):
        return True
    # If the name is a substring of the practice title or vice versa
    if n in t or t.startswith(n):
        return True
    return False


def merge_doctors(data, lead_title):
    pocs = {}
    for p in data.get('ldPersons') or []:
        name = (p.get('name') or '').strip()
        if not name or looks_like_practice_name(name, lead_title):
            continue
        key = name.lower()
        entry = pocs.setdefault(key, {'name': name, 'sources': set(), 'role': None, 'email': None, 'socials': set(), 'url': None})
        entry['sources'].add('json_ld')
        if p.get('jobTitle'):
            entry['role'] = p['jobTitle']
        if p.get('email'):
            entry['email'] = p['email']
        for s in (p.get('sameAs') or []):
            entry['socials'].add(s)
        if p.get('url'):
            entry['url'] = p['url']
    for h in data.get('drHeadings') or []:
        name = (h.get('name') or '').strip()
        if not name or looks_like_practice_name(name, lead_title):
            continue
        key = name.lower()
        entry = pocs.setdefault(key, {'name': name, 'sources': set(), 'role': None, 'email': None, 'socials': set(), 'url': None})
        entry['sources'].add(f"heading_{h.get('tag')}")
    for a in data.get('drAlts') or []:
        name = (a.get('name') or '').strip()
        if not name or looks_like_practice_name(name, lead_title):
            continue
        key = name.lower()
        entry = pocs.setdefault(key, {'name': name, 'sources': set(), 'role': None, 'email': None, 'socials': set(), 'url': None})
        entry['sources'].add('img_alt')
    out = []
    for v in pocs.values():
        v['sources'] = sorted(v['sources'])
        v['socials'] = sorted(v['socials'])
        out.append(v)
    return out


def crawl_url(website, lead_title, session):
    result = {
        'lead_title': lead_title,
        'website': website,
        'pages': [],
        'emails': [],
        'socials': [],
        'pocs': [],
        'errors': [],
        'hit403': False,
        'cloudflare_blocked': False,
        'status': 'unknown',
    }
    if not website:
        result['status'] = 'no_website'
        result['errors'].append('no_website')
        return result

    url = website if website.startswith('http') else 'https://' + website

    rc, out, err = ab('open', url, session=session)
    if rc != 0:
        # one quick retry
        time.sleep(2)
        rc, out, err = ab('open', url, session=session)
    if rc != 0:
        msg = (err + ' ' + out)[:300]
        result['errors'].append(f'open_fail: {msg}')
        if '403' in msg:
            result['hit403'] = True
            result['status'] = 'http_403'
        elif 'timeout' in msg.lower():
            result['status'] = 'timeout'
        else:
            result['status'] = 'open_error'
        return result

    ab('wait', '--load', 'networkidle', timeout=NETWORK_IDLE_TIMEOUT, session=session)

    rc, out, err = ab('eval', '--stdin', input_text=EXTRACT_JS, session=session)
    data = parse_eval_output(out)

    if not data:
        result['errors'].append(f'eval_fail_home: {(err or out)[:200]}')
        result['status'] = 'extract_failed'
        return result

    result['pages'].append({'url': data.get('url'), 'title': data.get('title')})

    if data.get('hasCloudflareChallenge'):
        time.sleep(8)
        ab('wait', '--load', 'networkidle', timeout=20, session=session)
        rc2, out2, _ = ab('eval', '--stdin', input_text=EXTRACT_JS, session=session)
        data2 = parse_eval_output(out2)
        if data2 and not data2.get('hasCloudflareChallenge'):
            data = data2
        else:
            result['cloudflare_blocked'] = True

    home_emails = set(data.get('emails') or []) | set(data.get('mailtos') or [])
    result['emails'].extend(home_emails)
    result['socials'].extend(data.get('socials') or [])
    home_pocs = merge_doctors(data, lead_title)

    internal = data.get('internal') or []
    visited = {data.get('url')}
    contact_link = next((h for h in internal if re.search(r'/(contact|get-in-touch)', h, re.I)), None)
    team_link = next((h for h in internal if re.search(r'/(team|staff|providers|doctors|our-doctor|meet|about)', h, re.I)), None)

    targets = []
    if contact_link and contact_link not in visited:
        targets.append(contact_link)
    if team_link and team_link not in visited and team_link != contact_link:
        targets.append(team_link)

    extra_pocs = []
    for link in targets[:2]:
        rc, out, err = ab('open', link, session=session)
        if rc != 0:
            result['errors'].append(f'open_fail_subpage: {link[:80]}')
            continue
        ab('wait', '--load', 'networkidle', timeout=NETWORK_IDLE_TIMEOUT, session=session)
        rc2, out2, _ = ab('eval', '--stdin', input_text=EXTRACT_JS, session=session)
        d2 = parse_eval_output(out2)
        if not d2:
            result['errors'].append(f'eval_fail_sub: {link[:80]}')
            continue
        result['pages'].append({'url': d2.get('url'), 'title': d2.get('title')})
        result['emails'].extend((d2.get('emails') or []) + (d2.get('mailtos') or []))
        result['socials'].extend(d2.get('socials') or [])
        extra_pocs.extend(merge_doctors(d2, lead_title))

    poc_by_name = {}
    for p in home_pocs + extra_pocs:
        k = p['name'].lower()
        if k not in poc_by_name:
            poc_by_name[k] = p
        else:
            existing = poc_by_name[k]
            existing['sources'] = sorted(set(existing['sources']) | set(p['sources']))
            existing['socials'] = sorted(set(existing['socials']) | set(p['socials']))
            if not existing.get('role') and p.get('role'):
                existing['role'] = p['role']
            if not existing.get('email') and p.get('email'):
                existing['email'] = p['email']

    result['pocs'] = list(poc_by_name.values())
    result['emails'] = sorted(set(result['emails']))
    result['socials'] = sorted(set(result['socials']))

    if result['emails']:
        result['status'] = 'ok'
    elif result['cloudflare_blocked']:
        result['status'] = 'cloudflare_blocked'
    elif result['pages']:
        result['status'] = 'no_email_found'
    else:
        result['status'] = 'unknown'
    return result


_lock = threading.Lock()


def append_result(r, done_list):
    with _lock:
        done_list.append(r)
        tmp = ENRICH.with_suffix('.json.tmp')
        with open(tmp, 'w') as f:
            json.dump(done_list, f, indent=2, ensure_ascii=False)
        tmp.replace(ENRICH)


def worker_task(lead, session_pool, done_list, idx, total):
    """Each task checks out a session from the pool, runs, returns it.
    Guarantees: at any moment, at most one task uses a given session.
    """
    session = session_pool.get()
    try:
        try:
            r = crawl_url(lead.get('website'), lead['title'], session=session)
        finally:
            session_pool.put(session)
    except Exception as e:
        r = {
            'lead_title': lead['title'], 'website': lead.get('website'),
            'status': 'crash', 'errors': [f'crash: {type(e).__name__}: {e}'],
            'emails': [], 'socials': [], 'pocs': [], 'pages': [],
            'hit403': False, 'cloudflare_blocked': False,
        }
    r['quality_score'] = lead.get('quality_score')
    r['metro'] = lead.get('metro')
    r['phone'] = lead.get('phone')
    append_result(r, done_list)
    em = ', '.join(r['emails'][:2]) or '-'
    po = ', '.join(p['name'] for p in r['pocs'][:2]) or '-'
    print(f"[{idx:>3}/{total}] {session} QS={lead.get('quality_score',0):.1f} status={r['status']:<18} em={len(r['emails']):>2} soc={len(r['socials']):>2} poc={len(r['pocs']):>2}  {lead['title'][:42]:<42}  [{em[:50]}] [{po[:40]}]", flush=True)


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_WORKERS
    queue_path = Path(sys.argv[2]) if len(sys.argv) > 2 else QUEUE
    with open(queue_path) as f:
        leads = json.load(f)
    print(f"queue source: {queue_path.name}", flush=True)

    if ENRICH.exists():
        with open(ENRICH) as f:
            done = json.load(f)
    else:
        done = []
    done_titles = {r['lead_title'] for r in done}
    pending = [l for l in leads if l['title'] not in done_titles]

    print(f"queue total: {len(leads)} | already done: {len(done)} | pending: {len(pending)} | workers: {workers}", flush=True)
    if not pending:
        print("nothing to do", flush=True)
        return

    # Session pool: one session per worker slot, checked out per-task. This
    # guarantees a session is never shared across in-flight tasks (which
    # corrupted browser state in the prior round-robin design).
    session_pool = queue.Queue()
    for i in range(workers):
        session_pool.put(f'crawl-w{i}')
    total = len(pending)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = []
        for i, lead in enumerate(pending, 1):
            futures.append(ex.submit(worker_task, lead, session_pool, done, i, total))
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as e:
                print(f"worker exception: {e}", flush=True)

    # Build retry queue
    retry = []
    for r in done:
        if r['emails']:
            continue
        if r['status'] in ('cloudflare_blocked', 'http_403', 'timeout', 'open_error', 'extract_failed', 'crash', 'no_website'):
            retry.append({
                'lead_title': r['lead_title'],
                'website': r.get('website'),
                'status': r['status'],
                'errors': r.get('errors', []),
                'quality_score': r.get('quality_score'),
                'metro': r.get('metro'),
            })
    with open(RETRY, 'w') as f:
        json.dump(retry, f, indent=2, ensure_ascii=False)

    n = len(done)
    found = sum(1 for r in done if r['emails'])
    cf = sum(1 for r in done if r['status'] == 'cloudflare_blocked')
    e403 = sum(1 for r in done if r['status'] == 'http_403')
    to = sum(1 for r in done if r['status'] == 'timeout')
    err = sum(1 for r in done if r['status'] in ('open_error', 'extract_failed', 'crash'))
    no_em = sum(1 for r in done if r['status'] == 'no_email_found')
    poc = sum(1 for r in done if r.get('pocs'))
    print(f"\n==== Summary ====")
    print(f"  Crawled            : {n}")
    print(f"  With emails        : {found}")
    print(f"  With POC           : {poc}")
    print(f"  Cloudflare-blocked : {cf}")
    print(f"  HTTP 403           : {e403}")
    print(f"  Timeout            : {to}")
    print(f"  Other open/extract : {err}")
    print(f"  Site reached, no email : {no_em}")
    print(f"\n  Enrichment -> {ENRICH}")
    print(f"  Retry queue -> {RETRY} ({len(retry)} entries)")


if __name__ == '__main__':
    main()
