"""Retail vertical — shared template.

Pain taxonomy unchanged from dental (vertical-agnostic STL hierarchy);
fit on retail is unproven. Treat retail campaigns as exploratory.

National retail chains here; regional/country-specific chains
(Canadian Tire, Loblaws, Toronto mall properties) go in
campaigns/<c>/overrides.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_OUTREACH_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_OUTREACH_ROOT) not in sys.path:
    sys.path.insert(0, str(_OUTREACH_ROOT))

from lib.enrichers.website_crawl import EnrichProfile

PAIN_WEIGHTS: dict[str, int] = {
    'calls_unanswered':            5,
    'booking_friction':            4,
    'followup_dropped':            4,
    'billing_or_intake_errors':    4,
    'frontline_communication':     2,
    'service_quality_in_session':  1,
}

SERVICE_MAP: dict[str, tuple[str, str]] = {
    'calls_unanswered':            ('Voice AI Agents (Inbound Coverage)',          'silverthreadlabs.com/services/voice-agents'),
    'booking_friction':            ('Voice AI Booking + Agentic Self-Service',     'silverthreadlabs.com/services/voice-agents'),
    'followup_dropped':            ('Agentic AI Systems (Autonomous Follow-up)',   'silverthreadlabs.com/services/agentic-ai'),
    'billing_or_intake_errors':    ('Workflow Automation + Systems Integration',   'silverthreadlabs.com/services/workflow-automation'),
    'frontline_communication':     ('Voice AI + Agentic CRM Outreach',             'silverthreadlabs.com/services/voice-agents'),
    'service_quality_in_session':  ('Automation Audit',                            'silverthreadlabs.com/audit'),
}

VENDOR_DOMAINS_EXTRA: frozenset[str] = frozenset({
    'lightspeedhq.com',
    'shoplazza.com',
    'bigcartel.com',
})

ENRICH_PROFILE = EnrichProfile(
    poc_title_markers_js=r"\b(?:Owner|Founder|Co-?Founder|Manager|Store Manager|General Manager|Buyer|Director|President)\b",
    jsonld_person_types=("person",),
    practice_name_words=frozenset({
        "shop", "store", "boutique", "market", "retail",
        "co", "company", "inc", "ltd",
    }),
    internal_link_gate_js=r"(contact|about|team|staff|our-story|story|owner|founder|meet|locations)",
    contact_link_pattern=r"/(contact|get-in-touch|reach-us)",
    team_link_pattern=r"/(team|staff|about|our-story|story|owner|founder|meet|people)",
)

DSO_TITLE_REGEX = re.compile(
    r'\b('
    r'Walmart|Costco|IKEA|Best Buy|Staples|'
    r'H&M|Zara|Uniqlo|Old Navy|Gap|Banana Republic|'
    r'Lululemon|Nike|Adidas|ALDO|Foot Locker|Champs Sports|'
    r'Urban Outfitters|Anthropologie|Free People|MUJI|'
    r'Sephora|MAC|Bath & Body Works|Lush|The Body Shop|'
    r'Apple Store|Microsoft Store|'
    r'Williams[- ]Sonoma|Pottery Barn|West Elm|Crate & Barrel'
    r')\b', re.I,
)

DSO_EMAIL_DOMAINS: set[str] = {
    'walmart.com',
    'costco.com',
    'ikea.com',
    'lululemon.com',
    'nike.com',
    'adidas.com',
    'sephora.com',
    'apple.com',
}

GEOGRAPHIC_PREFIXES_GENERIC: set[str] = set()

INDEPENDENT_FILTERS = {
    'max_rating_exclusive': 5.0,
    'min_pain_categories':  1,
    'exclude_chains':       True,
}

OSINT_ENABLED = False
OSINT_SOURCES = []
OSINT_FIELDS_DESIRED = []
OSINT_CONFIDENCE_THRESHOLD = 0.85
OSINT_HANDOFF_FIELDS = []
OSINT_SERP_QUERIES = {}
OSINT_DEEP_CRAWL_PATHS = []
OSINT_INDUSTRY_TERMS = []
