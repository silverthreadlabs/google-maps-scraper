#!/usr/bin/env python3
"""Incremental processor for the Kyiv/Lviv/Dnipro grid scrapes.

Reads whatever NDJSON exists, filters to software-relevant categories,
dedupes by place_id across cities, prints stats, and writes a combined
filtered file. Idempotent — safe to run repeatedly while scrapes run.
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent
CITIES = [
    ("kyiv",   ROOT / "software_kyiv_grid.json"),
    ("lviv",   ROOT / "software_lviv_grid.json"),
    ("dnipro", ROOT / "software_dnipro_grid.json"),
]
OUT = ROOT / "software_ua_combined.json"

SOFTWARE_CATEGORIES = {
    "Software company",
    "Computer service",
    "Computer consultant",
    "Internet marketing service",
    "Marketing agency",
    "Advertising agency",
    "Web designer",
    "Website designer",
    "Graphic designer",
    "Design agency",
    "Mobile application development company",
    "Information technology company",
    "Business management consultant",
    "Consultant",
    "Automation company",
    "E commerce agency",
}


def main() -> None:
    seen: dict[str, dict] = {}
    per_city = Counter()
    per_cat = Counter()
    excluded = Counter()

    for city, path in CITIES:
        if not path.exists():
            print(f"  [pending] {city}: {path.name} (not yet created)")
            continue
        rows = 0
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                rows += 1
                cat = rec.get("category") or ""
                if cat not in SOFTWARE_CATEGORIES:
                    excluded[cat] += 1
                    continue
                pid = rec.get("place_id") or rec.get("cid") or rec.get("link")
                if not pid or pid in seen:
                    continue
                rec["_city"] = city
                seen[pid] = rec
                per_city[city] += 1
                per_cat[cat] += 1
        print(f"  [done?]   {city}: {rows} total lines, {per_city[city]} kept")

    print()
    print(f"Total unique software leads: {len(seen)}")
    print()
    print("Per city:")
    for city, n in per_city.most_common():
        print(f"  {city:<8} {n}")
    print()
    print("Per category (kept):")
    for c, n in per_cat.most_common():
        print(f"  {n:<5} {c}")
    print()
    print(f"Excluded categories (top 10) — review for misses:")
    for c, n in excluded.most_common(10):
        print(f"  {n:<5} {c or '(blank)'}")

    with OUT.open("w") as f:
        for rec in seen.values():
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    em = sum(1 for r in seen.values() if r.get("emails"))
    web = sum(1 for r in seen.values() if r.get("web_site"))
    ph = sum(1 for r in seen.values() if r.get("phone"))
    n = len(seen) or 1
    print(f"\nCoverage: email {em}/{n} ({em*100//n}%)  website {web}/{n} ({web*100//n}%)  phone {ph}/{n} ({ph*100//n}%)")
    print(f"Wrote {OUT.name}")


if __name__ == "__main__":
    main()
