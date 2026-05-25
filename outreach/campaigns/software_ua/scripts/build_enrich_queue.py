#!/usr/bin/env python3
"""Build the full enrich-stage crawl queue.

Includes every WHITELIST-category lead (chains included, 0-review leads
included) minus foreign-shop pollution and known product misclassifications.
Skips leads with no website (nothing to crawl).
"""
from __future__ import annotations

import json
import sys
import importlib.util
from pathlib import Path

ROOT = Path("outreach/campaigns/software_ua")

spec = importlib.util.spec_from_file_location("bcb", ROOT / "build_classify_batches.py")
bcb = importlib.util.module_from_spec(spec); spec.loader.exec_module(bcb)


def main() -> None:
    master = json.load((ROOT / "outputs/2026-05-22/master.json").open())
    leads = master.get("leads") if isinstance(master, dict) else master

    pool = [
        l for l in leads
        if (l.get("category") or "") in bcb.WHITELIST
        and not bcb.is_foreign_shop(l.get("title",""), l.get("address",""))
        and (l.get("title") or "") not in bcb.PRODUCT_EXCLUDE_TITLES
    ]
    pool.sort(key=lambda x: -(x.get("quality_score") or 0))

    no_site = 0
    queue = []
    for l in pool:
        site = l.get("website") or l.get("web_site") or ""
        if not site:
            no_site += 1
            continue
        queue.append({
            "place_id": l["place_id"],
            "title": l.get("title",""),
            "website": site,
            "metro": l.get("metro"),
            "address": l.get("address",""),
        })

    out = ROOT / "enrichment/crawl_queue.json"
    out.write_text(json.dumps(queue, ensure_ascii=False, indent=2))
    print(f"Pool (whitelist + foreign-filter + product-filter): {len(pool)} leads")
    print(f"  with website (queued): {len(queue)}")
    print(f"  no website (skipped):  {no_site}")
    print(f"Wrote queue → {out}")


if __name__ == "__main__":
    main()
