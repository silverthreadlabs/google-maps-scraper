#!/usr/bin/env python3
"""Merge 15 classify-batch outputs into the sidecar schema expected by
merge_classifications.py.

Joins agent output (id -> categories) against review_index (id -> place_id,
rating, reviewer, snippet) to emit sidecar keyed by place_id and main.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

ROOT = Path("outreach/pipelines/software_ua")
BATCH_DIR = ROOT / "enrichment/pain_classifications/2026-05-22_batches"
INDEX = ROOT / "enrichment/pain_classifications/2026-05-22_review_index.json"
SIDECAR = ROOT / "enrichment/pain_classifications/2026-05-22.json"


def main() -> None:
    index = {int(k): v for k, v in json.load(INDEX.open()).items()}

    sidecar: dict[str, dict[str, list[dict]]] = {}
    all_confidences: list[float] = []
    hits_by_main: dict[str, int] = {}

    for path in sorted(BATCH_DIR.glob("batch_*_out.json")):
        data = json.load(path.open())
        rows = data if isinstance(data, list) else data.get("results", data)
        for row in rows:
            rid = row["id"]
            cats = row.get("categories") or []
            meta = index.get(rid)
            if not meta:
                continue
            pid = meta["place_id"]
            for cat in cats:
                main = cat["main"]
                conf = float(cat.get("confidence") or 0)
                all_confidences.append(conf)
                hits_by_main[main] = hits_by_main.get(main, 0) + 1
                sidecar.setdefault(pid, {}).setdefault(main, []).append({
                    "sub":        cat.get("sub"),
                    "confidence": conf,
                    "snippet":    meta["snippet"],
                    "rating":     meta["rating"],
                    "reviewer":   meta["reviewer"],
                    "quote":      cat.get("quote"),
                    "reasoning":  cat.get("reasoning"),
                })

    tmp = SIDECAR.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2))
    tmp.replace(SIDECAR)

    total_hits = sum(hits_by_main.values())
    print(f"Sidecar: {SIDECAR}")
    print(f"Leads with hits: {len(sidecar)}")
    print(f"Total hits: {total_hits}")
    print(f"Mean confidence: {mean(all_confidences):.3f}" if all_confidences else "Mean confidence: n/a")
    print(f"\nHits per main:")
    for m, n in sorted(hits_by_main.items(), key=lambda x: -x[1]):
        print(f"  {n:>3}  {m}")


if __name__ == "__main__":
    main()
