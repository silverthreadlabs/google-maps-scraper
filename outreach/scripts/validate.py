"""
Run email + phone + POC validators against a pipeline's master JSON.

Annotates invalid values with sibling flags (per the never-drop rule in
outreach/CLAUDE.md):

  emails_invalid       — list[{email, reason}], appended (existing entries
                         preserved; new invalids deduped by email).
  phone_invalid        — bool sibling flag.
  phone_invalid_reason — short reason tag.
  pocs[*].invalid      — bool flag set in-place on each POC dict whose
                         `name` looks like a section heading or role label.
  pocs[*].invalid_reason — short reason tag.

Pipeline config:
  METRO_AREA_CODES        (required for metro-mismatch phone check)
  VENDOR_DOMAINS_EXTRA    (optional — extends the lib's generic vendor set)

Defaults to the latest dated outputs/ folder. Override with --master.

Usage:
  python outreach/scripts/validate.py <pipeline> [--master PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.validators.email import validate_email
from lib.validators.phone import validate_phone
from lib.validators.poc import validate_poc
from scripts._common import (
    add_pipeline_arg,
    load_pipeline_config,
    pipeline_dir,
    pipeline_lock,
)


def latest_master(pdir: Path) -> Path | None:
    """Return the master.json under the most recent outputs/<date>/, or None."""
    out = pdir / 'outputs'
    if not out.is_dir():
        return None
    for d in sorted((p for p in out.iterdir() if p.is_dir()), reverse=True):
        m = d / 'master.json'
        if m.exists():
            return m
    return None


def annotate_emails(lead: dict, *, extra_vendor_domains: frozenset[str]) -> int:
    """Append new invalid-email entries to lead['emails_invalid']. Returns count added."""
    existing = list(lead.get('emails_invalid') or [])
    seen = {e['email'].lower() for e in existing if isinstance(e, dict) and e.get('email')}
    candidates = list(lead.get('emails') or []) + list(lead.get('crawled_emails') or [])
    added = 0
    for em in candidates:
        if not isinstance(em, str) or em.lower() in seen:
            continue
        ok, reason = validate_email(em, extra_vendor_domains=extra_vendor_domains)
        if not ok:
            existing.append({'email': em, 'reason': reason})
            seen.add(em.lower())
            added += 1
    if added:
        lead['emails_invalid'] = existing
    return added


def annotate_phone(lead: dict, *, metro_area_codes: dict | None) -> bool:
    """Set phone_invalid + phone_invalid_reason siblings. Returns True if invalid."""
    ok, reason = validate_phone(
        lead.get('phone'),
        lead.get('metro'),
        metro_area_codes=metro_area_codes,
    )
    lead['phone_invalid'] = not ok
    lead['phone_invalid_reason'] = reason or ''
    return not ok


def annotate_pocs(lead: dict) -> int:
    """Set `invalid` + `invalid_reason` on each POC dict whose name is a
    section heading or role label. Mutates in-place. Returns count newly
    flagged (skips POCs already marked invalid)."""
    flagged = 0
    for poc in lead.get('pocs') or []:
        if not isinstance(poc, dict) or poc.get('invalid'):
            continue
        ok, reason = validate_poc(poc.get('name'))
        if not ok:
            poc['invalid'] = True
            poc['invalid_reason'] = reason or ''
            flagged += 1
    return flagged


def write_atomic(path: Path, leads: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(leads, indent=2, ensure_ascii=False))
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Validate emails+phones in a pipeline master; annotate invalid values via sibling flags.',
    )
    add_pipeline_arg(parser)
    parser.add_argument(
        '--master', type=Path, default=None,
        help='master JSON (default: outputs/<latest-date>/master.json)',
    )
    args = parser.parse_args(argv)

    cfg = load_pipeline_config(args.pipeline)
    extra_vendor = getattr(cfg, 'VENDOR_DOMAINS_EXTRA', frozenset())
    metros = getattr(cfg, 'METRO_AREA_CODES', None)

    pdir = pipeline_dir(args.pipeline)
    master_path = args.master or latest_master(pdir)
    if master_path is None or not master_path.exists():
        sys.stderr.write(
            f"error: master not found "
            f"(checked {args.master if args.master else f'{pdir}/outputs/<latest>/master.json'})\n"
        )
        return 2

    with pipeline_lock(args.pipeline, 'validate'):
        leads = json.loads(master_path.read_text())
        n_email_added = 0
        n_phone_bad = 0
        n_pocs_flagged = 0
        for lead in leads:
            n_email_added += annotate_emails(lead, extra_vendor_domains=extra_vendor)
            if annotate_phone(lead, metro_area_codes=metros):
                n_phone_bad += 1
            n_pocs_flagged += annotate_pocs(lead)

        write_atomic(master_path, leads)

    print(
        f"validated {len(leads)} leads → +{n_email_added} email invalid, "
        f"{n_phone_bad} phones marked invalid, "
        f"{n_pocs_flagged} POCs marked invalid → {master_path}",
        flush=True,
    )
    print(f"next: /outreach {args.pipeline} handoff", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
