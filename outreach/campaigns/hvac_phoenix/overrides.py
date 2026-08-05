"""HVAC Phoenix — campaign overrides on verticals/hvac/config.py.

AssistantDial pilot campaign. The vertical default already carries the
client-fit pain weights (calls_unanswered / booking_friction heavy) and the
national PE/franchise chain regex, so this file only reserves the slot for
Phoenix-specific multi-location operators.

Region-specific chains below were surfaced by the 2026-07-04 pilot analyze run
(all appeared in the raw scrape as multi-service PE/platform brands with their
own call centers — dead leads for an AI-receptionist pitch). Chas Roberts and
Howard Air remain candidates: not yet seen in the data, add when analyze
surfaces them.
"""
from __future__ import annotations

import re

DSO_TITLE_REGEX_EXTRA = re.compile(
    r'\b('
    r'Parker & Sons|George Brazil|Penguin Air|Day & Night Air|'
    r'Precision Air & Plumbing|Hobaica|Christian Brothers A/C|'
    # Still listed under its own name on Maps, but decision-maker research
    # (2026-07-04) confirmed it merged into Penguin Air / Any Hour Group.
    r'Chandler Air'
    r')\b', re.I,
)

DSO_EMAIL_DOMAINS_EXTRA = {
    'parkerandsons.com',
    'georgebrazil.com',
    'penguinair.com',
    'dayandnightair.com',
    'precisionairandplumbing.com',
    'hobaica.com',
    'cbrothers.com',
}

# AssistantDial outreaches by PHONE (reps cold-call; see verticals/hvac/README
# reachability rule). Scoped to this campaign per user decision 2026-07-04 —
# "phone_first model but just for this set" (DDD-0002).
REACHABILITY_PROFILE = 'phone_first'
