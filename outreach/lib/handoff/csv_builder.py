"""
Build the sales-handoff CSV from the enriched master.

Includes ALL rows (independents + chain-flagged). Sales filters by tier or
chain flag in their tool of choice; we never drop rows.

Pain quotes: pulls up to N verbatim ≤3★ review snippets from `pain_hits`,
prioritized by pain category weight.

Vertical knobs (`service_map`, `pain_weights`) are passed in by the caller —
typically a pipeline-aware script that imports them from
`pipelines/<vertical>/config.py`. Both are still keyed by the legacy flat
category names; re-keying to `(main, sub)` tuples (per the pain-classifier
subagent output) is deferred to the pipeline-integration phase — see
`outreach/TODO.md`.
"""
import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from lib.url_normalize import normalize_url


# URL columns sales clicks on. Each gets normalized at output time; the
# original is preserved in the paired audit column when normalization changed
# the value (and left empty otherwise, so the CSV doesn't carry duplicate
# columns when there's nothing to audit).
HANDOFF_URL_FIELDS: list[tuple[str, str]] = [
    ('website',                  'website_raw'),
    ('google_maps_link',         'google_maps_link_raw'),
    ('website_redirect_target',  'website_redirect_target_raw'),
]

FIELDNAMES = [
    # identifiers
    'tier', 'quality_score', 'metro', 'title',
    # contact
    'best_email', 'all_emails', 'email_sources', 'phone',
    'website', 'address', 'google_maps_link',
    # socials
    'socials_facebook', 'socials_instagram', 'socials_linkedin',
    'socials_yelp', 'socials_tiktok', 'socials_youtube',
    # decision-maker
    'owner_name', 'owner_title', 'owner_linkedin', 'additional_team', 'pocs',
    'primary_contact', 'primary_contact_channel',
    # pain
    'top_pain_category', 'pain_breadth_count', 'pain_quote_1', 'pain_quote_2',
    'pain_quote_1_original', 'pain_quote_2_original',
    'pain_quote_1_rating', 'pain_quote_2_rating',
    'recommended_service', 'recommended_service_url',
    # context for sales
    'all_pain_categories', 'all_recommended_services',
    'crawl_status', 'research_note',
    # quality / context
    'review_count', 'rating', 'negative_reviews_1_3_star', 'reviews_analyzed',
    # audit — pre-normalization URLs (populated only when normalization changed the value)
    'website_raw', 'google_maps_link_raw', 'website_redirect_target_raw',
    # risk flags
    'is_chain_or_dso', 'chain_reason',
    'website_redirect_mismatch', 'website_redirect_target',
    'emails_invalid_count', 'crawled_emails_suspect',
    'phone_invalid', 'phone_invalid_reason',
]


def apply_url_normalization(row: dict, url_fields: list[tuple[str, str]]) -> None:
    """Strip tracking params from each URL field in `row`; record original in audit column when changed."""
    for field, audit in url_fields:
        raw = row.get(field) or ''
        cleaned = normalize_url(raw) or ''
        row[field] = cleaned
        row[audit] = raw if cleaned and cleaned != raw else ''


def tier(q):
    if q is None:
        return 'unranked'
    if q >= 60: return 'A'
    if q >= 30: return 'B'
    if q >= 15: return 'C'
    return 'D'


def trustworthy_emails(l):
    invalid = {e['email'].lower() for e in (l.get('emails_invalid') or [])}
    out = [e for e in (l.get('emails') or []) if e.lower() not in invalid]
    if not l.get('crawled_emails_suspect'):
        out += [e for e in (l.get('crawled_emails') or []) if e.lower() not in invalid]
    return out


# POCs below this confidence are vendor/cert badges or section labels that
# look name-like — kept on master.json for audit, dropped from the SDR-facing
# column. Calibrated so json_ld people (~0.7) and img_alt headshots (~0.45)
# survive while badges (~0.0) and bare heading labels (~0.25) fall out.
POC_MIN_CONFIDENCE = 0.30


def pocs_field(l):
    """Names for the `pocs` column: drop invalid POCs and low-confidence
    badges/labels, surface the most trustworthy contacts first. Mirrors how
    `all_emails` drops `emails_invalid` — the full set stays on master.json.

    `confidence` is optional: a POC with no score (older master, pre-scoring
    validate) is kept, so this never silently empties a legacy column."""
    pocs = [
        p for p in (l.get('pocs') or [])
        if isinstance(p, dict) and not p.get('invalid') and p.get('name')
    ]
    kept = [p for p in pocs
            if p.get('confidence') is None or p.get('confidence') >= POC_MIN_CONFIDENCE]
    kept.sort(
        key=lambda p: p.get('confidence') if p.get('confidence') is not None else 0.0,
        reverse=True,
    )
    return ';'.join(p['name'] for p in kept)


def _best_kept_poc(l):
    """Highest-confidence non-invalid crawled POC dict, or None."""
    pocs = [
        p for p in (l.get('pocs') or [])
        if isinstance(p, dict) and not p.get('invalid') and p.get('name')
        and (p.get('confidence') is None or p.get('confidence') >= POC_MIN_CONFIDENCE)
    ]
    if not pocs:
        return None
    return max(pocs, key=lambda p: p.get('confidence') if p.get('confidence') is not None else 0.0)


def _all_socials(l):
    """Every social URL known for the lead: crawled, raw, and OSINT-recovered
    (`social_urls`, grafted by merge_osint_into_master). Reading all three is
    required or recovered business socials never reach the deliverable."""
    return ((l.get('socials') or [])
            + (l.get('crawled_socials') or [])
            + (l.get('social_urls') or []))


def _first_social(l, needle):
    for s in _all_socials(l):
        if needle in s.lower():
            return s
    return ''


def _owner_channel(l):
    """Best reachable channel for the decision-maker, in preference order:
    owner LinkedIn → OSINT-recovered personal LinkedIn → primary-POC personal
    LinkedIn → personal email → primary-POC email → primary-POC other social →
    company LinkedIn → business social DM (Facebook/Instagram).

    The business-social fallback matters for no-website trades (barbers, auto
    shops): the owner runs the shop's IG/FB themselves, so a DM there reaches
    them directly. Channel intent: LinkedIn → personal email → other social →
    company → business DM."""
    primary = next(
        (p for p in (l.get('pocs') or [])
         if isinstance(p, dict) and (p.get('name') or '').strip()),
        None,
    )
    poc_socials = (primary.get('socials') or []) if primary else []
    poc_linkedin = next((s for s in poc_socials if 'linkedin.com' in s.lower()), '')
    poc_other_social = next((s for s in poc_socials if s), '')
    poc_email = (primary.get('email') if primary else '') or ''
    return (
        l.get('owner_linkedin')
        or l.get('linkedin_url_poc')
        or poc_linkedin
        or l.get('poc_email')
        or poc_email
        or poc_other_social
        or l.get('linkedin_url_company')
        or _first_social(l, 'linkedin.com')
        or _first_social(l, 'facebook.com')
        or _first_social(l, 'instagram.com')
        or ''
    )


def primary_contact(l):
    """Return (name, channel) for the single best reachable contact.

    Preference order for the person: owner-lookup → osint poc → crawled POC.
    See `_owner_channel` for the owner-branch channel waterfall. Returns
    ('', '') when nothing reachable is known."""
    # 1. owner-lookup decision-maker (ICP-targeted)
    if l.get('owner_name'):
        return l['owner_name'], _owner_channel(l)
    # 2. osint-discovered person
    if l.get('poc_name'):
        channel = (
            l.get('linkedin_url_poc')
            or l.get('poc_email') or ''
        )
        return l['poc_name'], channel
    # 3. highest-confidence crawled POC
    poc = _best_kept_poc(l)
    if poc:
        channel = (
            next((s for s in (poc.get('socials') or []) if 'linkedin' in s.lower()), '')
            or poc.get('email') or ''
            or (poc.get('socials') or [''])[0]
        )
        if not channel:
            channel = l.get('linkedin_url_company') or _first_social(l, 'linkedin.com')
        return poc['name'], channel
    # 4. no person — company-level channel only is not a "contact"
    return '', ''


def _invalid_email_set(l):
    return {
        e['email'].lower()
        for e in (l.get('emails_invalid') or [])
        if isinstance(e, dict) and e.get('email')
    }


def all_emails(l):
    """All extracted emails for the audit column, with already-flagged
    invalid entries (image artifacts, vendor noise, placeholders) removed —
    sales reads the CSV directly, so don't surface validate-stage junk
    here. The full unfiltered set is preserved on master.json for audit."""
    invalid = _invalid_email_set(l)
    out = [e for e in (l.get('emails') or []) if e and e.lower() not in invalid]
    for e in (l.get('crawled_emails') or []):
        if e and e.lower() not in invalid and e not in out:
            out.append(e)
    return out


def email_sources(l):
    """Positional sources for `all_emails` — must mirror its filtering so
    each remaining email lines up with its source by index."""
    invalid = _invalid_email_set(l)
    raw_emails  = list(l.get('emails') or [])
    raw_sources = list(l.get('emails_source') or [])
    out = []
    for i, e in enumerate(raw_emails):
        if not e or e.lower() in invalid:
            continue
        out.append(raw_sources[i] if i < len(raw_sources) else 'gosom_scraper')
    crawled  = list(l.get('crawled_emails') or [])
    crawled_sources = list(l.get('crawled_emails_source') or [])
    seen = set(e.lower() for e in raw_emails if e and e.lower() not in invalid)
    for i, e in enumerate(crawled):
        if not e or e.lower() in invalid or e.lower() in seen:
            continue
        seen.add(e.lower())
        out.append(crawled_sources[i] if i < len(crawled_sources) else 'agent_browser_crawl')
    return out


def _pain_hits_field(l: dict) -> dict:
    """Prefer agent_pain_hits (pain-classifier subagent output, keyed by the
    new STL hierarchy main category) over the legacy pain_hits (flat-keyed
    SBERT/regex output). Once the legacy field stops appearing in masters,
    drop the fallback."""
    return l.get('agent_pain_hits') or l.get('pain_hits') or {}


def top_pain_with_quotes(l, *, pain_weights: dict, n_quotes: int = 2):
    """Return (top_category_name, [quote-dict, ...]) — quotes are verbatim
    ≤3★ snippets, dedupe'd, ordered by pain category weight × hit count.

    Reads `agent_pain_hits` if present, falling back to `pain_hits` for
    leads classified by the legacy SBERT/regex flow."""
    pain = _pain_hits_field(l)
    if not pain:
        return (None, [])
    scored = sorted(pain.keys(), key=lambda c: -(pain_weights.get(c, 1) * len(pain[c])))
    top_cat = scored[0]
    quotes = []
    seen = set()
    for cat in scored:
        for hit in pain[cat]:
            snippet = (hit.get('snippet') or '').strip()
            if not snippet or snippet in seen:
                continue
            quotes.append({
                'category': cat,
                'rating': hit.get('rating'),
                'reviewer': hit.get('reviewer'),
                'snippet': snippet,
                'snippet_en': (hit.get('snippet_en') or '').strip(),
                'matched': hit.get('matched'),
            })
            seen.add(snippet)
            if len(quotes) >= n_quotes:
                return (top_cat, quotes)
    return (top_cat, quotes)


def split_socials(socials):
    """Categorize a flat social list into per-platform columns."""
    out = {'facebook': [], 'instagram': [], 'linkedin': [], 'yelp': [], 'tiktok': [], 'youtube': [], 'twitter': []}
    for s in socials or []:
        sl = s.lower()
        if 'facebook.com' in sl: out['facebook'].append(s)
        elif 'instagram.com' in sl: out['instagram'].append(s)
        elif 'linkedin.com' in sl: out['linkedin'].append(s)
        elif 'yelp.com' in sl: out['yelp'].append(s)
        elif 'tiktok.com' in sl: out['tiktok'].append(s)
        elif 'youtube.com' in sl: out['youtube'].append(s)
        elif 'twitter.com' in sl or 'x.com' in sl: out['twitter'].append(s)
    return {k: ';'.join(v) for k, v in out.items()}


def _backfill_quality_score(l: dict, pain_weights: dict) -> None:
    """Compute quality_score on `l` if missing. Weight constants match
    lib/ranking.py:quality_score defaults — kept literal here to avoid
    cyclic dependency on a vertical-supplied weight."""
    if 'quality_score' in l:
        return
    pain = _pain_hits_field(l)
    weighted = sum(pain_weights.get(c, 1) * len(h) for c, h in pain.items())
    breadth = len(pain)
    size = math.log10(max(l.get('review_count', 0), 1))
    rating_gap = max(0, 4.9 - (l.get('rating') or 0))
    l['quality_score'] = round(weighted + breadth * 2 + size * 3 + rating_gap * 4, 2)
    l['weighted_pain'] = weighted
    l['pain_breadth'] = breadth


def _build_row(l: dict, *, service_map: dict, pain_weights: dict) -> dict:
    top_cat, quotes = top_pain_with_quotes(l, pain_weights=pain_weights, n_quotes=2)
    q1 = quotes[0] if len(quotes) > 0 else None
    q2 = quotes[1] if len(quotes) > 1 else None
    socials = split_socials(_all_socials(l))
    trust_em = trustworthy_emails(l)
    pc_name, pc_channel = primary_contact(l)
    row = {
        'tier': tier(l.get('quality_score')),
        'quality_score': l.get('quality_score'),
        'metro': l.get('metro'),
        'title': l.get('title'),
        'best_email': trust_em[0] if trust_em else '',
        'all_emails': ';'.join(all_emails(l)),
        'email_sources': ';'.join(email_sources(l)),
        'phone': l.get('phone'),
        'website': l.get('website') or l.get('web_site'),
        'address': l.get('address'),
        'google_maps_link': l.get('link'),
        'owner_name': l.get('owner_name'),
        'owner_title': l.get('owner_title'),
        'owner_linkedin': l.get('owner_linkedin'),
        'additional_team': ';'.join(l.get('additional_team') or []),
        'pocs': pocs_field(l),
        'primary_contact': pc_name,
        'primary_contact_channel': pc_channel,
        'top_pain_category': top_cat or '',
        'pain_breadth_count': l.get('pain_breadth') or len(l.get('pain_categories') or []),
        'pain_quote_1': (q1 or {}).get('snippet_en') or (q1 or {}).get('snippet', ''),
        'pain_quote_2': (q2 or {}).get('snippet_en') or (q2 or {}).get('snippet', ''),
        'pain_quote_1_original': (q1 or {}).get('snippet', '') if (q1 or {}).get('snippet_en') else '',
        'pain_quote_2_original': (q2 or {}).get('snippet', '') if (q2 or {}).get('snippet_en') else '',
        'pain_quote_1_rating': (q1 or {}).get('rating', ''),
        'pain_quote_2_rating': (q2 or {}).get('rating', ''),
        'recommended_service': service_map.get(top_cat, ('', ''))[0] if top_cat else '',
        'recommended_service_url': service_map.get(top_cat, ('', ''))[1] if top_cat else '',
        'review_count': l.get('review_count'),
        'rating': l.get('rating'),
        'negative_reviews_1_3_star': l.get('negative_reviews_1_3_star'),
        'reviews_analyzed': l.get('reviews_analyzed'),
        'is_chain_or_dso': 'TRUE' if l.get('is_chain_or_dso') else 'FALSE',
        'chain_reason': l.get('chain_reason') or '',
        'website_redirect_mismatch': 'TRUE' if l.get('website_redirect_mismatch') else 'FALSE',
        'website_redirect_target': l.get('website_redirect_target') or '',
        'emails_invalid_count': len(l.get('emails_invalid') or []),
        'crawled_emails_suspect': 'TRUE' if l.get('crawled_emails_suspect') else 'FALSE',
        'phone_invalid': 'TRUE' if l.get('phone_invalid') else 'FALSE',
        'phone_invalid_reason': l.get('phone_invalid_reason') or '',
        'socials_facebook': socials['facebook'],
        'socials_instagram': socials['instagram'],
        'socials_linkedin': socials['linkedin'],
        'socials_yelp': socials['yelp'],
        'socials_tiktok': socials['tiktok'],
        'socials_youtube': socials['youtube'],
        'all_pain_categories': ';'.join(l.get('pain_categories') or []),
        'all_recommended_services': ';'.join(l.get('recommended_services') or []),
        'crawl_status': l.get('crawl_status') or '',
        'research_note': l.get('research_note') or '',
    }
    apply_url_normalization(row, HANDOFF_URL_FIELDS)
    return row


def build_handoff(
    input_path: Path,
    output_path: Path,
    *,
    service_map: dict,
    pain_weights: dict,
) -> int:
    """Read the enriched master from `input_path`, write a sales-handoff CSV
    to `output_path`. Returns the row count written.

    `service_map` and `pain_weights` are vertical-supplied (typically from
    `pipelines/<vertical>/config.py`).
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = json.loads(input_path.read_text())

    for l in rows:
        _backfill_quality_score(l, pain_weights)

    rows.sort(key=lambda x: (x.get('is_chain_or_dso', False), -x.get('quality_score', 0)))

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        for l in rows:
            w.writerow(_build_row(l, service_map=service_map, pain_weights=pain_weights))

    print(f"wrote {output_path} ({len(rows)} rows)", flush=True)
    return len(rows)


# Entry point: outreach/lib/cli/handoff.py — loads pipeline config and
# resolves master.json under pipelines/<vertical>/outputs/<date>/.
