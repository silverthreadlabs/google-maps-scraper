"""Graft confident OSINT hits into master.json with full provenance.

Reads enrichment/osint/<date>.json (judged by osint-binder subagent),
filters by confidence threshold, applies validators at the boundary
(per outreach/CLAUDE.md rule 5), respects immutability (rule 1).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
