"""HVAC Atlanta — campaign overrides on verticals/hvac/config.py.

AssistantDial pilot campaign. The vertical default already carries the
client-fit pain weights (calls_unanswered / booking_friction heavy) and the
national PE/franchise chain regex, so this file only reserves the slot for
Atlanta-specific multi-location operators.

Region-specific chains: populate from what analyze surfaces, don't guess
(CLAUDE.md rule 6). Known candidates to check against the data:
    Coolray, Estes Services, Reliable Heating & Air, R.S. Andrews, Casteel,
    Moncrief.
Once evidence exists:
    import re
    DSO_TITLE_REGEX_EXTRA = re.compile(r'\\b(Some Regional Chain)\\b', re.I)
    DSO_EMAIL_DOMAINS_EXTRA = {'someregionalchain.com'}
"""
from __future__ import annotations

import re

# Surfaced in the 2026-07-04 pilot scrape: Casteel is a large Atlanta
# multi-service (HVAC/plumbing/electrical) operator with its own call
# center — pre-identified as a regional-platform candidate, now confirmed
# present in the data.
DSO_TITLE_REGEX_EXTRA = re.compile(r'\b(Casteel)\b', re.I)
DSO_EMAIL_DOMAINS_EXTRA = {'casteelair.com'}

# Surfaced by 2026-07-04 decision-maker research: Air Force Heating was
# acquired by Air Pros USA (2022); Assured Comfort by Southern Home
# Services (2022). Both are platform-owned despite independent-looking
# names. Extend the earlier Casteel regex.
DSO_TITLE_REGEX_EXTRA = re.compile(
    r'\b(Casteel|Air Force Heating|Assured Comfort)\b', re.I)
DSO_EMAIL_DOMAINS_EXTRA = {'casteelair.com', 'airforceheatingandair.com', 'assuredcomfort.com'}
