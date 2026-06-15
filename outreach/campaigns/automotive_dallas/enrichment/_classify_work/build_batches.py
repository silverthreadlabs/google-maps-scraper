"""One-off batch builder for the automotive_dallas classify stage.

Builds review_index.json (id -> {place_id, rating, reviewer, snippet}) and
batch_NNN.json files (each a list of {id, text}) for the pain-classifier
subagent. Selection source = master independents; reviews source = raw NDJSON.
Follows the /outreach classify runbook (merge user_reviews + extended, dedupe,
rating<=3 filter, full review text, batches of BATCH_SIZE).
"""
from __future__ import annotations
import json, math
from pathlib import Path

CAMP = Path(__file__).resolve().parents[2]   # campaigns/automotive_dallas
RAW = CAMP / 'raw' / 'automotive_dallas.json'
MASTER = CAMP / 'outputs' / '2026-06-12' / 'master.json'
WORK = Path(__file__).resolve().parent
BATCH_SIZE = 40

# index raw by place_id
raw = {}
for line in RAW.open():
    line = line.strip()
    if not line:
        continue
    d = json.loads(line)
    pid = d.get('place_id')
    if pid:
        raw[pid] = d

leads = json.load(MASTER.open())
independents = [l for l in leads if not l.get('is_chain_or_dso')]
independents.sort(key=lambda l: -(l.get('quality_score') or 0))

review_index = {}
rows = []          # {id, text}
next_id = 0
leads_with_reviews = 0

for lead in independents:
    pid = lead.get('place_id')
    d = raw.get(pid, {})
    seen = set()
    merged = (d.get('user_reviews') or []) + (d.get('user_reviews_extended') or [])
    kept = 0
    for rev in merged:
        text = rev.get('description') or rev.get('Description') or ''
        if not text:
            continue
        rating_s = rev.get('rating') or rev.get('Rating') or ''
        reviewer = rev.get('reviewer_name') or rev.get('Name') or ''
        try:
            rating = int(rating_s)
        except (TypeError, ValueError):
            rating = None
        key = (reviewer, text[:120])
        if key in seen:
            continue
        seen.add(key)
        # pain signal concentrated at rating<=3; None kept
        if rating is not None and rating > 3:
            continue
        rid = next_id
        next_id += 1
        review_index[str(rid)] = {
            'place_id': pid,
            'rating': rating,
            'reviewer': reviewer,
            'snippet': text,          # FULL text, never truncated
        }
        rows.append({'id': rid, 'text': text})
        kept += 1
    if kept:
        leads_with_reviews += 1

# write review_index
(WORK / 'review_index.json').write_text(json.dumps(review_index, ensure_ascii=False))

# write batches
n_batches = math.ceil(len(rows) / BATCH_SIZE)
batch_dir = WORK / 'batches'
batch_dir.mkdir(exist_ok=True)
for i in range(n_batches):
    chunk = rows[i * BATCH_SIZE:(i + 1) * BATCH_SIZE]
    (batch_dir / f'batch_{i:03d}.json').write_text(json.dumps(chunk, ensure_ascii=False))

print(f'independents selected   : {len(independents)}')
print(f'leads with kept reviews  : {leads_with_reviews}')
print(f'total reviews (id rows)  : {len(rows)}')
print(f'batches @ {BATCH_SIZE}            : {n_batches}')
print(f'review_index -> {WORK / "review_index.json"}')
print(f'batches      -> {batch_dir}/batch_000.json .. batch_{n_batches-1:03d}.json')
