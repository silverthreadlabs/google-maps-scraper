"""Automotive SF Bay Area — campaign overrides on verticals/automotive/config.py.

Mirrors the software_ua_v2 pattern: the vertical default already targets the
buyer (owner / GM / service manager) in its OSINT POC query, so this file only
(a) pins the person-level decision-maker fields the osint gap-detector should
always chase, and (b) reserves a slot for Bay-Area-specific franchise/chain
brands once we have evidence of which regional multi-location operators recur
in the scrape.

Honest fit note: STL's voice-AI / inbound-coverage pitch fits auto repair
well — missed calls, dropped quotes, and surprise billing are the signature
pains (mains 1, 3, 4). Expect F1 in the dental ballpark (~0.78), higher than
the B2B-software campaigns, because auto-shop reviews discuss response-speed
and billing pain directly rather than project-delivery pain.
"""
from __future__ import annotations

import re

# ── Decision-maker targeting (campaign-scoped) ──────────────────────────
# The reachable buyer at an independent auto shop is the owner / general
# manager / service manager. Pin the person-level fields explicitly so the
# osint gap-detector keeps chasing them even if the vertical default shifts.
# (The vertical's OSINT_SERP_QUERIES already biases linkedin_url_poc toward
# these roles; campaign_config overlays per-key, so we don't repeat it here.)
OSINT_FIELDS_DESIRED = [
    "linkedin_url_poc", "poc_name", "poc_email", "poc_role",
]

# ── Region-specific chains ──────────────────────────────────────────────
# National automotive chains live in verticals/automotive/config.py and cover
# the bulk of Bay-Area franchise locations (Jiffy Lube, Midas, Caliber
# Collision, AutoZone, Enterprise, CarMax, …). Below are NorCal-specific
# multi-location operators the national regex misses, verified as genuine
# Bay-Area chains (CLAUDE.md rule 6 — region-specific brands belong here):
#
#   Wheel Works          — the Bay Area's largest tire/auto chain (est. 1976,
#                          Bridgestone-owned), many SF + East Bay + Peninsula
#                          stores. Domain wheelworks.net.
#   Stress-Free Auto Care — 15+ Bay Area locations (multiple in SF), Peninsula
#                          + East Bay + South Bay. Domain stressfree.com.
DSO_TITLE_REGEX_EXTRA = re.compile(
    r'\b('
    r'Wheel Works|'
    r'Stress-?Free Auto Care'
    r')\b', re.I,
)

DSO_EMAIL_DOMAINS_EXTRA = {
    'wheelworks.net',
    'stressfree.com',
}
