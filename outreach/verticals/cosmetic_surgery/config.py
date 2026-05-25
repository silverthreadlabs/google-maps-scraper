"""Cosmetic / plastic surgery vertical — shared template.

Pain taxonomy unchanged from dental (vertical-agnostic STL hierarchy).
National chain list here; regional dermatology DSOs go in
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
    'rosemontmedia.com',
    'influxmarketing.com',
    'studioiii.com',
})

ENRICH_PROFILE = EnrichProfile(
    poc_title_markers_js=r"\b(?:Dr\.?|MD|M\.D\.?|D\.O\.?|DO|FACS|F\.A\.C\.S\.?)\b",
    jsonld_person_types=("person", "physician"),
    practice_name_words=frozenset({
        "plastic", "cosmetic", "surgery", "surgical",
        "aesthetics", "aesthetic", "medspa", "facial",
        "clinic", "institute", "center",
    }),
    internal_link_gate_js=r"(contact|about|team|staff|providers|surgeons|doctors|meet|our-team|dr-|practice)",
    contact_link_pattern=r"/(contact|get-in-touch|consultation|reach-us)",
    team_link_pattern=r"/(team|staff|providers|doctors|surgeons|meet|about|our-(?:doctor|surgeon|team))",
)

DSO_TITLE_REGEX = re.compile(
    r'\b('
    r'Sono Bello|SonoBello|'
    r'LaserAway|Laser Away|'
    r'Ideal Image|'
    r'Skinney Medspa|'
    r'Athena Cosmetic|'
    r'Bosley|Hair Club|'
    r'Plastic Surgery Group of'
    r')\b', re.I,
)

DSO_EMAIL_DOMAINS: set[str] = {
    'sonobello.com',
    'laseraway.com',
    'idealimage.com',
    'bosley.com',
    'hairclub.com',
}

GEOGRAPHIC_PREFIXES_GENERIC: set[str] = {
    'advanced cosmetic', 'modern cosmetic', 'premier plastic',
    'advanced plastic', 'modern plastic', 'aesthetic',
    'family cosmetic',
}

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
