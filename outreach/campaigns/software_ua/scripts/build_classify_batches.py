#!/usr/bin/env python3
"""Build classify-stage inputs for the top-100 software_ua leads.

Reads master + raw NDJSONs. Filters master to software-whitelist /
non-chain / ≥3 reviews, takes top 100 by quality_score. Indexes reviews
from raw (merging user_reviews + user_reviews_extended, normalizing key
casing, deduping, filtering to rating ≤ 3). Splits into batches of 30
and writes them to enrichment/pain_classifications/2026-05-22_batches/.
Also writes the in-memory review_index as JSON so the merge step can
join subagent outputs back to place_id / rating / reviewer / snippet.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path("outreach/campaigns/software_ua")
MASTER = ROOT / "outputs/2026-05-22/master.json"
RAW_DIR = ROOT / "raw"
OUT_DIR = ROOT / "enrichment/pain_classifications/2026-05-22_batches"
INDEX_FILE = ROOT / "enrichment/pain_classifications/2026-05-22_review_index.json"

WHITELIST = {
    "Software company", "Computer service", "Computer consultant",
    "Internet marketing service", "Marketing agency", "Advertising agency",
    "Web designer", "Website designer", "Graphic designer", "Design agency",
    "Mobile application development company", "Information technology company",
    "Business management consultant", "Consultant", "Automation company",
    "E commerce agency",
}

# Foreign-shop pollution patterns. These Google-Maps listings register as
# Ukrainian businesses but are based abroad (typically India/Pakistan offshore
# shops that scrape Ukrainian Maps for visibility). Their reviews contain real
# pain but they aren't the target ICP.
FOREIGN_TITLE_TOKENS = {
    "pvt ltd", "pvt. ltd", "private ltd", "pvt limited",
    "pty ltd", "smc private", "limited liability company usa",
    # South Asian metros (appear in title or address of fake-UA listings)
    "rawalpindi", "lahore", "karachi", "islamabad",
    "mumbai", "delhi", "bangalore", "hyderabad", "chennai", "pune",
    "noida", "gurgaon", "ahmedabad", "kolkata", "jaipur", "indore",
    # Other cities seen as "registered HQ" of fake-UA shops
    "new york", "nyc", "london", "dubai", "manila",
}

# Country codes / country names in address that mean NOT-Ukraine (catches
# shops that registered a UA pin but list their real HQ in address).
NON_UA_ADDRESS_TOKENS = {
    "india", "pakistan", "bangladesh", "philippines",
    "usa", "united states", "u.s.a.", "u.s.",
    "united kingdom", "uae", "u.a.e.", "united arab",
}

# Brand patterns: shops we've confirmed via spot-check are not Ukrainian
# despite passing the token filters above. Manually maintained.
FOREIGN_BRANDS = {
    "radixweb",          # Indian shop, no Pvt Ltd marker
    "dd.nyc",            # NYC studio
    "unitedsol",         # Pakistani shop
    "viremp",            # Indian
    "immentia",          # Indian
    "online yourself",   # Pakistani ("Software House in Rawalpindi" handled by token but be safe)
    "10com web",         # appears to be US-based with foreign reviewers
}

# Software *products* miscategorized as "Software company" — they have
# end-user complaints (patients, account holders) rather than B2B client
# complaints. Manually maintained; add as found during spot-checks.
PRODUCT_EXCLUDE_TITLES = {
    "МІС Health24",      # healthcare records platform; complaints from patients
    "Auspex Streamline", # appears to be a product, not an agency
    "SEVEN",             # reviewed as a café, not a software shop (Google miscategorization)
}

BATCH_SIZE = 30
# Broadened scope (2026-05-22 v4): Ezly can be pitched to ANY Ukrainian software
# shop, not just ones with negative reviews. We classify only those with reviews
# (no pain signal without reviews), but the downstream handoff includes every
# software-whitelist lead — pain just lifts ranking for those that have it.
TOP_N = 99999             # effectively "all" (cap exists for safety)
MIN_REVIEWS = 1           # need at least 1 review to classify anything
INCLUDE_CHAINS = True     # include EPAM-tier outsourcers (user decision 2026-05-22)


def is_foreign_shop(title: str, address: str) -> bool:
    t = (title or "").lower()
    a = (address or "").lower()
    for tok in FOREIGN_TITLE_TOKENS:
        if tok in t or tok in a:
            return True
    for tok in NON_UA_ADDRESS_TOKENS:
        if tok in a:
            return True
    for brand in FOREIGN_BRANDS:
        if brand in t:
            return True
    return False


def normalize_review(rev: dict) -> tuple[str, int | None, str]:
    """Read review across capitalized + lowercase key variants."""
    text = rev.get("description") or rev.get("Description") or ""
    rating_s = rev.get("rating") or rev.get("Rating") or ""
    reviewer = rev.get("reviewer_name") or rev.get("Name") or ""
    try:
        rating = int(rating_s)
    except (ValueError, TypeError):
        rating = None
    return text, rating, reviewer


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    master = json.load(MASTER.open())
    leads = master.get("leads") if isinstance(master, dict) else master

    pre = [
        l for l in leads
        if (l.get("category") or "") in WHITELIST
        and (INCLUDE_CHAINS or not l.get("is_chain_or_dso"))
        and (l.get("review_count") or 0) >= MIN_REVIEWS
    ]
    dropped_foreign = [l for l in pre if is_foreign_shop(l.get("title",""), l.get("address",""))]
    dropped_products = [l for l in pre if (l.get("title") or "") in PRODUCT_EXCLUDE_TITLES]
    filtered = [
        l for l in pre
        if not is_foreign_shop(l.get("title",""), l.get("address",""))
        and (l.get("title") or "") not in PRODUCT_EXCLUDE_TITLES
    ]
    filtered.sort(key=lambda x: -(x.get("quality_score") or 0))
    selected = filtered[:TOP_N]
    selected_ids = {l["place_id"] for l in selected}
    print(f"Pre-filter pool: {len(pre)}")
    print(f"  dropped foreign shops: {len(dropped_foreign)} (e.g. {[l.get('title','')[:35] for l in dropped_foreign[:3]]})")
    print(f"  dropped products:      {len(dropped_products)} (e.g. {[l.get('title','')[:35] for l in dropped_products[:3]]})")
    print(f"Selected top {len(selected)} leads (of {len(filtered)} after filter)")

    raw_by_pid: dict[str, dict] = {}
    for path in sorted(RAW_DIR.glob("*.json")):
        for line in path.open():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            pid = rec.get("place_id")
            if pid in selected_ids and pid not in raw_by_pid:
                raw_by_pid[pid] = rec
    print(f"Found raw rows for {len(raw_by_pid)} / {len(selected)} selected leads")

    review_index: dict[int, dict] = {}
    batch_rows: list[dict] = []
    next_id = 0

    for lead in selected:
        pid = lead["place_id"]
        raw = raw_by_pid.get(pid)
        if not raw:
            continue
        merged = (raw.get("user_reviews") or []) + (raw.get("user_reviews_extended") or [])
        seen: set[tuple[str, str]] = set()
        for rev in merged:
            text, rating, reviewer = normalize_review(rev)
            if not text:
                continue
            key = (reviewer, text[:120])
            if key in seen:
                continue
            seen.add(key)
            if rating is not None and rating > 3:
                continue
            review_index[next_id] = {
                "place_id": pid,
                "rating": rating,
                "reviewer": reviewer,
                "snippet": text,
            }
            batch_rows.append({"id": next_id, "text": text})
            next_id += 1

    print(f"Built review index with {len(review_index)} reviews (rating ≤ 3 only)")

    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(review_index, ensure_ascii=False, indent=2))

    batches = [batch_rows[i:i + BATCH_SIZE] for i in range(0, len(batch_rows), BATCH_SIZE)]
    for i, batch in enumerate(batches):
        (OUT_DIR / f"batch_{i:03d}.json").write_text(json.dumps(batch, ensure_ascii=False, indent=2))
    print(f"Wrote {len(batches)} batches of up to {BATCH_SIZE} reviews each → {OUT_DIR}")
    print(f"Review index → {INDEX_FILE}")


if __name__ == "__main__":
    main()
