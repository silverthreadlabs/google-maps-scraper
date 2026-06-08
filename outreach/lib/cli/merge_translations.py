"""
Merge a translation sidecar into a campaign's master.json.

Grafts `snippet_en` onto each agent_pain_hits[*] whose snippet was translated,
matched by (place_id, snippet_key). Provenance per outreach/CLAUDE.md rule 1;
atomic write. Idempotent — re-running re-applies the same English text.

Sidecar shape (produced by the translator subagent over the *_request.json):
    { "<place_id>": { "<snippet_key>": "<english text>" } }

Usage:
    python outreach/lib/cli/merge_translations.py \\
        --master  .../outputs/<date>/master.json \\
        --sidecar .../enrichment/translations/<date>.json \\
        --out     .../outputs/<date>/master.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.cli.translate import snippet_key

PROVENANCE_TAG = 'translator-subagent'


def merge(master: list[dict], sidecar: dict[str, dict]) -> dict:
    """Mutate `master` in place; return stats. Each translated snippet gets
    snippet_en + provenance on its hit."""
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    translated = 0
    leads_touched = 0
    for lead in master:
        pid = lead.get('place_id')
        by_key = sidecar.get(pid) if pid else None
        if not by_key:
            continue
        lead_hit = False
        for hits in (lead.get('agent_pain_hits') or {}).values():
            for hit in hits:
                key = snippet_key(hit.get('snippet') or '')
                english = by_key.get(key)
                if english:
                    hit['snippet_en'] = english
                    hit['snippet_en_source'] = PROVENANCE_TAG
                    hit['snippet_en_added_at'] = now
                    translated += 1
                    lead_hit = True
        if lead_hit:
            leads_touched += 1
    return {'snippets_translated': translated, 'leads_touched': leads_touched}


def write_atomic(path: Path, master: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(master, indent=2, ensure_ascii=False))
    tmp.replace(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Graft a translation sidecar into master.json.')
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
        sys.stderr.write("error: master must be a JSON array of leads\n")
        return 2
    if not isinstance(sidecar, dict):
        sys.stderr.write("error: sidecar must be a JSON object keyed by place_id\n")
        return 2

    stats = merge(master, sidecar)
    write_atomic(args.out, master)
    print(f"  snippets translated: {stats['snippets_translated']}", file=sys.stderr)
    print(f"  leads touched      : {stats['leads_touched']}", file=sys.stderr)
    print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
