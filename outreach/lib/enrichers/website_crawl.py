"""
Vertical-agnostic website crawler — emails, socials, person-of-contact (POC).

Per-vertical heuristics live in `EnrichProfile`: title markers (Dr/DDS/DMD
for dental, Esq/Attorney for legal, …), JSON-LD person types, practice-name
filter words, and the internal-link patterns we walk to find the POC.

Run shape: callers (a slash command or a small CLI script) load the queue
and the pipeline's profile, then call `run_pool(...)`. Resumable: rerunning
skips leads already in `enrichment_path`. Parallel: spawns N agent-browser
sessions, distributes leads via a thread pool with one session per worker
slot (no shared state across in-flight tasks).
"""
from __future__ import annotations

import json
import queue
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PER_CMD_TIMEOUT = 45
NETWORK_IDLE_TIMEOUT = 25
DEFAULT_WORKERS = 4


@dataclass(frozen=True)
class EnrichProfile:
    """Vertical-specific knobs the crawler injects into JS / Python heuristics.

    Each field maps to one injection point. A new vertical = one new instance.
    """
    poc_title_markers_js: str
    """JS regex source (no surrounding slashes) marking a POC title.
    Dental: r"\\b(?:Dr\\.?|DDS|DMD|D\\.D\\.S\\.?|D\\.M\\.D\\.?)\\b"."""

    jsonld_person_types: tuple[str, ...]
    """Lowercased substrings of JSON-LD @type that count as a POC.
    Dental: ("person", "dentist", "physician")."""

    practice_name_words: frozenset[str]
    """Words that flag a JSON-LD 'Person' entry as the practice itself
    rather than a real person. Dental: dental, dentistry, smiles, …"""

    internal_link_gate_js: str
    """Broad JS regex source for which internal links to keep — pre-filters
    `data.internal` so we don't ship every link on the page through stdout."""

    contact_link_pattern: str
    """Python regex to pick ONE contact-page link from `data.internal`."""

    team_link_pattern: str
    """Python regex to pick ONE team/POC-page link from `data.internal`."""


EXTRACT_JS_TEMPLATE = r"""
(() => {
  const html = document.documentElement.outerHTML;
  const REJECT = /(\.png|\.jpg|\.jpeg|\.svg|\.gif|\.webp|\.woff|\.woff2|\.ttf|\.eot|\.ico|\.css|\.js|\.json|\.xml|@sentry|@keen|@example|@2x|@3x|wixpress|cloudflare|@u\.|@s\.|@v\.|@w\.|@a\.|@b\.|@rola\.com|@wix\.com|@wixsite\.com|@squarespace\.com|@godaddy\.com|@duda\.co|@weebly\.com|@webflow\.io|@webflow\.com|@yelp\.com|@google\.com|@facebook\.com|@instagram\.com|@youtube\.com|@gmpg\.org|@schema\.org|@w3\.org|@sentry\.io|@datadoghq\.com|@hubspot\.com|@mailchimp\.com|@constantcontact\.com|@noreply|@no-reply|@donotreply|@do-not-reply|@yourdomain\.com|@domain\.com|@email\.com|@yoursite\.com|sample@|test@|demo@|placeholder@|email@email|john\.doe@|jane\.doe@)/i;
  const PERSON_TYPES = __JSONLD_PERSON_TYPES__;
  const drMarker = /__POC_TITLE_MARKERS__/i;
  // Honorific prefix is optional, so this captures "Sarah Patel" whether or
  // not the heading prefixes "Dr./Esq./..." — works across verticals.
  const drNameRe = /(?:Dr\.?\s+)?([A-Z][a-zA-Z'’-]{1,}(?:\s+[A-Z]\.?)?\s+[A-Z][a-zA-Z'’-]{1,})/;

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
    .filter(h => /__INTERNAL_LINK_GATE__/i.test(h)))];

  const ldPersons = [];
  document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
    try {
      const data = JSON.parse(s.textContent);
      const items = Array.isArray(data) ? data : [data];
      const visit = (n) => {
        if (!n || typeof n !== 'object') return;
        const type = (n['@type'] || '').toString().toLowerCase();
        if (PERSON_TYPES.some(t => type.includes(t))) {
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


def _build_extract_js(profile: EnrichProfile) -> str:
    """Render EXTRACT_JS_TEMPLATE with profile knobs injected at the three sites."""
    return (
        EXTRACT_JS_TEMPLATE
        .replace("__POC_TITLE_MARKERS__", profile.poc_title_markers_js)
        .replace("__JSONLD_PERSON_TYPES__", json.dumps(list(profile.jsonld_person_types)))
        .replace("__INTERNAL_LINK_GATE__", profile.internal_link_gate_js)
    )


def _ab(*args, timeout=PER_CMD_TIMEOUT, input_text=None, session=None):
    """Run an agent-browser CLI subcommand. Returns (rc, stdout, stderr)."""
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
    """Extract the JSON payload from agent-browser eval stdout (handles both
    plain and double-encoded forms)."""
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


def looks_like_practice_name(name, lead_title, *, profile: EnrichProfile) -> bool:
    """Filter out 'Person' candidates that are actually the practice itself."""
    if not name or ' ' not in name:
        return True
    n = name.lower()
    t = (lead_title or '').lower()
    if any(w in n for w in profile.practice_name_words):
        return True
    if n in t or t.startswith(n):
        return True
    return False


def merge_doctors(data, lead_title, *, profile: EnrichProfile):
    """Merge POC candidates from JSON-LD / headings / img alts; dedupe by name."""
    pocs = {}
    for p in data.get('ldPersons') or []:
        name = (p.get('name') or '').strip()
        if not name or looks_like_practice_name(name, lead_title, profile=profile):
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
        if not name or looks_like_practice_name(name, lead_title, profile=profile):
            continue
        key = name.lower()
        entry = pocs.setdefault(key, {'name': name, 'sources': set(), 'role': None, 'email': None, 'socials': set(), 'url': None})
        entry['sources'].add(f"heading_{h.get('tag')}")
    for a in data.get('drAlts') or []:
        name = (a.get('name') or '').strip()
        if not name or looks_like_practice_name(name, lead_title, profile=profile):
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


def crawl_url(website, lead_title, *, profile: EnrichProfile, session: str):
    """Crawl one website using `session`; return per-lead enriched payload."""
    extract_js = _build_extract_js(profile)
    contact_re = re.compile(profile.contact_link_pattern, re.I)
    team_re = re.compile(profile.team_link_pattern, re.I)

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

    rc, out, err = _ab('open', url, session=session)
    if rc != 0:
        # one quick retry
        time.sleep(2)
        rc, out, err = _ab('open', url, session=session)
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

    _ab('wait', '--load', 'networkidle', timeout=NETWORK_IDLE_TIMEOUT, session=session)

    rc, out, err = _ab('eval', '--stdin', input_text=extract_js, session=session)
    data = parse_eval_output(out)

    if not data:
        result['errors'].append(f'eval_fail_home: {(err or out)[:200]}')
        result['status'] = 'extract_failed'
        return result

    result['pages'].append({'url': data.get('url'), 'title': data.get('title')})

    if data.get('hasCloudflareChallenge'):
        time.sleep(8)
        _ab('wait', '--load', 'networkidle', timeout=20, session=session)
        rc2, out2, _err2 = _ab('eval', '--stdin', input_text=extract_js, session=session)
        data2 = parse_eval_output(out2)
        if data2 and not data2.get('hasCloudflareChallenge'):
            data = data2
        else:
            result['cloudflare_blocked'] = True

    home_emails = set(data.get('emails') or []) | set(data.get('mailtos') or [])
    result['emails'].extend(home_emails)
    result['socials'].extend(data.get('socials') or [])
    home_pocs = merge_doctors(data, lead_title, profile=profile)

    internal = data.get('internal') or []
    visited = {data.get('url')}
    contact_link = next((h for h in internal if contact_re.search(h)), None)
    team_link = next((h for h in internal if team_re.search(h)), None)

    targets = []
    if contact_link and contact_link not in visited:
        targets.append(contact_link)
    if team_link and team_link not in visited and team_link != contact_link:
        targets.append(team_link)

    extra_pocs = []
    for link in targets[:2]:
        rc, out, err = _ab('open', link, session=session)
        if rc != 0:
            result['errors'].append(f'open_fail_subpage: {link[:80]}')
            continue
        _ab('wait', '--load', 'networkidle', timeout=NETWORK_IDLE_TIMEOUT, session=session)
        rc2, out2, _err2 = _ab('eval', '--stdin', input_text=extract_js, session=session)
        d2 = parse_eval_output(out2)
        if not d2:
            result['errors'].append(f'eval_fail_sub: {link[:80]}')
            continue
        result['pages'].append({'url': d2.get('url'), 'title': d2.get('title')})
        result['emails'].extend((d2.get('emails') or []) + (d2.get('mailtos') or []))
        result['socials'].extend(d2.get('socials') or [])
        extra_pocs.extend(merge_doctors(d2, lead_title, profile=profile))

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


def _append_result(r, done_list, enrichment_path: Path):
    """Append + atomically rewrite enrichment_path under a global lock."""
    with _lock:
        done_list.append(r)
        tmp = enrichment_path.with_suffix(enrichment_path.suffix + '.tmp')
        with open(tmp, 'w') as f:
            json.dump(done_list, f, indent=2, ensure_ascii=False)
        tmp.replace(enrichment_path)


def _worker_task(lead, *, profile, session_pool, done_list, enrichment_path, idx, total):
    """Each task checks out a session from the pool, runs, returns it.
    Guarantees: at any moment, at most one task uses a given session."""
    session = session_pool.get()
    try:
        try:
            r = crawl_url(lead.get('website'), lead['title'], profile=profile, session=session)
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
    _append_result(r, done_list, enrichment_path)
    em = ', '.join(r['emails'][:2]) or '-'
    po = ', '.join(p['name'] for p in r['pocs'][:2]) or '-'
    print(f"[{idx:>3}/{total}] {session} QS={lead.get('quality_score',0):.1f} "
          f"status={r['status']:<18} em={len(r['emails']):>2} soc={len(r['socials']):>2} "
          f"poc={len(r['pocs']):>2}  {lead['title'][:42]:<42}  [{em[:50]}] [{po[:40]}]",
          flush=True)


_RETRYABLE_STATUSES = frozenset({
    'cloudflare_blocked', 'http_403', 'timeout',
    'open_error', 'extract_failed', 'crash', 'no_website',
})


def run_pool(
    leads: Iterable[dict],
    *,
    profile: EnrichProfile,
    enrichment_path: Path,
    retry_path: Path,
    workers: int = DEFAULT_WORKERS,
    session_prefix: str = 'crawl',
) -> dict:
    """Run the crawler over `leads`, writing per-lead payloads to `enrichment_path`.

    Resumable: leads already present in `enrichment_path` are skipped.
    Returns a summary dict (counts by status).
    """
    leads = list(leads)
    enrichment_path = Path(enrichment_path)
    retry_path = Path(retry_path)
    enrichment_path.parent.mkdir(parents=True, exist_ok=True)
    retry_path.parent.mkdir(parents=True, exist_ok=True)

    if enrichment_path.exists():
        with open(enrichment_path) as f:
            done = json.load(f)
    else:
        done = []
    done_titles = {r['lead_title'] for r in done}
    pending = [l for l in leads if l['title'] not in done_titles]

    print(f"queue total: {len(leads)} | already done: {len(done)} | "
          f"pending: {len(pending)} | workers: {workers}", flush=True)
    if not pending:
        print("nothing to do", flush=True)
        return _summary(done, retry_path, [])

    session_pool = queue.Queue()
    for i in range(workers):
        session_pool.put(f'{session_prefix}-w{i}')
    total = len(pending)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = []
        for i, lead in enumerate(pending, 1):
            futures.append(ex.submit(
                _worker_task, lead,
                profile=profile, session_pool=session_pool,
                done_list=done, enrichment_path=enrichment_path,
                idx=i, total=total,
            ))
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as e:
                print(f"worker exception: {e}", flush=True)

    retry = [
        {
            'lead_title': r['lead_title'],
            'website': r.get('website'),
            'status': r['status'],
            'errors': r.get('errors', []),
            'quality_score': r.get('quality_score'),
            'metro': r.get('metro'),
        }
        for r in done
        if not r['emails'] and r['status'] in _RETRYABLE_STATUSES
    ]
    with open(retry_path, 'w') as f:
        json.dump(retry, f, indent=2, ensure_ascii=False)

    return _summary(done, retry_path, retry)


def _summary(done, retry_path, retry):
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
    print(f"  Retry queue -> {retry_path} ({len(retry)} entries)")
    return {
        'crawled': n, 'with_emails': found, 'with_poc': poc,
        'cloudflare_blocked': cf, 'http_403': e403, 'timeout': to,
        'open_or_extract_errors': err, 'no_email_found': no_em,
        'retry_count': len(retry),
    }
