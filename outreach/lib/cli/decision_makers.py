"""
decision-makers — unified people enrichment (manual / subagent-research flow).

Collapses the old `owner-lookup` (single owner -> scalars) and `contacts`
(team -> pocs[]) stages into one. A single research pass per company captures
the owner AND the rest of the reachable team — CTO / tech lead, sales /
business-development / partnerships — each as an entry in `pocs[]` with
whatever channels exist (LinkedIn / X / Instagram / Facebook / personal email).

Exactly one person is the **primary** decision-maker (the ICP buyer). The
researcher marks them with `primary: true`; absent that we fall back to a
role-keyword match (founder / owner / CEO / ...), then to the first person.
The `owner_name` / `owner_title` / `owner_linkedin` scalars — which feed the
CRM "Decision Maker" panel and the handoff `primary_contact` — become a
**derived projection** of that primary POC. push_leads forwards both the
scalars and `pocs[]` (with per-POC `socials`), so every channel rides along.

Bracketed like the stages it replaces so the manual lift stays idempotent and
provenance-clean:

  1. `--print-queue`  — emit eligible leads (tier A/B/C with a website) with a
                        research brief: company, website, who we already have,
                        and the roles to chase (incl. marking the primary).
  2. <fill the sidecar at  enrichment/decision_makers/<date>.json>  keyed by
     place_id to a LIST of people (a bare dict is accepted as a single primary,
     for owner-lookup back-compat):
        {"<place_id>": [
           {"name": "...", "role": "Founder", "primary": true,
            "linkedin": "...", "twitter": "...", "instagram": "...",
            "facebook": "...", "email": "...", "confidence": 0.9,
            "evidence": "..."}, ...]}
  3. `--apply`         — append/merge people into `pocs[]` with provenance,
                        designate the primary, project owner_* scalars.

  `--backfill-owner-pocs` — no sidecar; materialize an owner POC from existing
                        owner_* scalars on any lead that has an owner but no
                        owner POC (migrates leads enriched before this stage).

CLAUDE.md rule 1: existing pocs are preserved; re-found people MERGE channels.
Idempotency is keyed on "is there an owner POC?", not "is owner_name set?", and
an existing owner_name is never clobbered.

Usage:
  python outreach/lib/cli/decision_makers.py <pipeline> --print-queue \\
      [--limit N] [--tiers A,B,C] [--master PATH]

  python outreach/lib/cli/decision_makers.py <pipeline> --apply \\
      [--sidecar PATH] [--master PATH] [--min-confidence 0.5]

  python outreach/lib/cli/decision_makers.py <pipeline> --backfill-owner-pocs \\
      [--master PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.cli._common import add_pipeline_arg, pipeline_dir, pipeline_lock
from lib.cli._pocs import (
    merge_channels_into_poc,
    norm_name,
    norm_url,
    owner_scalars_from_poc,
    pick_primary_index,
    poc_from_person,
)

POC_SOURCE = 'decision_maker_research'
OWNER_SOURCE = 'decision_maker_primary'
BACKFILL_SOURCE = 'owner_scalar_backfill'
DEFAULT_MIN_CONFIDENCE = 0.5
ROLES_WANTED = ('the primary buyer (founder / owner / CEO — mark primary:true) '
                '+ CTO / tech lead + sales / business-development / partnerships')


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
    tiers=('A', 'B', 'C'),
    require_website: bool = True,
    limit: int | None = None,
) -> list[dict]:
    """Eligible leads for a research pass: in `tiers`, with a website (when
    required), sorted by quality_score desc. We do NOT require an empty owner —
    the pass captures the whole team, and a re-pass augments channels."""
    tiers = set(tiers)
    eligible = [
        l for l in master
        if l.get('tier') in tiers
        and (not require_website or (l.get('website') or l.get('web_site')))
    ]
    eligible.sort(key=lambda l: -(l.get('quality_score') or 0))
    return eligible[:limit] if limit is not None else eligible


def print_queue(queue: list[dict], file=sys.stdout) -> None:
    for l in queue:
        pid = l.get('place_id') or ''
        tier = l.get('tier') or ''
        qs = l.get('quality_score')
        owner = (l.get('owner_name') or '').strip()
        existing = [p.get('name') for p in (l.get('pocs') or []) if p.get('name')]
        print(f'[{tier} qs={qs}]  place_id={pid}', file=file)
        print(f'  company : {l.get("title") or ""}', file=file)
        print(f'  website : {l.get("website") or l.get("web_site") or "—"}', file=file)
        print(f'  have owner: {owner or "—"}', file=file)
        if existing:
            print(f'  have pocs : {"; ".join(existing)}', file=file)
        print(f'  find: {ROLES_WANTED}', file=file)
        print('', file=file)
    print(f'# {len(queue)} lead(s). Fill the sidecar keyed by place_id with a LIST of '
          f'people (mark the buyer with "primary": true):\n'
          f'#   {{"<place_id>": [{{"name","role","primary","linkedin","twitter",'
          f'"instagram","facebook","email","confidence","evidence"}}]}}\n'
          f'# then run --apply.', file=file)


def _normalize_people(entry) -> list[dict]:
    """Accept either a LIST of people (decision-makers / contacts shape) or a
    bare DICT (legacy owner-lookup `{name,title,linkedin}` — a single primary)."""
    if isinstance(entry, dict):
        # Legacy owner-lookup dict — hand-curated and trusted, so it predates
        # the confidence floor; default it to pass.
        person = {**entry, 'primary': True}
        person.setdefault('confidence', 1.0)
        return [person]
    return list(entry or [])


def _find_match(poc: dict, pocs: list[dict]) -> dict | None:
    """Return an existing POC that is the same person as `poc` (by normalized
    name, or by a shared LinkedIn URL), else None."""
    nkey = norm_name(poc.get('name'))
    li_keys = {norm_url(s) for s in (poc.get('socials') or []) if 'linkedin.com' in s.lower()}
    for existing in pocs:
        if nkey and norm_name(existing.get('name')) == nkey:
            return existing
        for s in existing.get('socials') or []:
            if 'linkedin.com' in s.lower() and norm_url(s) in li_keys:
                return existing
    return None


def _materialize_owner_poc_if_missing(lead: dict, *, now_iso: str) -> None:
    """If the lead carries an owner_name but no POC represents that person,
    synthesize one from the scalars (LinkedIn-only until research adds more).
    Keeps the owner present in pocs[] even on leads enriched before this
    stage existed."""
    owner_name = (lead.get('owner_name') or '').strip()
    if not owner_name:
        return
    pocs = lead.get('pocs') or []
    synthetic = poc_from_person(
        {'name': owner_name, 'title': lead.get('owner_title'),
         'linkedin': lead.get('owner_linkedin'), 'primary': True,
         'confidence': None},
        source=BACKFILL_SOURCE, now_iso=now_iso,
    )
    match = _find_match(synthetic, pocs)
    if match is None:
        lead['pocs'] = [synthetic] + pocs
    else:
        match['primary'] = True
        merge_channels_into_poc(match, synthetic)


def _designate_primary_and_project(lead: dict, *, now_iso: str) -> bool:
    """Pick the primary POC, move it to pocs[0], set its primary flag, and
    project owner_* scalars off it. Guards the scalar overwrite: an existing
    owner_name is preserved. Returns True if scalars were (re)derived."""
    pocs = lead.get('pocs') or []
    idx = pick_primary_index(pocs)
    if idx is None:
        return False
    for i, p in enumerate(pocs):
        p['primary'] = (i == idx)
    primary = pocs.pop(idx)
    lead['pocs'] = [primary] + pocs

    scalars = owner_scalars_from_poc(primary)
    derived = False
    if not (lead.get('owner_name') or '').strip():
        lead['owner_name'] = scalars['name']
        lead['owner_title'] = scalars['title']
        lead['owner_linkedin'] = scalars['linkedin']
        derived = True
    else:
        # Owner set by hand/old run — never clobber, but fill empty siblings.
        if not (lead.get('owner_title') or '').strip() and scalars['title']:
            lead['owner_title'] = scalars['title']
            derived = True
        if not (lead.get('owner_linkedin') or '').strip() and scalars['linkedin']:
            lead['owner_linkedin'] = scalars['linkedin']
            derived = True
    if derived:
        lead['owner_source'] = OWNER_SOURCE
        lead['owner_added_at'] = now_iso
    return derived


def apply_sidecar(
    master: list[dict],
    sidecar: dict,
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    now_iso: str | None = None,
) -> dict:
    """Append/merge researched people into each lead's pocs[] in place,
    designate the primary, and project owner_* scalars. Idempotent. Returns
    stats."""
    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    by_pid = {l.get('place_id'): l for l in master if l.get('place_id')}
    stats = {'appended': 0, 'merged': 0, 'skipped_lowconf': 0,
             'skipped_noname': 0, 'orphan': 0, 'orphan_pids': [],
             'owner_set': 0}
    for pid, entry in sidecar.items():
        lead = by_pid.get(pid)
        if lead is None:
            stats['orphan'] += 1
            stats['orphan_pids'].append(pid)
            continue
        pocs = list(lead.get('pocs') or [])
        for person in _normalize_people(entry):
            name = (person.get('name') or '').strip()
            if not name:
                stats['skipped_noname'] += 1
                continue
            conf = person.get('confidence')
            try:
                conf_f = float(conf) if conf is not None else 0.0
            except (TypeError, ValueError):
                conf_f = 0.0
            if conf_f < min_confidence:
                stats['skipped_lowconf'] += 1
                continue
            poc = poc_from_person(person, source=POC_SOURCE, now_iso=now_iso)
            match = _find_match(poc, pocs)
            if match is not None:
                merge_channels_into_poc(match, poc)
                stats['merged'] += 1
            else:
                pocs.append(poc)
                stats['appended'] += 1
        lead['pocs'] = pocs
        _materialize_owner_poc_if_missing(lead, now_iso=now_iso)
        if _designate_primary_and_project(lead, now_iso=now_iso):
            stats['owner_set'] += 1
    return stats


def backfill_owner_pocs(master: list[dict], *, now_iso: str | None = None) -> dict:
    """Materialize an owner POC from owner_* scalars on every lead that has an
    owner but no owner POC. No new research — migrates pre-existing data into
    the unified pocs[] model. Idempotent. Returns stats."""
    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    stats = {'synthesized': 0, 'scanned': 0}
    for lead in master:
        if not (lead.get('owner_name') or '').strip():
            continue
        stats['scanned'] += 1
        before = len(lead.get('pocs') or [])
        _materialize_owner_poc_if_missing(lead, now_iso=now_iso)
        _designate_primary_and_project(lead, now_iso=now_iso)
        if len(lead.get('pocs') or []) > before:
            stats['synthesized'] += 1
    return stats


def write_atomic(path: Path, master: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(master, indent=2, ensure_ascii=False))
    tmp.replace(path)


def _load_master(args) -> tuple[Path | None, list[dict] | None]:
    pdir = pipeline_dir(args.pipeline)
    master_path = args.master or latest_master(pdir)
    if master_path is None or not master_path.exists():
        sys.stderr.write(f"error: master not found: {master_path}\n")
        return None, None
    master = json.loads(master_path.read_text())
    if not isinstance(master, list):
        sys.stderr.write(f"error: master must be a JSON array: {master_path}\n")
        return None, None
    return master_path, master


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Unified decision-maker enrichment: queue printer + sidecar '
                    'applier + owner-POC backfill.',
    )
    add_pipeline_arg(parser)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--print-queue', action='store_true',
                      help='print research briefs for eligible leads')
    mode.add_argument('--apply', action='store_true',
                      help='read sidecar and append/merge people into pocs[]')
    mode.add_argument('--backfill-owner-pocs', action='store_true',
                      help='materialize owner POCs from existing owner_* scalars '
                           '(no sidecar; migrates pre-existing leads)')
    parser.add_argument('--limit', type=int, default=None,
                        help='cap the queue at top-N (default: no cap)')
    parser.add_argument('--tiers', default='A,B,C',
                        help='comma-separated tiers to include (default: A,B,C)')
    parser.add_argument('--no-require-website', action='store_true',
                        help='include leads without a website in the queue')
    parser.add_argument('--master', type=Path, default=None,
                        help='master JSON (default: outputs/<latest-date>/master.json)')
    parser.add_argument('--sidecar', type=Path, default=None,
                        help='sidecar JSON (default: enrichment/decision_makers/<today>.json)')
    parser.add_argument('--min-confidence', type=float, default=DEFAULT_MIN_CONFIDENCE,
                        help=f'drop people below this confidence (default: {DEFAULT_MIN_CONFIDENCE})')
    args = parser.parse_args(argv)

    pdir = pipeline_dir(args.pipeline)
    master_path, master = _load_master(args)
    if master is None:
        return 2

    if args.print_queue:
        tiers = tuple(t.strip().upper() for t in args.tiers.split(',') if t.strip())
        queue = select_queue(
            master, tiers=tiers,
            require_website=not args.no_require_website, limit=args.limit,
        )
        print_queue(queue)
        return 0

    if args.backfill_owner_pocs:
        with pipeline_lock(args.pipeline, 'decision_makers'):
            stats = backfill_owner_pocs(master)
            write_atomic(master_path, master)
        print(f"  owner POCs synthesized: {stats['synthesized']} "
              f"(of {stats['scanned']} leads with an owner)", file=sys.stderr)
        print(f"wrote {master_path}", flush=True)
        return 0

    today = datetime.now(timezone.utc).date().isoformat()
    sidecar_path = args.sidecar or (pdir / 'enrichment' / 'decision_makers' / f'{today}.json')
    if not sidecar_path.exists():
        sys.stderr.write(
            f"error: sidecar not found: {sidecar_path}\n"
            f"hint: --print-queue to see what's needed, then write the sidecar with the\n"
            f"shape  {{\"<place_id>\": [{{\"name\", \"role\", \"primary\", \"linkedin\", "
            f"\"email\", \"confidence\"}}]}}\n"
        )
        return 2

    sidecar = json.loads(sidecar_path.read_text())
    if not isinstance(sidecar, dict):
        sys.stderr.write(f"error: sidecar must be a JSON object keyed by place_id: {sidecar_path}\n")
        return 2

    with pipeline_lock(args.pipeline, 'decision_makers'):
        stats = apply_sidecar(master, sidecar, min_confidence=args.min_confidence)
        write_atomic(master_path, master)

    print(f"  people appended : {stats['appended']}", file=sys.stderr)
    print(f"  channels merged : {stats['merged']}", file=sys.stderr)
    print(f"  owner scalars   : {stats['owner_set']}", file=sys.stderr)
    print(f"  skipped (lowconf): {stats['skipped_lowconf']}", file=sys.stderr)
    print(f"  skipped (noname): {stats['skipped_noname']}", file=sys.stderr)
    print(f"  orphan place_ids: {stats['orphan']}", file=sys.stderr)
    if stats['orphan_pids']:
        sample = stats['orphan_pids'][:5]
        ellipsis = '…' if len(stats['orphan_pids']) > 5 else ''
        print(f"    first {len(sample)}: {sample}{ellipsis}", file=sys.stderr)
    print(f"wrote {master_path}", flush=True)
    print(f"next: re-push with push_leads.py (or /outreach {args.pipeline} handoff)", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
