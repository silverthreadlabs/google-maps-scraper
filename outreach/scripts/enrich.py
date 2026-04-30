"""
Run website-crawl enrichment for a pipeline.

Reads the lead queue from `pipelines/<pipeline>/enrichment/crawl_queue.json`
(override with `--queue`). Walks each lead's website with agent-browser via
the lib's `run_pool`, writing per-lead enriched payloads to
`enrichment/website_crawl.json` and a retry list to `website_crawl_retry.json`.

Resumable: leads already in `website_crawl.json` are skipped.

Pipeline config requirements:
  ENRICH_PROFILE — see lib/enrichers/website_crawl.py:EnrichProfile.

Usage:
  python outreach/scripts/enrich.py <pipeline> [--queue PATH] [--workers N]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.enrichers.website_crawl import run_pool
from scripts._common import (
    add_pipeline_arg,
    load_pipeline_config,
    pipeline_dir,
    pipeline_lock,
    require_attr,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Run website-crawl enrichment for a pipeline.',
    )
    add_pipeline_arg(parser)
    parser.add_argument(
        '--queue', type=Path, default=None,
        help='lead queue JSON (default: pipelines/<pipeline>/enrichment/crawl_queue.json)',
    )
    parser.add_argument(
        '--workers', type=int, default=4,
        help='parallel agent-browser sessions (default: 4)',
    )
    args = parser.parse_args(argv)

    cfg = load_pipeline_config(args.pipeline)
    profile = require_attr(cfg, 'ENRICH_PROFILE', args.pipeline)

    pdir = pipeline_dir(args.pipeline)
    queue_path = args.queue or (pdir / 'enrichment' / 'crawl_queue.json')
    if not queue_path.exists():
        sys.stderr.write(f"error: queue not found: {queue_path}\n")
        return 2

    leads = json.loads(queue_path.read_text())
    enrichment_path = pdir / 'enrichment' / 'website_crawl.json'
    retry_path = pdir / 'enrichment' / 'website_crawl_retry.json'

    print(f"queue source: {queue_path}", flush=True)
    with pipeline_lock(args.pipeline, 'enrich'):
        run_pool(
            leads,
            profile=profile,
            enrichment_path=enrichment_path,
            retry_path=retry_path,
            workers=args.workers,
            session_prefix=f'{args.pipeline}-crawl',
        )
    return 0


if __name__ == '__main__':
    sys.exit(main())
