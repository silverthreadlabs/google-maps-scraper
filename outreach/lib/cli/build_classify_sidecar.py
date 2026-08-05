"""
Join pain-classifier batch outputs into the merge-ready sidecar.

Reads a work directory produced by `build_classify_batches.py`
(`queue_NNN.json` + `review_index.json` + one `out_NNN.json` per batch) and
emits the place_id-keyed dict that `merge_classifications.py` consumes:

    {"<place_id>": {"<main>": [{sub, confidence, snippet, rating,
                                reviewer, reasoning}]}}

`snippet` comes from `review_index.json` — the FULL review text, not the
subagent's `quote` span. Sales reads the snippet verbatim in the handoff CSV,
so it is never truncated. The subagent's verbatim span is kept alongside as
`quote` for audit.

Refuses to overwrite an existing sidecar (CLAUDE.md rule 1 — the prior run is
the audit record). Pass `--out` to choose a different path.

Usage:
  python outreach/lib/cli/build_classify_sidecar.py <pipeline> --work DIR
      [--out PATH] [--min-confidence F]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.cli._common import add_pipeline_arg, pipeline_dir


def build(work: Path, min_conf: float = 0.0) -> tuple[dict, Counter]:
    index = json.loads((work / 'review_index.json').read_text())
    sidecar: dict[str, dict[str, list]] = {}
    stats = Counter()

    for out in sorted(work.glob('out_*.json')):
        idx = out.name[4:7]
        stats['files'] += 1
        try:
            rows = json.loads(out.read_text())
        except json.JSONDecodeError:
            stats['files_unparseable'] += 1
            sys.stderr.write(f'warn: unparseable, skipped: {out.name}\n')
            continue
        for row in rows:
            rid = str(row.get('id'))
            meta = index.get(rid)
            if meta is None:
                stats['hits_orphaned'] += 1
                continue
            stats['reviews'] += 1
            for cat in (row.get('categories') or []):
                main = cat.get('main')
                if not main:
                    stats['hits_no_main'] += 1
                    continue
                conf = cat.get('confidence')
                conf = float(conf) if isinstance(conf, (int, float)) else 0.0
                if conf < min_conf:
                    stats['hits_below_threshold'] += 1
                    continue
                sidecar.setdefault(meta['place_id'], {}).setdefault(main, []).append({
                    'sub':        cat.get('sub'),
                    'confidence': conf,
                    'snippet':    meta['snippet'],
                    'rating':     meta['rating'],
                    'reviewer':   meta['reviewer'],
                    'reasoning':  cat.get('reasoning') or '',
                    'quote':      cat.get('quote') or '',
                    'batch':      idx,
                })
                stats['hits'] += 1
                stats[f'main:{main}'] += 1
    stats['leads'] = len(sidecar)
    return sidecar, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Join classifier batch outputs into the merge-ready sidecar.')
    add_pipeline_arg(parser)
    parser.add_argument('--work', type=Path, required=True,
                        help='work dir with review_index.json and out_*.json')
    parser.add_argument('--out', type=Path, default=None,
                        help='sidecar path (default: <work>/../<work-date>.json)')
    parser.add_argument('--min-confidence', type=float, default=0.0,
                        help='drop hits below this confidence (default: keep all)')
    args = parser.parse_args(argv)

    work = args.work
    if not (work / 'review_index.json').exists():
        sys.stderr.write(f'error: no review_index.json in {work}\n')
        return 2

    out = args.out
    if out is None:
        date = work.name.split('_work_')[0]
        out = work.parent / f'{date}.json'
    if out.exists():
        sys.stderr.write(f'error: sidecar already exists: {out}\n'
                         f'the prior run is the audit record — pass --out to write elsewhere\n')
        return 2

    sidecar, stats = build(work, args.min_confidence)

    tmp = out.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(sidecar, indent=1, ensure_ascii=False))
    tmp.replace(out)

    print(f'batch files    : {stats["files"]}  (unparseable {stats["files_unparseable"]})')
    print(f'reviews joined : {stats["reviews"]}  (orphaned {stats["hits_orphaned"]})')
    print(f'hits kept      : {stats["hits"]}  (below threshold {stats["hits_below_threshold"]})')
    print(f'leads with pain: {stats["leads"]}')
    print()
    for k in sorted((k for k in stats if k.startswith('main:')),
                    key=lambda k: -stats[k]):
        print(f'  {k[5:]:<28} {stats[k]}')
    print(f'\nwrote {out}')
    print(f'next: merge_classifications.py {args.pipeline} --sidecar {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
