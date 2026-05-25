"""Dentist vertical — shared template for any dental campaign.

Generic dental knobs that apply regardless of city/region. Region-specific
chain lists (e.g. Florida-heavy DSOs) go in campaigns/<c>/overrides.py
under DSO_TITLE_REGEX_EXTRA / DSO_EMAIL_DOMAINS_EXTRA.

Geographic prefixes here are vertical-generic descriptors only
("family dental", "general dental"). City-name prefixes live in
locations/<loc>.yaml so they travel with the location.
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
    'gargle.com',
    'officite.com',
    'mydentalmail.com',
    'dentalqore.com',
    'progressivedental.com',
})

ENRICH_PROFILE = EnrichProfile(
    poc_title_markers_js=r"\b(?:Dr\.?|DDS|DMD|D\.D\.S\.?|D\.M\.D\.?)\b",
    jsonld_person_types=("person", "dentist", "physician"),
    practice_name_words=frozenset({
        "dental", "dentistry", "smiles", "orthodontics",
        "clinic", "office", "practice",
    }),
    internal_link_gate_js=r"(contact|about|team|staff|get-in-touch|our-team|meet|providers|doctors|dentist|dr-)",
    contact_link_pattern=r"/(contact|get-in-touch)",
    team_link_pattern=r"/(team|staff|providers|doctors|our-doctor|meet|about)",
)

DSO_TITLE_REGEX = re.compile(
    r'\b('
    r'Aspen Dental|Heartland Dental|Pacific Dental|Smile Direct|SmileDirectClub|'
    r'Western Dental|Great Expressions|Sage Dental|Affordable Dentures|Affordable Care|'
    r'Gentle Dental|Comfort Dental|Monarch Dental|Kool Smiles|Mint Dentistry|'
    r'Dental Depot|Castle Dental|Birner|Jefferson Dental|ClearChoice|Perfect Teeth|'
    r'Smile Brands|Bright Now|Merit Dental|Midwest Dental|Mondovi Dental|'
    r'Smile Generation|'
    r'Dental Care Alliance|North American Dental|NADG|Tend Dental|'
    r'Benevis|MB2 Dental|42 North Dental|InterDent|Smile Doctors|'
    r'My Dentist Group|Aspida Dental|'
    r'Ideal Dental|Rose Dental Group|Advanced Dental Care of|'
    r'Signature Smiles|Coast Dental Smilecare|Smilecare|Westwind Dental|'
    r'The Smile Design'
    r')\b', re.I,
)

DSO_EMAIL_DOMAINS: set[str] = {
    'nadentalgroup.com',
    'mb2dental.com',
    'mydentistgroup.com',
    'aspidamail.com',
    'smilegeneration.com',
    'smilegen.com',
    'thesmiledesign.com',
    'aspendental.com',
    'heartlanddental.com',
    'pdsdental.com',
    'gargle.com',
    'rola.com',
    'mydentalmail.com',
}

GEOGRAPHIC_PREFIXES_GENERIC: set[str] = {
    'family dental', 'general dental', 'cosmetic dental', 'modern dental',
    'advanced dental', 'gentle dental',
}

INDEPENDENT_FILTERS = {
    'max_rating_exclusive': 5.0,
    'min_pain_categories':  1,
    'exclude_chains':       True,
}

OSINT_ENABLED = True
OSINT_SOURCES = ["whois", "deep_site_crawl", "serp"]
OSINT_FIELDS_DESIRED = [
    "linkedin_url_company",
    "linkedin_url_poc",
    "social_urls",
    "poc_name",
    "poc_email",
    "poc_role",
    "news_mentions",
]
OSINT_CONFIDENCE_THRESHOLD = 0.85
OSINT_HANDOFF_FIELDS = ["linkedin_url_poc", "linkedin_url_company", "social_urls"]

OSINT_SERP_QUERIES = {
    "linkedin_url_poc":     'site:linkedin.com/in "{poc_name}" "{city}" dentist OR DDS OR DMD',
    "linkedin_url_company": 'site:linkedin.com/company "{business_name}" "{city}" dental',
    "social_urls":          '"{business_name}" "{city}" instagram OR facebook OR twitter',
    "news_mentions":        '"{business_name}" "{city}" news OR press OR opening',
}

OSINT_DEEP_CRAWL_PATHS = [
    "/about", "/about-us", "/our-team", "/team", "/staff",
    "/leadership", "/our-doctors", "/dentists",
    "/contact", "/contact-us",
]

OSINT_INDUSTRY_TERMS = ["dentist", "DDS", "DMD", "dental practice"]
