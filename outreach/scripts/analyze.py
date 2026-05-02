"""
Build the initial master.json for a pipeline from its raw scrape NDJSON(s).

Reads `pipelines/<pipeline>/raw/*.json`, dedupes by `place_id`, runs chain
detection (`lib.chain_detection.ChainDetector`), computes review-merge stats
and `quality_score`, validates incoming gosom-side emails to partition them
into `emails` vs `emails_invalid` at ingest, and writes
`pipelines/<pipeline>/outputs/<date>/master.json`.

Email-ingest hardening (`emails_invalid` at boundary):
  Gosom's email regex captures WordPress image filenames like
  `*_1440x640@2x.png` and placeholder values like `your@email.com` from
  rendered HTML. Without filtering at ingest, the validate stage flags
  them later but they linger in `master.emails`. Running `validate_email`
  here means the master's `emails` field carries only RFC-shape-valid,
  non-vendor, non-placeholder candidates from the start; rejects land in
  `emails_invalid` with reason. CLAUDE.md rule 1 preserved — nothing is
  dropped, just routed to the right field with provenance.

Pipeline config requirements:
  PAIN_WEIGHTS, DSO_TITLE_REGEX, DSO_EMAIL_DOMAINS, GEOGRAPHIC_PREFIXES.
  Optional: VENDOR_DOMAINS_EXTRA (extends generic email-vendor blocklist).

Usage:
  python outreach/scripts/analyze.py <pipeline> [--output-date YYYY-MM-DD] [--force]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.chain_detection import ChainDetector
from lib.ranking import quality_score, tier
from lib.validators.email import validate_email
from scripts._common import (
    add_pipeline_arg,
    load_pipeline_config,
    pipeline_dir,
    pipeline_lock,
    require_attr,
)


def merge_reviews(raw: dict) -> list[dict]:
    """Merge `user_reviews` + `user_reviews_extended` per CLAUDE.md rule 3,
    deduped by (reviewer, text[:120]). Returns a list of
    {reviewer, text, rating} for downstream stats — not stored in master."""
    out, seen = [], set()
    for src in ('user_reviews', 'user_reviews_extended'):
        for rev in (raw.get(src) or []):
            text = (rev.get('description') or rev.get('Description') or '').strip()
            if not text:
                continue
            reviewer = (rev.get('reviewer_name') or rev.get('Name') or '').strip()
            key = (reviewer, text[:120])
            if key in seen:
                continue
            seen.add(key)
            rs = rev.get('rating') or rev.get('Rating')
            try:
                rating = int(rs) if rs is not None else None
            except (TypeError, ValueError):
                rating = None
            out.append({'reviewer': reviewer, 'text': text, 'rating': rating})
    return out


def partition_emails(
    raw_emails: list[str],
    *,
    extra_vendor_domains: frozenset[str] = frozenset(),
) -> tuple[list[str], list[dict]]:
    """Run each incoming email through `validate_email`. Returns
    (valid_emails, invalid_entries). Order is preserved; duplicates are
    collapsed (case-insensitive) so the master never carries the same
    address twice."""
    valid: list[str] = []
    invalid: list[dict] = []
    seen_valid: set[str] = set()
    seen_invalid: set[str] = set()
    for em in raw_emails or []:
        if not isinstance(em, str):
            continue
        em = em.strip()
        if not em:
            continue
        ok, reason = validate_email(em, extra_vendor_domains=extra_vendor_domains)
        key = em.lower()
        if ok:
            if key in seen_valid:
                continue
            seen_valid.add(key)
            valid.append(em)
        else:
            if key in seen_invalid:
                continue
            seen_invalid.add(key)
            invalid.append({'email': em, 'reason': reason or 'malformed'})
    return valid, invalid


def load_raw(raw_dir: Path) -> list[dict]:
    """Read every `*.json` NDJSON under `raw_dir` and return concatenated rows."""
    rows = []
    for p in sorted(raw_dir.glob('*.json')):
        with p.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
    return rows


def dedupe_by_place_id(rows: list[dict]) -> list[dict]:
    """First-occurrence wins; rows without place_id are dropped — they can't
    be referenced downstream anyway. Logs nothing here; caller can compare
    counts."""
    seen, out = set(), []
    for r in rows:
        pid = r.get('place_id')
        if not pid or pid in seen:
            continue
        seen.add(pid)
        out.append(r)
    return out


def build_lead(
    raw: dict,
    *,
    chain_detector: ChainDetector,
    pain_weights: dict[str, int],
    metro: str,
    extra_vendor_domains: frozenset[str],
    now_iso: str,
) -> dict:
    title = raw.get('title', '')
    website = raw.get('web_site') or raw.get('website') or ''
    raw_emails = raw.get('emails') or []
    valid_emails, invalid_entries = partition_emails(
        raw_emails, extra_vendor_domains=extra_vendor_domains,
    )

    chain = chain_detector.classify_one(title, website, valid_emails)
    reviews = merge_reviews(raw)
    neg = sum(1 for r in reviews if r['rating'] is not None and r['rating'] <= 3)

    rating = raw.get('review_rating') or 0.0
    review_count = raw.get('review_count') or 0
    pain_hits = {}  # legacy SBERT slot — empty (classify-stage fills agent_pain_hits)
    qs, weighted, breadth = quality_score(
        pain_hits, review_count, rating, pain_weights=pain_weights,
    )

    lead = {
        # identity
        'place_id':        raw.get('place_id') or '',
        'place_id_source': 'gosom_scraper',
        'title':           title,
        'link':            raw.get('link') or '',
        # contact
        'website':       website,
        'phone':         raw.get('phone') or '',
        'address':       raw.get('address') or '',
        'emails':        valid_emails,
        'emails_source': ['gosom_scraper'] * len(valid_emails),
    }
    if invalid_entries:
        lead['emails_invalid'] = invalid_entries
    # classification
    lead.update({
        'category':        raw.get('category') or '',
        'metro':           metro,
        'is_chain_or_dso': chain.is_chain,
        'chain_reason':    chain.reason,
        # reviews / pain (pain populated post-classify+merge)
        'rating':                     rating,
        'review_count':               review_count,
        'reviews_analyzed':           len(reviews),
        'negative_reviews_1_3_star':  neg,
        'negative_pct':               round(neg / len(reviews), 3) if reviews else 0.0,
        'pain_hits':       pain_hits,
        'agent_pain_hits': {},
        'pain_categories': [],
        'pain_breadth':    breadth,
        'weighted_pain':   weighted,
        # ranking
        'quality_score': qs,
        'score':         qs,
        'tier':          tier(qs),
        'analyzed_at':   now_iso,
    })
    return lead


def analyze(
    raw_rows: list[dict],
    *,
    pain_weights: dict[str, int],
    dso_title_regex,
    dso_email_domains: set[str],
    geographic_prefixes: set[str],
    metro: str = '',
    extra_vendor_domains: frozenset[str] = frozenset(),
    now_iso: str | None = None,
) -> tuple[list[dict], dict]:
    """Pure function — easy to unit-test. Returns (master_leads, stats)."""
    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    leads_raw = dedupe_by_place_id(raw_rows)

    detector = ChainDetector(
        title_dso_regex=dso_title_regex,
        dso_email_domains=dso_email_domains,
        geographic_prefixes=geographic_prefixes,
    )
    detector.fit(leads_raw)

    master = [
        build_lead(
            r,
            chain_detector=detector,
            pain_weights=pain_weights,
            metro=metro,
            extra_vendor_domains=extra_vendor_domains,
            now_iso=now_iso,
        )
        for r in leads_raw
    ]
    master.sort(key=lambda l: -l['quality_score'])

    stats = {
        'raw_rows':         len(raw_rows),
        'unique_place_ids': len(leads_raw),
        'chains_flagged':   sum(1 for l in master if l['is_chain_or_dso']),
        'leads_with_invalid_emails': sum(1 for l in master if l.get('emails_invalid')),
        'invalid_emails_total':      sum(len(l.get('emails_invalid') or []) for l in master),
    }
    return master, stats


def write_atomic(path: Path, master: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(master, indent=2, ensure_ascii=False))
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Build initial master.json from raw scrape NDJSON.',
    )
    add_pipeline_arg(parser)
    parser.add_argument(
        '--output-date', default=None,
        help='ISO date for outputs/<date>/ folder (default: today UTC)',
    )
    parser.add_argument(
        '--force', action='store_true',
        help='overwrite outputs/<date>/master.json if it already exists',
    )
    args = parser.parse_args(argv)

    cfg = load_pipeline_config(args.pipeline)
    pain_weights        = require_attr(cfg, 'PAIN_WEIGHTS', args.pipeline)
    dso_title_regex     = require_attr(cfg, 'DSO_TITLE_REGEX', args.pipeline)
    dso_email_domains   = require_attr(cfg, 'DSO_EMAIL_DOMAINS', args.pipeline)
    geographic_prefixes = require_attr(cfg, 'GEOGRAPHIC_PREFIXES', args.pipeline)
    metros              = getattr(cfg, 'METROS', [])
    metro               = metros[0] if metros else ''
    extra_vendor        = getattr(cfg, 'VENDOR_DOMAINS_EXTRA', frozenset())

    pdir = pipeline_dir(args.pipeline)
    raw_dir = pdir / 'raw'
    if not raw_dir.is_dir():
        sys.stderr.write(f"error: no raw/ folder for pipeline {args.pipeline!r}: {raw_dir}\n")
        return 2

    today = args.output_date or datetime.now(timezone.utc).date().isoformat()
    out_path = pdir / 'outputs' / today / 'master.json'
    if out_path.exists() and not args.force:
        sys.stderr.write(
            f"error: {out_path} already exists. Pass --force to overwrite, "
            f"or use --output-date to write a new dated folder.\n"
        )
        return 2

    with pipeline_lock(args.pipeline, 'analyze'):
        raw_rows = load_raw(raw_dir)
        if not raw_rows:
            sys.stderr.write(f"error: no rows found in {raw_dir}/*.json\n")
            return 2

        master, stats = analyze(
            raw_rows,
            pain_weights=pain_weights,
            dso_title_regex=dso_title_regex,
            dso_email_domains=dso_email_domains,
            geographic_prefixes=geographic_prefixes,
            metro=metro,
            extra_vendor_domains=extra_vendor,
        )
        write_atomic(out_path, master)

    print(f"  raw rows           : {stats['raw_rows']}", file=sys.stderr)
    print(f"  unique place_ids   : {stats['unique_place_ids']}", file=sys.stderr)
    print(f"  chains flagged     : {stats['chains_flagged']}", file=sys.stderr)
    print(f"  leads w/ invalid em: {stats['leads_with_invalid_emails']}", file=sys.stderr)
    print(f"  invalid emails     : {stats['invalid_emails_total']}", file=sys.stderr)
    print(f"wrote {out_path}", flush=True)
    print(f"next: /outreach {args.pipeline} enrich (or classify if you have reviews)", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
