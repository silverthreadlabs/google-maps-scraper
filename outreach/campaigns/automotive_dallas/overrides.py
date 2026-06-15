"""Automotive Dallas / DFW — campaign overrides on verticals/automotive/config.py.

Same shape as automotive_sanfrancisco: the vertical default already targets the
buyer (owner / GM / service manager) in its OSINT POC query, so this file only
(a) pins the person-level decision-maker fields the osint gap-detector should
always chase, and (b) reserves a slot for DFW-specific franchise/chain brands
once analyze surfaces which regional multi-location operators recur in the data.

Fit note: STL's POC + socials + email outreach fits owner-operated DFW auto
shops well. National chains are excluded by the vertical regex; the campaign's
job is to surface the reachable independents.
"""
from __future__ import annotations

# ── Decision-maker targeting (campaign-scoped) ──────────────────────────
# Primary channel is POC + their socials, then email — so the person-level
# fields matter most. Pin them so the osint gap-detector keeps chasing them
# even if the vertical default shifts. (The vertical's OSINT_SERP_QUERIES
# already biases linkedin_url_poc toward owner/GM/service-manager roles;
# campaign_config overlays per-key, so we don't repeat it here.)
OSINT_FIELDS_DESIRED = [
    "linkedin_url_poc", "poc_name", "poc_email", "poc_role",
]

# ── Region-specific chains (reserved) ───────────────────────────────────
# National automotive chains live in verticals/automotive/config.py and cover
# the bulk of DFW franchise locations (Jiffy Lube, Christian Brothers, Caliber
# Collision, Discount Tire HQ'd in nearby Scottsdale but dense in TX, AutoZone,
# Enterprise, CarMax, …). If analyze surfaces a DFW-specific multi-location
# operator the national regex misses, add it here as DSO_TITLE_REGEX_EXTRA /
# DSO_EMAIL_DOMAINS_EXTRA — populate from the data, don't guess (CLAUDE.md
# rule 6). Example, once evidence exists:
#   import re
#   DSO_TITLE_REGEX_EXTRA = re.compile(r'\b(Some DFW Chain)\b', re.I)
#   DSO_EMAIL_DOMAINS_EXTRA = {'somedfwchain.com'}
