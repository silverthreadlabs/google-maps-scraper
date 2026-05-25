"""Graft confident OSINT hits into master.json with full provenance.

Reads enrichment/osint/<date>.json (judged by osint-binder subagent),
filters by confidence threshold, applies validators at the boundary
(per outreach/CLAUDE.md rule 5), respects immutability (rule 1).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.validators.email import validate_email


# Fields that hold lists in master (per spec field-cardinality table).
LIST_FIELDS = {'social_urls', 'news_mentions'}

# Fields that require email validation at the boundary (CLAUDE.md rule 5).
EMAIL_FIELDS = {'poc_email'}


def graft(master: list[dict], sidecar: list[dict], *, threshold: float) -> dict:
    """Mutate `master` in place. Returns stats dict."""
    by_pid = {lead.get('place_id'): lead for lead in master}
    grafted = skipped_below = skipped_existing = 0
    for record in sidecar:
        pid = record.get('place_id')
        lead = by_pid.get(pid)
        if lead is None:
            continue
        enriched_at = record.get('enriched_at')
        for field, fr in record.get('fields', {}).items():
            sel = fr.get('selected_index')
            conf = fr.get('selected_confidence')
            if sel is None or conf is None:
                continue
            if conf < threshold:
                skipped_below += 1
                continue
            cand = fr['candidates'][sel]
            if field in LIST_FIELDS:
                _graft_list_field(lead, field, fr, threshold, enriched_at)
                grafted += 1
            else:
                if _is_filled(lead.get(field)):
                    skipped_existing += 1
                    continue
                _graft_scalar_field(lead, field, cand, enriched_at)
                grafted += 1
    return {'grafted': grafted, 'skipped_below_threshold': skipped_below,
            'skipped_existing_value': skipped_existing}


def _is_filled(v) -> bool:
    return v not in (None, '', [], {})


def _validate_email_for_graft(value: str):
    """Adapter wrapping validate_email into a uniform (ok, reason) shape."""
    ok, reason = validate_email(value)
    if ok:
        return True, None
    return False, reason or 'validator_rejected'


def _graft_scalar_field(lead: dict, field: str, cand: dict, enriched_at: str | None) -> None:
    value = cand['value']
    if field in EMAIL_FIELDS:
        ok, reason = _validate_email_for_graft(value)
        if not ok:
            lead[f'{field}_invalid'] = True
            lead[f'{field}_invalid_reason'] = reason or 'validator_rejected'
            lead[f'{field}_invalid_source'] = f'osint_{cand["source"]}'
            return
    lead[field] = value
    lead[f'{field}_source'] = f'osint_{cand["source"]}'
    lead[f'{field}_added_at'] = enriched_at
    lead[f'{field}_confidence'] = cand['judge_confidence']
    if cand.get('query'):
        lead[f'{field}_query'] = cand['query']
    if cand.get('judge_reasoning'):
        lead[f'{field}_judge_reasoning'] = cand['judge_reasoning']


def _graft_list_field(lead: dict, field: str, fr: dict, threshold: float, enriched_at: str | None) -> None:
    """List-typed fields collect ALL candidates above threshold."""
    items = []
    for c in fr['candidates']:
        if c.get('judge_verdict') == 'match' and (c.get('judge_confidence') or 0) >= threshold:
            items.append({
                'value': c['value'],
                'source': f'osint_{c["source"]}',
                'confidence': c['judge_confidence'],
                'query': c.get('query'),
                'judge_reasoning': c.get('judge_reasoning'),
            })
    if not items:
        return
    if not _is_filled(lead.get(field)):
        lead[field] = items
        lead[f'{field}_added_at'] = enriched_at


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

import argparse
import json

from lib.cli._common import (
    add_pipeline_arg,
    load_pipeline_config,
    pipeline_dir,
    pipeline_lock,
    require_attr,
)
from lib.cli.merge_crawl_into_master import latest_master, write_atomic


def _latest_osint_sidecar(pdir: Path) -> Path | None:
    d = pdir / 'enrichment' / 'osint'
    if not d.is_dir():
        return None
    candidates = sorted(d.glob('*.json'), reverse=True)
    return candidates[0] if candidates else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Graft enrichment/osint/<date>.json (judged) into master.json.',
    )
    add_pipeline_arg(parser)
    parser.add_argument('--master', type=Path, default=None,
                        help='master JSON (default: outputs/<latest-date>/master.json)')
    parser.add_argument('--sidecar', type=Path, default=None,
                        help='OSINT sidecar (default: latest enrichment/osint/<date>.json)')
    parser.add_argument('--threshold', type=float, default=None,
                        help='confidence threshold (default: cfg.osint_confidence_threshold)')
    args = parser.parse_args(argv)

    cfg = load_pipeline_config(args.pipeline)
    threshold = args.threshold if args.threshold is not None \
                else float(require_attr(cfg, 'OSINT_CONFIDENCE_THRESHOLD', args.pipeline))

    pdir = pipeline_dir(args.pipeline)
    master_path = args.master or latest_master(pdir)
    sidecar_path = args.sidecar or _latest_osint_sidecar(pdir)

    if master_path is None or not master_path.exists():
        sys.stderr.write(f"error: master not found: {master_path}\n")
        return 2
    if sidecar_path is None or not sidecar_path.exists():
        sys.stderr.write(f"error: OSINT sidecar not found: {sidecar_path}\n")
        return 2

    with pipeline_lock(args.pipeline, 'merge_osint'):
        master = json.loads(master_path.read_text())
        sidecar = json.loads(sidecar_path.read_text())
        stats = graft(master, sidecar, threshold=threshold)
        write_atomic(master_path, master)

    print(f"  threshold        : {threshold}", file=sys.stderr)
    print(f"  grafted          : {stats['grafted']}", file=sys.stderr)
    print(f"  skipped (below)  : {stats['skipped_below_threshold']}", file=sys.stderr)
    print(f"  skipped (filled) : {stats['skipped_existing_value']}", file=sys.stderr)
    print(f"wrote {master_path}", flush=True)
    print(f"next: /outreach {args.pipeline} classify", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
