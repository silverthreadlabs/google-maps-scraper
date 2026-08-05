"""HVAC Dallas / DFW — campaign overrides on verticals/hvac/config.py.

AssistantDial pilot campaign. The vertical default already carries the
client-fit pain weights (calls_unanswered / booking_friction heavy) and the
national PE/franchise chain regex, so this file only reserves the slot for
Dallas / DFW-specific multi-location operators.

Region-specific chains: populate from what analyze surfaces, don't guess
(CLAUDE.md rule 6). Known candidates to check against the data:
    A#1 Air, Berkeys, Baker Brothers, Milestone, Frymire, Levy & Son.
Once evidence exists:
    import re
    DSO_TITLE_REGEX_EXTRA = re.compile(r'\\b(Some Regional Chain)\\b', re.I)
    DSO_EMAIL_DOMAINS_EXTRA = {'someregionalchain.com'}
"""
from __future__ import annotations
