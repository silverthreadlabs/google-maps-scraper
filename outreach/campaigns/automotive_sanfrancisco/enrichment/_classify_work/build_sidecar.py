"""Join pain-classifier batch outputs to review_index -> sidecar keyed by place_id.

Sidecar schema matches lib/cli/merge_classifications.py SIDECAR SCHEMA:
  { "<place_id>": { "<main>": [ {sub, confidence, snippet, rating, reviewer, reasoning} ] } }
Also validates: out-file ids subset of batch input ids, reports coverage and confidence stats.
Mirrors automotive_dallas/_classify_work/build_sidecar.py (sidecar date 2026-06-15).
"""
from __future__ import annotations
import json, glob, os, collections, statistics
from pathlib import Path

WORK = Path(__file__).resolve().parent
review_index = json.load(open(WORK / 'review_index.json'))
batch_dir = WORK / 'batches'
out_dir = WORK / 'batches_out'

# expected ids per batch (from input)
expected_ids = {}
for bf in sorted(glob.glob(str(batch_dir / 'batch_*.json'))):
    name = os.path.basename(bf).replace('.json', '')
    rows = json.load(open(bf))
    expected_ids[name] = {r['id'] for r in rows}

sidecar = {}
all_confidences = []
hits_by_main = collections.Counter()
total_hits = 0
problems = []
covered_ids = set()

for name, ids in sorted(expected_ids.items()):
    of = out_dir / f'{name}.out.json'
    if not of.exists():
        problems.append(f'{name}: MISSING output')
        continue
    try:
        data = json.load(open(of))
    except json.JSONDecodeError as e:
        problems.append(f'{name}: JSON error {e}')
        continue
    out_ids = set()
    for rec in data:
        rid = rec.get('id')
        out_ids.add(rid)
        cats = rec.get('categories') or []
        meta = review_index.get(str(rid))
        if meta is None:
            problems.append(f'{name}: id {rid} not in review_index')
            continue
        pid = meta['place_id']
        for cat in cats:
            main = cat.get('main')
            if not main:
                continue
            conf = cat.get('confidence')
            try:
                conf = float(conf)
            except (TypeError, ValueError):
                conf = None
            entry = {
                'sub':        cat.get('sub'),
                'confidence': conf,
                'snippet':    meta['snippet'],       # FULL review text
                'rating':     meta['rating'],
                'reviewer':   meta['reviewer'],
                'reasoning':  cat.get('reasoning', ''),
            }
            sidecar.setdefault(pid, {}).setdefault(main, []).append(entry)
            hits_by_main[main] += 1
            total_hits += 1
            if conf is not None:
                all_confidences.append(conf)
    stray = out_ids - ids
    if stray:
        problems.append(f'{name}: {len(stray)} out-of-range ids: {sorted(stray)[:5]}')
    covered_ids |= (out_ids & ids)

# write sidecar
sidecar_path = WORK.parent / 'pain_classifications' / '2026-06-15.json'
sidecar_path.parent.mkdir(parents=True, exist_ok=True)
tmp = sidecar_path.with_suffix('.json.tmp')
tmp.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2))
tmp.rename(sidecar_path)

all_expected = set().union(*expected_ids.values()) if expected_ids else set()
print(f'batches processed   : {len(expected_ids)}')
print(f'reviews covered     : {len(covered_ids)} / {len(all_expected)}')
print(f'leads with hits     : {len(sidecar)}')
print(f'total hits          : {total_hits}')
print(f'mean confidence     : {statistics.mean(all_confidences):.3f}' if all_confidences else 'mean confidence: n/a')
print(f'hits by main        :')
for m, c in hits_by_main.most_common():
    print(f'    {m:32s} {c}')
print(f'problems            : {len(problems)}')
for p in problems[:30]:
    print(f'    ! {p}')
print(f'sidecar -> {sidecar_path}')
