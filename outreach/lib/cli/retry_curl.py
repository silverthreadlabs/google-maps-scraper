"""
Retry the recoverable part of a campaign's website-crawl retry queue.

Reads every `website_crawl*_retry.json` under `campaigns/<pipeline>/enrichment/`
(override with repeated `--queue`), refetches each candidate host with a plain
HTTP client and a realistic User-Agent, and writes recovered rows to
`enrichment/website_crawl_curl_retry.json`.

The output is shaped like a `website_crawl.json` row, so it merges with
`merge_crawl_into_master.py --crawl <path>` exactly like a normal crawl file.

Resumable: hosts already present in the output file are skipped.

Usage:
  python outreach/lib/cli/retry_curl.py <pipeline> [--queue PATH ...]
                                        [--workers N] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.chain_detection import extract_hostname
from lib.cli._common import (
    add_pipeline_arg,
    load_pipeline_config,
    pipeline_dir,
    pipeline_lock,
)
from lib.enrichers.curl_retry import retry_one_guarded, select_candidates

OUT_NAME = 'website_crawl_curl_retry.json'
_write_lock = threading.Lock()


def load_queues(pdir: Path, explicit: list[Path] | None) -> list[dict]:
    """Rows from the given queue files, or every retry file in enrichment/."""
    paths = explicit or sorted((pdir / 'enrichment').glob('website_crawl*_retry.json'))
    rows: list[dict] = []
    for p in paths:
        if not p.exists():
            sys.stderr.write(f'warn: queue not found, skipping: {p}\n')
            continue
        data = json.loads(p.read_text())
        rows.extend(data)
        print(f'queue: {p.name} ({len(data)} rows)', flush=True)
    return rows


def _append(row: dict, done: list[dict], out_path: Path) -> None:
    with _write_lock:
        done.append(row)
        tmp = out_path.with_suffix(out_path.suffix + '.tmp')
        tmp.write_text(json.dumps(done, indent=1, ensure_ascii=False))
        tmp.replace(out_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Plain-HTTP retry for a crawl retry queue.')
    add_pipeline_arg(parser)
    parser.add_argument('--queue', type=Path, action='append', default=None,
                        help='retry queue JSON; repeatable (default: all in enrichment/)')
    parser.add_argument('--workers', type=int, default=8,
                        help='parallel fetches (default: 8)')
    parser.add_argument('--limit', type=int, default=None,
                        help='stop after N candidates (for a smoke run)')
    parser.add_argument('--hard-timeout', type=float, default=45.0,
                        help='per-host wall-clock kill in seconds (default: 45)')
    args = parser.parse_args(argv)

    cfg = load_pipeline_config(args.pipeline)
    extra_vendors = getattr(cfg, 'vendor_domains_extra', frozenset())
    pdir = pipeline_dir(args.pipeline)
    out_path = pdir / 'enrichment' / OUT_NAME

    candidates = select_candidates(load_queues(pdir, args.queue))
    if not candidates:
        print('no retry candidates', flush=True)
        return 0

    done: list[dict] = []
    if out_path.exists():
        done = json.loads(out_path.read_text())
    done_hosts = {extract_hostname(r.get('website') or '') for r in done} - {''}
    pending = [c for c in candidates
               if extract_hostname(c.get('website') or '') not in done_hosts]
    if args.limit:
        pending = pending[:args.limit]

    low = sum(1 for c in pending if c.get('low_odds'))
    print(f'candidates: {len(candidates)} | already done: {len(done)} | '
          f'pending: {len(pending)} ({low} low-odds cloudflare) | '
          f'workers: {args.workers}', flush=True)
    if not pending:
        print('nothing to do', flush=True)
        return 0

    total = len(pending)
    with pipeline_lock(args.pipeline, 'retry_curl'):
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {
                ex.submit(retry_one_guarded, c,
                          extra_vendor_domains=extra_vendors,
                          hard_timeout=args.hard_timeout): (i, c)
                for i, c in enumerate(pending, 1)
            }
            for f in as_completed(futs):
                i, c = futs[f]
                try:
                    row = f.result()
                except Exception as e:  # noqa: BLE001
                    row = {'lead_title': c.get('lead_title'),
                           'website': c.get('website'), 'emails': [], 'socials': [],
                           'pocs': [], 'pages': [], 'status': 'still_failing',
                           'errors': [f'worker: {type(e).__name__}: {e}'[:120]]}
                _append(row, done, out_path)
                em = ','.join(row['emails'])[:46] or '-'
                print(f'[{i:>4}/{total}] {row["status"]:<16} '
                      f'em={len(row["emails"]):>2}  '
                      f'{str(row["lead_title"])[:38]:<38} [{em}]', flush=True)

    fresh = done[-total:] if total <= len(done) else done
    counts: dict[str, int] = {}
    for r in fresh:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    recovered = sum(1 for r in fresh if r['status'] == 'ok')
    print('\n==== Summary ====', flush=True)
    for k in sorted(counts):
        print(f'  {k:<18}: {counts[k]}', flush=True)
    print(f'  emails recovered  : {sum(len(r["emails"]) for r in fresh)}', flush=True)
    print(f'  hosts recovered   : {recovered} of {total}', flush=True)
    print(f'wrote {out_path}', flush=True)
    print(f'next: merge_crawl_into_master.py {args.pipeline} --crawl {out_path}',
          flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
