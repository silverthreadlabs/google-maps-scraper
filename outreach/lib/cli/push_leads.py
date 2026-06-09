"""
Bulk-import leads from a pipeline's master.json into the stl-knights backend.

Reads master.json (enriched), merges raw reviews from raw/*.json, transforms
each lead into the API's importLeadsSchema shape, and POSTs in chunks to
POST /leads/campaigns/:campaignId/import.

The script first upserts the campaign (reusing push_campaign logic) to obtain
the campaign UUID, then pushes leads.

Auth: reads OUTREACH_API_KEY from env (or --api-key). Exits 2 if unset.

Usage:
  python outreach/lib/cli/push_leads.py <pipeline> [--base-url URL] [--master PATH]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.handoff.csv_builder import (
    _pain_hits_field,
    all_emails,
    email_sources,
    split_socials,
    top_pain_with_quotes,
    trustworthy_emails,
)
from lib.cli._common import (
    add_pipeline_arg,
    load_dotenv,
    load_pipeline_config,
    pipeline_dir,
    pipeline_lock,
    require_attr,
)

load_dotenv()
from lib.cli.analyze import merge_reviews, load_raw, dedupe_by_place_id
from lib.cli.push_campaign import _resolve_api_key, _vertical_from_config, upsert_campaign
from lib.cli.validate import latest_master

DEFAULT_CHUNK_SIZE = 50


def _build_reviews_index(raw_dir: Path) -> dict[str, list[dict]]:
    """Build place_id → merged reviews from raw NDJSON files."""
    raw_rows = load_raw(raw_dir)
    deduped = dedupe_by_place_id(raw_rows)
    index: dict[str, list[dict]] = {}
    for row in deduped:
        pid = row.get('place_id')
        if not pid:
            continue
        reviews = merge_reviews(row)
        if reviews:
            index[pid] = reviews
    return index


def _pick_best_email(lead: dict) -> str:
    """Pick the best email from gosom + crawled emails, preferring the first
    trustworthy email."""
    trust = trustworthy_emails(lead)
    return trust[0] if trust else ''


def _flatten_pain_hits(lead: dict) -> list[dict]:
    """Convert agent_pain_hits / pain_hits dict-of-arrays into flat list
    matching the API's painHitPayloadSchema."""
    pain = _pain_hits_field(lead)
    if not pain:
        return []
    hits = []
    for category, entries in pain.items():
        for hit in entries:
            hits.append({
                'category': category,
                # P2: prefer the translated English snippet so non-English
                # campaigns deliver English pain quotes to the CRM. The
                # original-language text is preserved in master + the full
                # reviews payload.
                'snippet': hit.get('snippet_en') or hit.get('snippet') or hit.get('quote') or '',
                'rating': hit.get('rating') or 1,
                'reviewer': hit.get('reviewer'),
                'matched_keyword': hit.get('matched') or hit.get('sub'),
            })
    return hits[:200]


def _build_emails(lead: dict) -> list[dict]:
    """Merge gosom + crawled emails into the API's emailPayloadSchema."""
    emails_list = all_emails(lead)
    sources_list = email_sources(lead)
    best = _pick_best_email(lead)
    result = []
    seen: set[str] = set()
    for i, em in enumerate(emails_list):
        key = em.lower()
        if key in seen:
            continue
        seen.add(key)
        source = sources_list[i] if i < len(sources_list) else 'unknown'
        result.append({
            'email': em,
            'source': source,
            'is_best': em.lower() == best.lower() if best else False,
        })
    return result[:50]


DEFAULT_REVIEWS_CAP = 500


def _build_reviews_payload(reviews: list[dict], cap: int = DEFAULT_REVIEWS_CAP) -> list[dict]:
    """Convert analyze.merge_reviews output to API reviewPayloadSchema."""
    payload = []
    for rev in reviews[:cap]:
        payload.append({
            'reviewer_name': rev.get('reviewer') or rev.get('Name') or '',
            'rating': rev.get('rating') or 1,
            'description': rev.get('text') or rev.get('Description'),
            'profile_picture': rev.get('ProfilePicture'),
            'review_date': rev.get('review_date'),
        })
    return payload


def _build_pocs(lead: dict) -> list[dict]:
    """Convert master pocs to API pocPayloadSchema."""
    raw_pocs = lead.get('pocs') or []
    result = []
    for poc in raw_pocs:
        if poc.get('invalid'):
            continue
        result.append({
            'name': poc.get('name') or '',
            'role': poc.get('role'),
            'email': poc.get('email'),
            'socials': poc.get('socials'),
            'url': poc.get('url'),
            # Tell the CRM which POC is the primary decision-maker (owner) so it
            # can surface them distinctly without re-matching owner_name.
            'primary': bool(poc.get('primary')),
        })
    return result


def _build_socials(lead: dict) -> dict[str, str]:
    """Build socials dict from gosom + crawled socials."""
    all_social_urls = list(lead.get('socials') or []) + list(lead.get('crawled_socials') or [])
    return split_socials(all_social_urls)


def transform_lead(
    lead: dict,
    *,
    reviews_index: dict[str, list[dict]],
    pain_weights: dict[str, int],
    service_map: dict[str, tuple[str, str]],
    reviews_cap: int = DEFAULT_REVIEWS_CAP,
) -> dict:
    """Transform a master.json lead into the importLeadsSchema shape."""
    place_id = lead.get('place_id') or ''
    raw_reviews = reviews_index.get(place_id, [])

    pain_hits = _flatten_pain_hits(lead)
    top_cat, _ = top_pain_with_quotes(lead, pain_weights=pain_weights)
    svc_name, svc_url = service_map.get(top_cat, ('', '')) if top_cat else ('', '')

    all_svc = set()
    pain = _pain_hits_field(lead)
    for cat in (pain or {}):
        sn, _ = service_map.get(cat, ('', ''))
        if sn:
            all_svc.add(sn)

    return {
        'place_id': place_id,
        'tier': lead.get('tier') or 'unranked',
        'quality_score': lead.get('quality_score'),
        'title': lead.get('title') or '',
        'category': lead.get('category'),
        'address': lead.get('address'),
        'phone': lead.get('phone'),
        'website': lead.get('website') or lead.get('web_site'),
        'google_maps_link': lead.get('link'),
        'rating': lead.get('rating'),
        'review_count': lead.get('review_count'),
        'negative_reviews_1_3_star': lead.get('negative_reviews_1_3_star'),
        'reviews_analyzed': lead.get('reviews_analyzed'),
        'best_email': _pick_best_email(lead) or None,
        'socials': _build_socials(lead),
        'owner_name': lead.get('owner_name'),
        'owner_title': lead.get('owner_title'),
        'owner_linkedin': lead.get('owner_linkedin'),
        'pocs': _build_pocs(lead),
        'additional_team': lead.get('additional_team') or [],
        'top_pain_category': top_cat,
        'recommended_service': svc_name or None,
        'recommended_service_url': svc_url or None,
        'all_recommended_services': sorted(all_svc),
        'crawl_status': lead.get('crawl_status'),
        'research_note': lead.get('research_note'),
        'is_chain_or_dso': bool(lead.get('is_chain_or_dso')),
        'chain_reason': lead.get('chain_reason'),
        'emails': _build_emails(lead),
        'pain_hits': pain_hits,
        'reviews': _build_reviews_payload(raw_reviews, cap=reviews_cap),
    }


RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def push_chunk(
    *,
    base_url: str,
    api_key: str,
    campaign_id: str,
    leads: list[dict],
    max_retries: int = 3,
    backoff_base: float = 2.0,
) -> dict:
    """POST a chunk of leads to the import endpoint with retry/backoff on
    429 and 5xx. Final failure raises so the caller counts it as an error."""
    data = json.dumps({'leads': leads}).encode()
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(
            f'{base_url}/leads/campaigns/{campaign_id}/import',
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}',
            },
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode(errors='replace')
            if e.code in RETRYABLE_STATUSES and attempt < max_retries:
                sleep_for = backoff_base ** attempt
                sys.stderr.write(
                    f"warn: API returned {e.code} (attempt {attempt + 1}/{max_retries + 1}), "
                    f"retrying in {sleep_for:.1f}s\n"
                )
                time.sleep(sleep_for)
                last_exc = e
                continue
            sys.stderr.write(f"error: API returned {e.code}: {error_body}\n")
            raise
        except urllib.error.URLError as e:
            sys.stderr.write(f"error: cannot reach API at {base_url}: {e.reason}\n")
            raise
    # Exhausted retries on retryable status
    assert last_exc is not None
    raise last_exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Bulk-import leads from a pipeline into stl-knights.',
    )
    add_pipeline_arg(parser)
    parser.add_argument(
        '--base-url', default=os.environ.get('STL_API_URL', 'http://localhost:3001'),
        help='stl-knights API base URL (default: $STL_API_URL or http://localhost:3001)',
    )
    parser.add_argument(
        '--api-key', default=None,
        help='override OUTREACH_API_KEY env var',
    )
    parser.add_argument(
        '--master', type=Path, default=None,
        help='master JSON path (default: outputs/<latest-date>/master.json)',
    )
    parser.add_argument(
        '--campaign-name', default=None,
        help='campaign display name (default: derived from pipeline name)',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='transform and validate without sending to API',
    )
    parser.add_argument(
        '--chunk-size', type=int, default=DEFAULT_CHUNK_SIZE,
        help=f'leads per import request (default: {DEFAULT_CHUNK_SIZE}). '
             f'Lower when nginx returns 413 on large review payloads.',
    )
    parser.add_argument(
        '--reviews-cap', type=int, default=DEFAULT_REVIEWS_CAP,
        help=f'max reviews attached per lead (default: {DEFAULT_REVIEWS_CAP}). '
             f'Lower to shrink per-lead payload when nginx 413s individual leads.',
    )
    parser.add_argument(
        '--only-place-ids', type=Path, default=None,
        help='path to a file of place_ids (one per line) to restrict the push to. '
             'Useful for retrying a failed subset; importer upserts by place_id.',
    )
    parser.add_argument(
        '--chunk-sleep', type=float, default=0.0,
        help='seconds to sleep between chunks (default: 0). Use a positive '
             'value to pace requests below the API rate limit.',
    )
    args = parser.parse_args(argv)

    api_key = _resolve_api_key(args.api_key)
    cfg = load_pipeline_config(args.pipeline)

    pain_weights = require_attr(cfg, 'PAIN_WEIGHTS', args.pipeline)
    service_map = require_attr(cfg, 'SERVICE_MAP', args.pipeline)
    metros = getattr(cfg, 'metros', [])
    metro = metros[0] if metros else ''
    vertical = _vertical_from_config(cfg)

    pdir = pipeline_dir(args.pipeline)
    master_path = args.master or latest_master(pdir)
    if master_path is None or not master_path.exists():
        sys.stderr.write(
            f"error: master not found "
            f"(checked {args.master if args.master else f'{pdir}/outputs/<latest>/master.json'})\n"
        )
        return 2

    raw_dir = pdir / 'raw'
    if not raw_dir.is_dir():
        sys.stderr.write(f"warn: no raw/ folder — reviews will be empty\n")
        reviews_index: dict[str, list[dict]] = {}
    else:
        print(f"building reviews index from {raw_dir} ...", flush=True)
        reviews_index = _build_reviews_index(raw_dir)
        print(f"  {len(reviews_index)} leads with reviews", flush=True)

    master = json.loads(master_path.read_text())
    print(f"loaded {len(master)} leads from {master_path}", flush=True)

    if args.only_place_ids:
        wanted = {
            line.strip() for line in args.only_place_ids.read_text().splitlines()
            if line.strip()
        }
        before = len(master)
        master = [lead for lead in master if (lead.get('place_id') or '') in wanted]
        missing = wanted - {lead.get('place_id') or '' for lead in master}
        print(
            f"filtered to {len(master)} of {before} leads via {args.only_place_ids} "
            f"({len(missing)} place_ids not found in master)",
            flush=True,
        )
        if not master:
            sys.stderr.write("error: --only-place-ids filtered everything out\n")
            return 2

    slug = args.pipeline.replace('/', '_')
    name = args.campaign_name or slug.replace('_', ' ').title()

    if not args.dry_run:
        print(f"upserting campaign '{slug}' ...", flush=True)
        result = upsert_campaign(
            base_url=args.base_url,
            api_key=api_key,
            slug=slug,
            name=name,
            metro=metro,
            vertical=vertical,
        )
        campaign_id = result.get('data', {}).get('id')
        if not campaign_id:
            sys.stderr.write(f"error: campaign upsert did not return an id: {result}\n")
            return 1
        print(f"  campaign_id={campaign_id}", flush=True)

    with pipeline_lock(args.pipeline, 'push_leads'):
        transformed = [
            transform_lead(
                lead,
                reviews_index=reviews_index,
                pain_weights=pain_weights,
                service_map=service_map,
                reviews_cap=args.reviews_cap,
            )
            for lead in master
        ]

    if args.dry_run:
        print(f"dry-run: {len(transformed)} leads transformed", flush=True)
        sample = transformed[0] if transformed else {}
        print(json.dumps(sample, indent=2, default=str)[:2000], flush=True)
        return 0

    total_imported = 0
    total_errors = 0
    chunk_size = args.chunk_size
    for i in range(0, len(transformed), chunk_size):
        chunk = transformed[i:i + chunk_size]
        chunk_num = (i // chunk_size) + 1
        total_chunks = math.ceil(len(transformed) / chunk_size)
        print(f"pushing chunk {chunk_num}/{total_chunks} ({len(chunk)} leads) ...", flush=True)
        try:
            resp = push_chunk(
                base_url=args.base_url,
                api_key=api_key,
                campaign_id=campaign_id,
                leads=chunk,
            )
            data = resp.get('data', {})
            total_imported += data.get('imported', 0)
            total_errors += data.get('errors', 0)
        except (urllib.error.HTTPError, urllib.error.URLError):
            total_errors += len(chunk)
            continue
        finally:
            if args.chunk_sleep > 0:
                time.sleep(args.chunk_sleep)

    print(
        f"done: {total_imported} imported, {total_errors} errors "
        f"(from {len(transformed)} leads)",
        flush=True,
    )
    return 1 if total_errors > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
