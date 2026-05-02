"""
Decision-maker enrichment — manual-input flow.

There's no fully-automated provider yet (LinkedIn-via-agent-browser hits
Cloudflare; paid people-search APIs aren't integrated). This script
brackets the manual lift so it stays idempotent and provenance-clean:

  1. `--print-queue`  — emit the open queue: tier-A/B leads with no
                        owner_name yet, formatted as ready-to-paste
                        web-search queries.
  2. <fill the sidecar by hand at  enrichment/owner_lookups/<date>.json>
  3. `--apply`         — read the sidecar, patch master in place with
                        owner_name / owner_title / owner_linkedin +
                        provenance, atomic write.

When an automated provider lands later, slot it behind step 1 (write
the sidecar from web search results) and re-run step 3. The interface
stays identical so handoff downstream doesn't notice.

Idempotency: leads already carrying `owner_name` are skipped both ways.

Usage:
  python outreach/scripts/owner_lookup.py <pipeline> --print-queue \\
      [--limit N] [--tiers A,B] [--master PATH]

  python outreach/scripts/owner_lookup.py <pipeline> --apply \\
      [--sidecar PATH] [--master PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._common import add_pipeline_arg, pipeline_dir, pipeline_lock


OWNER_SOURCE = 'web_search_linkedin'


def latest_master(pdir: Path) -> Path | None:
    out = pdir / 'outputs'
    if not out.is_dir():
        return None
    for d in sorted((p for p in out.iterdir() if p.is_dir()), reverse=True):
        m = d / 'master.json'
        if m.exists():
            return m
    return None


def select_queue(
    master: list[dict],
    *,
    tiers: set[str],
    limit: int | None = None,
) -> list[dict]:
    """Pick eligible leads: in `tiers`, no owner_name set, sorted by
    quality_score desc. Returns full lead dicts (caller decides what to
    surface)."""
    eligible = [
        l for l in master
        if l.get('tier') in tiers and not (l.get('owner_name') or '').strip()
    ]
    eligible.sort(key=lambda l: -(l.get('quality_score') or 0))
    return eligible[:limit] if limit is not None else eligible


def print_queue(queue: list[dict], file=sys.stdout) -> None:
    """Emit one line per eligible lead with a ready-to-paste search query
    plus the place_id key the user will need when filling the sidecar.
    Format is human-readable; piping to a file is fine."""
    for l in queue:
        title = l.get('title') or ''
        metro = l.get('metro') or ''
        pid   = l.get('place_id') or ''
        tier  = l.get('tier') or ''
        qs    = l.get('quality_score')
        query = f'"{title}" {metro} owner founder linkedin'
        print(f'[{tier} qs={qs}]  place_id={pid}', file=file)
        print(f'  search: {query}', file=file)
        print(f'  website: {l.get("website") or "—"}', file=file)
        print('', file=file)
    print(f'# {len(queue)} lead(s). Fill the sidecar with `{{place_id: {{name, title, linkedin}}}}` '
          f'and run --apply.', file=file)


def apply_sidecar(
    master: list[dict],
    sidecar: dict,
    *,
    now_iso: str | None = None,
) -> dict:
    """Patch master in place with owner fields from sidecar. Skips leads
    that already carry `owner_name` (idempotent). Returns stats."""
    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    by_pid = {l.get('place_id'): l for l in master if l.get('place_id')}
    patched = skipped_set = orphan = 0
    orphan_pids = []
    for pid, entry in sidecar.items():
        lead = by_pid.get(pid)
        if lead is None:
            orphan += 1
            orphan_pids.append(pid)
            continue
        if (lead.get('owner_name') or '').strip():
            skipped_set += 1
            continue
        lead['owner_name']     = entry.get('name') or ''
        lead['owner_title']    = entry.get('title') or ''
        lead['owner_linkedin'] = entry.get('linkedin') or ''
        lead['owner_source']   = OWNER_SOURCE
        lead['owner_added_at'] = now_iso
        patched += 1
    return {
        'patched':       patched,
        'skipped_set':   skipped_set,
        'orphan':        orphan,
        'orphan_pids':   orphan_pids,
    }


def write_atomic(path: Path, master: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(master, indent=2, ensure_ascii=False))
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Owner-lookup queue printer + sidecar applier (manual provider).',
    )
    add_pipeline_arg(parser)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--print-queue', action='store_true',
                      help='print ready-to-paste search queries for eligible leads')
    mode.add_argument('--apply', action='store_true',
                      help='read sidecar and patch master in place')
    parser.add_argument('--limit', type=int, default=None,
                        help='cap the queue at top-N (default: no cap)')
    parser.add_argument('--tiers', default='A,B',
                        help='comma-separated tiers to include (default: A,B)')
    parser.add_argument('--master', type=Path, default=None,
                        help='master JSON (default: outputs/<latest-date>/master.json)')
    parser.add_argument('--sidecar', type=Path, default=None,
                        help='sidecar JSON (default: enrichment/owner_lookups/<today>.json)')
    args = parser.parse_args(argv)

    pdir = pipeline_dir(args.pipeline)
    master_path = args.master or latest_master(pdir)
    if master_path is None or not master_path.exists():
        sys.stderr.write(f"error: master not found: {master_path}\n")
        return 2

    master = json.loads(master_path.read_text())
    if not isinstance(master, list):
        sys.stderr.write(f"error: master must be a JSON array: {master_path}\n")
        return 2

    if args.print_queue:
        tiers = {t.strip().upper() for t in args.tiers.split(',') if t.strip()}
        queue = select_queue(master, tiers=tiers, limit=args.limit)
        print_queue(queue)
        return 0

    today = datetime.now(timezone.utc).date().isoformat()
    sidecar_path = args.sidecar or (pdir / 'enrichment' / 'owner_lookups' / f'{today}.json')
    if not sidecar_path.exists():
        sys.stderr.write(
            f"error: sidecar not found: {sidecar_path}\n"
            f"hint: --print-queue to see what's needed, then write the sidecar with the\n"
            f"shape  {{\"<place_id>\": {{\"name\": ..., \"title\": ..., \"linkedin\": ...}}}}\n"
        )
        return 2

    sidecar = json.loads(sidecar_path.read_text())
    if not isinstance(sidecar, dict):
        sys.stderr.write(f"error: sidecar must be a JSON object keyed by place_id: {sidecar_path}\n")
        return 2

    with pipeline_lock(args.pipeline, 'owner_lookup'):
        stats = apply_sidecar(master, sidecar)
        write_atomic(master_path, master)

    print(f"  patched         : {stats['patched']}", file=sys.stderr)
    print(f"  skipped (already): {stats['skipped_set']}", file=sys.stderr)
    print(f"  orphan place_ids: {stats['orphan']}", file=sys.stderr)
    if stats['orphan_pids']:
        sample = stats['orphan_pids'][:5]
        ellipsis = '…' if len(stats['orphan_pids']) > 5 else ''
        print(f"    first {len(sample)}: {sample}{ellipsis}", file=sys.stderr)
    print(f"wrote {master_path}", flush=True)
    print(f"next: /outreach {args.pipeline} handoff", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
