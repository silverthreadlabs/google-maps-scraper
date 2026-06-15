#!/usr/bin/env python3
"""Build the website-crawl queue for automotive_sanfrancisco.

Queues every lead that has a website, deduped by hostname (one
representative — the highest quality_score — per site). merge_crawl joins
the crawl payload back onto every master row sharing that hostname, so
crawling one representative covers all listings of a multi-location site.
Leads with no website are skipped (nothing to crawl).
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path("outreach/campaigns/automotive_sanfrancisco")


def hostname(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def main() -> None:
    master = json.loads((ROOT / "outputs/2026-06-15/master.json").read_text())
    leads = master.get("leads") if isinstance(master, dict) else master

    by_host: dict[str, dict] = {}
    no_site = 0
    for l in leads:
        site = l.get("website") or ""
        host = hostname(site)
        if not host:
            no_site += 1
            continue
        # keep the highest quality_score lead as the host representative
        cur = by_host.get(host)
        if cur is None or (l.get("quality_score") or 0) > (cur.get("quality_score") or 0):
            by_host[host] = l

    queue = [
        {
            "place_id": l["place_id"],
            "title": l.get("title", ""),
            "website": l.get("website", ""),
            "metro": l.get("metro"),
            "address": l.get("address", ""),
            "quality_score": l.get("quality_score"),
        }
        for l in by_host.values()
    ]
    queue.sort(key=lambda x: -(x.get("quality_score") or 0))

    out = ROOT / "enrichment/crawl_queue.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(queue, ensure_ascii=False, indent=2))
    print(f"leads with website: {len(leads) - no_site} | no website (skipped): {no_site}")
    print(f"unique hostnames (queued): {len(queue)}")
    print(f"wrote queue -> {out}")


if __name__ == "__main__":
    main()
