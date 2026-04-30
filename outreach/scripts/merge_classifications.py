"""
Merge a pain-classifier sidecar into a pipeline's master.json.

Bridges the /outreach `classify` stage (which dispatches the
pain-classifier subagent and produces a per-place_id sidecar) and the
`handoff` stage (which reads `agent_pain_hits` from each lead).

Inputs
------
  --master PATH    existing master.json (list of leads with `place_id`)
  --sidecar PATH   sidecar JSON (see SIDECAR SCHEMA below)
  --out PATH       new master.json (atomic write — temp then rename)

SIDECAR SCHEMA
--------------
Dict keyed by place_id (string). Value is the agent_pain_hits dict that
csv_builder.top_pain_with_quotes consumes — same shape as the legacy
`pain_hits` so handoff works without per-source branching:

    {
      "<place_id>": {
        "<main>": [
          {
            "sub":        str | null,
            "confidence": float,
            "snippet":    str,            # verbatim review excerpt
            "rating":     int | null,     # source review rating
            "reviewer":   str | null,     # source review author
            "reasoning":  str             # subagent's why-string
          }
        ]
      }
    }

The classify stage of /outreach builds this shape: it joins each
subagent hit back to its source review (for rating/reviewer/snippet)
and groups hits by main category. This script does NOT do that work —
its only job is grafting the prepared dict into master with provenance
and atomic write.

Provenance (per outreach/CLAUDE.md rule 1)
------------------------------------------
Every lead gets these fields added (existing fields untouched, including
the legacy `pain_hits` from earlier SBERT runs):

    agent_pain_hits          : dict above (or {} if no hits for this lead)
    agent_pain_hits_source   : 'pain-classifier-subagent'
    agent_pain_hits_added_at : ISO-8601 UTC timestamp

Stats (stderr)
--------------
    master leads      : <N>
    leads with hits   : <M>           (≥1 main category fired)
    leads without hits: <N - M>
    orphan place_ids  : <count>       (in sidecar, not in master)

A high orphan count usually means the classify stage ran against a
different master than the one given here — investigate before shipping.

Usage
-----
    python outreach/scripts/merge_classifications.py \\
        --master   outreach/pipelines/dental_sunbelt/outputs/2026-04-25/master.json \\
        --sidecar  outreach/pipelines/dental_sunbelt/enrichment/pain_classifications/2026-04-30.json \\
        --out      outreach/pipelines/dental_sunbelt/outputs/2026-04-30/master.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROVENANCE_TAG = 'pain-classifier-subagent'


def merge(master: list[dict], sidecar: dict[str, dict]) -> dict:
    """Mutate `master` in place: each lead gets agent_pain_hits + provenance.
    Returns a stats dict.

    Also refreshes the derived `pain_breadth` / `pain_categories` views to
    reflect agent_pain_hits when present (else legacy `pain_hits`). These
    are computed views, not raw data; csv_builder reads `pain_breadth_count`
    from `pain_breadth` and only recomputes when `quality_score` is missing,
    so without this refresh agent-only pipelines ship handoff CSVs with
    pain_breadth_count=0."""
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    master_place_ids = {l.get('place_id') for l in master if l.get('place_id')}
    leads_with_hits = 0
    for lead in master:
        place_id = lead.get('place_id')
        hits = sidecar.get(place_id, {}) if place_id else {}
        lead['agent_pain_hits'] = hits
        lead['agent_pain_hits_source'] = PROVENANCE_TAG
        lead['agent_pain_hits_added_at'] = now
        if hits:
            leads_with_hits += 1
        derived_pain = hits or lead.get('pain_hits') or {}
        lead['pain_breadth'] = len(derived_pain)
        lead['pain_categories'] = sorted(derived_pain.keys())
    orphan_place_ids = sorted(pid for pid in sidecar if pid not in master_place_ids)
    return {
        'master_leads': len(master),
        'leads_with_hits': leads_with_hits,
        'leads_without_hits': len(master) - leads_with_hits,
        'orphan_place_ids': orphan_place_ids,
    }


def write_atomic(path: Path, master: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(master, indent=2, ensure_ascii=False))
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Graft a pain-classifier sidecar into a master.json (adds agent_pain_hits + provenance).',
    )
    parser.add_argument('--master', type=Path, required=True)
    parser.add_argument('--sidecar', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)

    if not args.master.exists():
        sys.stderr.write(f"error: master not found: {args.master}\n")
        return 2
    if not args.sidecar.exists():
        sys.stderr.write(f"error: sidecar not found: {args.sidecar}\n")
        return 2

    master = json.loads(args.master.read_text())
    sidecar = json.loads(args.sidecar.read_text())
    if not isinstance(master, list):
        sys.stderr.write(f"error: master must be a JSON array of leads: {args.master}\n")
        return 2
    if not isinstance(sidecar, dict):
        sys.stderr.write(
            f"error: sidecar must be a JSON object keyed by place_id: {args.sidecar}\n"
        )
        return 2

    stats = merge(master, sidecar)
    write_atomic(args.out, master)

    print(f"  master leads      : {stats['master_leads']}", file=sys.stderr)
    print(f"  leads with hits   : {stats['leads_with_hits']}", file=sys.stderr)
    print(f"  leads without hits: {stats['leads_without_hits']}", file=sys.stderr)
    print(f"  orphan place_ids  : {len(stats['orphan_place_ids'])}", file=sys.stderr)
    if stats['orphan_place_ids']:
        sample = stats['orphan_place_ids'][:5]
        ellipsis = '…' if len(stats['orphan_place_ids']) > 5 else ''
        print(f"    first {len(sample)}: {sample}{ellipsis}", file=sys.stderr)
    print(f"wrote {args.out}", flush=True)
    # Print a "next:" hint. Pipeline name is derived from the master path
    # (outputs/<date>/master.json → pipelines/<pipeline>/...) when possible.
    pipeline = ''
    parts = args.out.parts
    if 'pipelines' in parts:
        i = parts.index('pipelines')
        if i + 1 < len(parts):
            pipeline = parts[i + 1]
    print(f"next: /outreach {pipeline or '<pipeline>'} validate", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
