"""
Graft `enrichment/website_crawl.json` into a pipeline's master.json.

The enrich stage writes one record per UNIQUE HOSTNAME (the queue is
deduped by hostname, so multiple master leads sharing a domain get the
same crawl payload). This script joins each master lead to its crawl row
by hostname and adds `crawled_emails` / `crawled_socials` / `pocs` /
`crawl_status` / `crawl_pages_visited` with provenance, atomically writing
the master back.

Per CLAUDE.md rule 1: existing fields are not replaced; new fields carry
`<field>_source` and `<field>_added_at`. Leads whose hostname has no
crawl row get `crawl_attempted: False` (so consumers can distinguish "we
crawled and got nothing" from "we never crawled it").

Usage:
  python outreach/scripts/merge_crawl_into_master.py <pipeline> \\
    [--master PATH] [--crawl PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.chain_detection import extract_hostname
from scripts._common import (
    add_pipeline_arg,
    pipeline_dir,
    pipeline_lock,
)


CRAWLED_EMAIL_SOURCE  = 'agent_browser_crawl'
CRAWLED_SOCIAL_SOURCE = 'agent_browser_crawl'
POCS_SOURCE           = 'agent_browser_crawl'


def index_crawl_by_hostname(crawl_rows: list[dict]) -> dict[str, dict]:
    """Build a hostname → crawl-row map. When the same hostname appears
    twice (rare), prefer rows with `status == 'ok'` over error rows so
    downstream consumers see the most useful payload."""
    by_host: dict[str, dict] = {}
    for row in crawl_rows:
        host = extract_hostname(row.get('website') or '')
        if not host:
            continue
        existing = by_host.get(host)
        if existing is None:
            by_host[host] = row
            continue
        if existing.get('status') != 'ok' and row.get('status') == 'ok':
            by_host[host] = row
    return by_host


def graft(
    master: list[dict],
    crawl_by_host: dict[str, dict],
    *,
    now_iso: str | None = None,
) -> dict:
    """Mutate `master` in place — add crawl-derived fields per CLAUDE.md
    rule 1. Returns a stats dict."""
    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    matched = unmatched = 0
    for lead in master:
        host = extract_hostname(lead.get('website') or '')
        row = crawl_by_host.get(host) if host else None
        if row is None:
            unmatched += 1
            lead.setdefault('crawl_attempted', False)
            continue
        matched += 1
        emails  = list(row.get('emails')  or [])
        socials = list(row.get('socials') or [])
        pocs    = list(row.get('pocs')    or [])
        lead['crawled_emails']            = emails
        lead['crawled_emails_source']     = [CRAWLED_EMAIL_SOURCE] * len(emails)
        lead['crawled_emails_added_at']   = now_iso
        lead['crawled_socials']           = socials
        lead['crawled_socials_source']    = [CRAWLED_SOCIAL_SOURCE] * len(socials)
        lead['crawled_socials_added_at']  = now_iso
        lead['pocs']                      = pocs
        lead['pocs_source']               = POCS_SOURCE
        lead['pocs_added_at']             = now_iso
        lead['crawl_status']              = row.get('status') or ''
        lead['crawl_pages_visited']       = list(row.get('pages') or [])
        lead['crawl_attempted']           = True
        lead['crawl_added_at']            = now_iso
        if row.get('cloudflare_blocked'):
            lead['cloudflare_blocked'] = True
    return {
        'master_leads': len(master),
        'matched':      matched,
        'unmatched':    unmatched,
        'unique_hosts': len(crawl_by_host),
    }


def write_atomic(path: Path, master: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(master, indent=2, ensure_ascii=False))
    tmp.replace(path)


def latest_master(pdir: Path) -> Path | None:
    out = pdir / 'outputs'
    if not out.is_dir():
        return None
    for d in sorted((p for p in out.iterdir() if p.is_dir()), reverse=True):
        m = d / 'master.json'
        if m.exists():
            return m
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Graft enrichment/website_crawl.json into pipeline master.json.',
    )
    add_pipeline_arg(parser)
    parser.add_argument(
        '--master', type=Path, default=None,
        help='master JSON (default: outputs/<latest-date>/master.json)',
    )
    parser.add_argument(
        '--crawl', type=Path, default=None,
        help='website_crawl.json (default: enrichment/website_crawl.json)',
    )
    args = parser.parse_args(argv)

    pdir = pipeline_dir(args.pipeline)
    master_path = args.master or latest_master(pdir)
    crawl_path  = args.crawl  or (pdir / 'enrichment' / 'website_crawl.json')

    if master_path is None or not master_path.exists():
        sys.stderr.write(f"error: master not found: {master_path}\n")
        return 2
    if not crawl_path.exists():
        sys.stderr.write(f"error: website_crawl.json not found: {crawl_path}\n")
        return 2

    with pipeline_lock(args.pipeline, 'merge_crawl'):
        master     = json.loads(master_path.read_text())
        crawl_rows = json.loads(crawl_path.read_text())
        if not isinstance(master, list):
            sys.stderr.write(f"error: master must be a JSON array: {master_path}\n")
            return 2
        if not isinstance(crawl_rows, list):
            sys.stderr.write(f"error: crawl file must be a JSON array: {crawl_path}\n")
            return 2

        crawl_by_host = index_crawl_by_hostname(crawl_rows)
        stats = graft(master, crawl_by_host)
        write_atomic(master_path, master)

    print(f"  master leads     : {stats['master_leads']}", file=sys.stderr)
    print(f"  unique crawl hosts: {stats['unique_hosts']}", file=sys.stderr)
    print(f"  matched           : {stats['matched']}", file=sys.stderr)
    print(f"  unmatched         : {stats['unmatched']}", file=sys.stderr)
    print(f"wrote {master_path}", flush=True)
    print(f"next: /outreach {args.pipeline} validate", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
