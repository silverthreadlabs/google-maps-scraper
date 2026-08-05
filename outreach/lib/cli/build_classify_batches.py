"""
Build pain-classifier batch files for a campaign.

Writes one `queue_NNN.json` per batch plus a `review_index.json` under
`campaigns/<pipeline>/enrichment/pain_classifications/<date>_work_<tag>/`.
Each subagent reads one queue file and writes one `out_NNN.json`, so the
review text never passes through the orchestrator's context.

Selection follows the classify runbook:
  - Reviews come from `raw/*.json`, never from master (master is
    post-aggregation and may have dropped the review arrays).
  - Both key shapes are read: `description`/`Description`,
    `rating`/`Rating`, `reviewer_name`/`Name` (CLAUDE.md rule 3 merges
    `user_reviews` + `user_reviews_extended`).
  - Deduped by `(reviewer, text[:120])`.
  - Kept when `rating <= 3`, or when the rating is missing — the agent can
    still classify on the text.
  - `snippet` holds the FULL review text. Sales reads it verbatim in the
    handoff CSV, so it is never truncated.

Usage:
  python outreach/lib/cli/build_classify_batches.py <pipeline> \\
      [--only-contactable] [--batch-size N] [--tag NAME] [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.cli._common import add_pipeline_arg, pipeline_dir


def latest_master(pdir: Path) -> Path | None:
    out = pdir / 'outputs'
    if not out.is_dir():
        return None
    for d in sorted((p for p in out.iterdir() if p.is_dir()), reverse=True):
        m = d / 'master.json'
        if m.exists():
            return m
    return None


def clean_emails(lead: dict) -> list[str]:
    bad = {x['email'] for x in (lead.get('emails_invalid') or [])
           if isinstance(x, dict) and x.get('email')}
    pool = list(lead.get('crawled_emails') or []) + list(lead.get('emails') or [])
    return [e for e in pool if e not in bad]


def has_valid_phone(lead: dict) -> bool:
    return bool(lead.get('phone') and not lead.get('phone_invalid'))


def is_unclassified(lead: dict) -> bool:
    return not lead.get('agent_pain_hits') and not lead.get('pain_hits')


def index_raw(pdir: Path) -> dict[str, dict]:
    """place_id -> raw scrape record, from every NDJSON under raw/."""
    raw: dict[str, dict] = {}
    for f in sorted(glob.glob(str(pdir / 'raw' / '*.json'))):
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                pid = rec.get('place_id')
                if pid:
                    raw.setdefault(pid, rec)
    return raw


def negative_reviews(rec: dict) -> list[dict]:
    """Deduped reviews rated 3 or lower, or with no rating."""
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    both = (rec.get('user_reviews') or []) + (rec.get('user_reviews_extended') or [])
    for rev in both:
        if not isinstance(rev, dict):
            continue
        text = rev.get('description') or rev.get('Description') or ''
        if not text:
            continue
        reviewer = rev.get('reviewer_name') or rev.get('Name') or ''
        key = (reviewer, text[:120])
        if key in seen:
            continue
        seen.add(key)
        rating_raw = rev.get('rating') or rev.get('Rating')
        try:
            rating = int(rating_raw)
        except (TypeError, ValueError):
            rating = None
        if rating is not None and rating > 3:
            continue
        out.append({'rating': rating, 'reviewer': reviewer, 'snippet': text})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Build pain-classifier batch files for a campaign.')
    add_pipeline_arg(parser)
    parser.add_argument('--only-contactable', action='store_true',
                        help='restrict to leads with a valid phone AND a clean email')
    parser.add_argument('--batch-size', type=int, default=30,
                        help='reviews per batch (runbook range 20-40; default 30)')
    parser.add_argument('--tag', default='auto', help='work directory suffix')
    parser.add_argument('--date', default=None, help='sidecar date (default: today UTC)')
    args = parser.parse_args(argv)

    pdir = pipeline_dir(args.pipeline)
    mpath = latest_master(pdir)
    if mpath is None:
        sys.stderr.write(f'error: no master under {pdir / "outputs"}\n')
        return 2
    master = json.loads(mpath.read_text())
    print(f'master: {mpath}  ({len(master)} leads)', flush=True)

    leads = [l for l in master if is_unclassified(l)]
    print(f'unclassified: {len(leads)}', flush=True)
    if args.only_contactable:
        leads = [l for l in leads if has_valid_phone(l) and clean_emails(l)]
        print(f'  with valid phone AND clean email: {len(leads)}', flush=True)

    raw = index_raw(pdir)
    print(f'raw place_ids indexed: {len(raw)}', flush=True)
    missing = sum(1 for l in leads if l.get('place_id') not in raw)
    if missing:
        pct = 100.0 * missing / max(len(leads), 1)
        print(f'warn: {missing} selected leads ({pct:.1f}%) have no raw record',
              flush=True)

    review_index: dict[str, dict] = {}
    rows: list[dict] = []
    next_id = 0
    leads_with = 0
    for lead in leads:
        rec = raw.get(lead.get('place_id'))
        if not rec:
            continue
        revs = negative_reviews(rec)
        if not revs:
            continue
        leads_with += 1
        for r in revs:
            review_index[str(next_id)] = {
                'place_id': lead['place_id'],
                'rating': r['rating'],
                'reviewer': r['reviewer'],
                'snippet': r['snippet'],
            }
            # The runbook documents `text`; the pain-classifier agent
            # definition documents `snippet`. Emit both so neither breaks.
            rows.append({'id': next_id, 'snippet': r['snippet'],
                         'text': r['snippet'], 'rating': r['rating']})
            next_id += 1

    date = args.date or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    work = pdir / 'enrichment' / 'pain_classifications' / f'{date}_work_{args.tag}'
    if work.exists() and any(work.glob('queue_*.json')):
        sys.stderr.write(f'error: work dir already has batches: {work}\n'
                         f'pass a different --tag to keep the prior run\n')
        return 2
    work.mkdir(parents=True, exist_ok=True)

    size = args.batch_size
    batches = [rows[i:i + size] for i in range(0, len(rows), size)]
    for i, b in enumerate(batches):
        (work / f'queue_{i:03d}.json').write_text(json.dumps(b, indent=1,
                                                            ensure_ascii=False))
    (work / 'review_index.json').write_text(json.dumps(review_index, indent=1,
                                                       ensure_ascii=False))

    print(f'\nleads contributing reviews: {leads_with}', flush=True)
    print(f'reviews queued            : {len(rows)}', flush=True)
    print(f'batches                   : {len(batches)} of <= {size}', flush=True)
    print(f'work dir                  : {work}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
