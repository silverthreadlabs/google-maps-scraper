"""HVAC Tampa Bay — campaign overrides on verticals/hvac/config.py.

AssistantDial pilot campaign. The vertical default already carries the
client-fit pain weights (calls_unanswered / booking_friction heavy) and the
national PE/franchise chain regex, so this file only reserves the slot for
Tampa Bay-specific multi-location operators.

Region-specific chains: populate from what analyze surfaces, don't guess
(CLAUDE.md rule 6). Known candidates to check against the data:
    Red Cap, CoolToday, IERNA, Bayonet (Del-Air / Air Pros already in the
    vertical regex).
Once evidence exists:
    import re
    DSO_TITLE_REGEX_EXTRA = re.compile(r'\\b(Some Regional Chain)\\b', re.I)
    DSO_EMAIL_DOMAINS_EXTRA = {'someregionalchain.com'}
"""
from __future__ import annotations

import re

# Surfaced by 2026-07-04 decision-maker research (all evidence-based):
# - And Services (Alexa Air LLC): ~7-location multi-service regional platform.
# - CoolToday: PE-owned (acquired by Wrench Group, 2019).
# - Universal Air & Heat: acquired by Air Pros USA (airprosusa.com press
#   release, 2022); still listed under its own name on Maps.
# - Integrity Home Solutions: absorbed into PE-backed Frank Gay Home Services
#   after founder sold in 2021 (BBB profile at the Integrity URL now shows
#   Frank Gay at the same Tampa address).
DSO_TITLE_REGEX_EXTRA = re.compile(
    r'\b('
    r'And Services|CoolToday|Cool Today|Universal Air (?:&|and) Heat|'
    r'Integrity Home Solutions|Frank Gay'
    r')\b', re.I,
)
DSO_EMAIL_DOMAINS_EXTRA = {
    'andservices.com',
    'cooltoday.com',
    'universalairandheat.com',
    'integrityhomesolutions.com',
    'frankgayservices.com',
}

# AssistantDial now A/B-tests PHONE and EMAIL outreach in parallel, and has
# redefined the best lead as "a validated phone number AND a good-quality,
# genuinely reachable email" (user decision 2026-07-31, DDD-0004). The profile
# keeps DDD-0002's 25-point callable gate exactly — a callable lead still
# clears the C line — and scores email quality on the E-ladder beside it.
#
# Was 'phone_first' (DDD-0002, 2026-07-04). hvac_phoenix stays on phone_first
# until its website crawl has run: it has no email evidence to score yet, so
# flipping it today would cost 92 B->C demotions and buy 4 (DDD-0004 §6).
#
# Grade once, after ALL enrichment finishes (DDD-0004 §4b): email coverage now
# drives the grade, so a partially enriched master grades systematically low.
REACHABILITY_PROFILE = 'phone_email_parallel'
