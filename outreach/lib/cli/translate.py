"""
translate — build the translation-request sidecar for a campaign.

The translate stage is locale-gated (no-op for en-* campaigns) and selects the
pain snippets that will surface in the handoff (top-2 pain quotes per lead),
keeping only those that need translation (see lib.lang_detect). It writes a
request sidecar:

    enrichment/translations/<date>_request.json
    { "<place_id>": { "<snippet_key>": "<original snippet>", ... }, ... }

A translator subagent (dispatched by the /outreach skill) reads it and writes
the answer sidecar enrichment/translations/<date>.json with the same keys
mapped to English. merge_translations.py then grafts snippet_en onto master.

Usage:
    python outreach/lib/cli/translate.py <pipeline> [--output-date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.cli._common import (
    add_pipeline_arg, load_pipeline_config, pipeline_dir, pipeline_lock,
)
from lib.handoff.csv_builder import _pain_hits_field
from lib.lang_detect import needs_translation


def snippet_key(snippet: str) -> str:
    return hashlib.sha1((snippet or '').strip().encode('utf-8')).hexdigest()[:12]


def select_for_translation(master, *, locale, pain_weights=None):
    """Return {place_id: {snippet_key: original_snippet}} for EVERY pain-hit
    snippet that needs translation and isn't already translated. Pure; no I/O.

    Covers all pain hits, not just the top-2 the handoff CSV surfaces: the CRM
    push (push_leads) delivers the full pain-hits array, so every hit must be
    translated for the delivered leads to read in English. Hits already
    carrying `snippet_en` are skipped, so re-runs are idempotent. `pain_weights`
    is accepted for backward compatibility but no longer used (no ranking)."""
    out: dict[str, dict[str, str]] = {}
    for lead in master:
        pid = lead.get('place_id')
        if not pid:
            continue
        pain = _pain_hits_field(lead) or {}
        for _category, hits in pain.items():
            for hit in hits:
                snippet = (hit.get('snippet') or hit.get('quote') or '').strip()
                if not snippet:
                    continue
                if (hit.get('snippet_en') or '').strip():
                    continue  # already translated — idempotent re-run
                if not needs_translation(snippet, locale):
                    continue
                out.setdefault(pid, {})[snippet_key(snippet)] = snippet
    return out


def _latest_master(pdir: Path) -> Path | None:
    out_dir = pdir / 'outputs'
    if not out_dir.is_dir():
        return None
    dated = sorted(d for d in out_dir.iterdir() if d.is_dir())
    for d in reversed(dated):
        m = d / 'master.json'
        if m.exists():
            return m
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Build the translation-request sidecar.')
    add_pipeline_arg(parser)
    parser.add_argument('--master', type=Path, default=None)
    parser.add_argument('--output-date', default=None)
    args = parser.parse_args(argv)

    cfg = load_pipeline_config(args.pipeline)
    pdir = pipeline_dir(args.pipeline)
    master_path = args.master or _latest_master(pdir)
    if not master_path or not master_path.exists():
        sys.stderr.write(f"error: master not found for {args.pipeline}\n")
        return 2

    with pipeline_lock(args.pipeline, 'translate'):
        master = json.loads(Path(master_path).read_text())
        requests = select_for_translation(
            master, locale=cfg.locale, pain_weights=cfg.pain_weights
        )
        today = args.output_date or datetime.now(timezone.utc).strftime('%Y-%m-%d')
        req_dir = pdir / 'enrichment' / 'translations'
        req_dir.mkdir(parents=True, exist_ok=True)
        req_path = req_dir / f'{today}_request.json'
        tmp = req_path.with_suffix(req_path.suffix + '.tmp')
        tmp.write_text(json.dumps(requests, indent=2, ensure_ascii=False))
        tmp.replace(req_path)

    n_leads = len(requests)
    n_snips = sum(len(v) for v in requests.values())
    if cfg.locale.lower().startswith('en'):
        print(f"locale={cfg.locale!r} is English — nothing to translate (no-op).", flush=True)
    print(f"wrote {req_path} ({n_snips} snippet(s) across {n_leads} lead(s))", flush=True)
    print(f"next: dispatch the translator subagent over {req_path.name}, write "
          f"enrichment/translations/{today}.json, then run "
          f"merge_translations.py", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
