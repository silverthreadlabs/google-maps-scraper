"""Software / digital-agency vertical — shared template.

Default weighting tuned for Ezly's AI communication assistant ICP
(small/mid agencies). Campaigns can override PAIN_WEIGHTS and
SERVICE_MAP in their overrides.py if pitching a different product.

Region-specific outsourcer brand lists (UA: EPAM, GlobalLogic; etc.)
go in campaigns/<c>/overrides.py.
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
    'frontline_communication':     5,
    'followup_dropped':            5,
    'calls_unanswered':            4,
    'deadline_missed':             2,
    'scope_drift':                 2,
    'service_quality_in_session':  1,
    'delivery_quality':            1,
    'hidden_subcontracting':       1,
    'booking_friction':            1,
    'billing_or_intake_errors':    1,
}

SERVICE_MAP: dict[str, tuple[str, str]] = {
    'frontline_communication':     ('Ezly — AI Communication Assistant (tone + personalization)',     'getezly.com/home'),
    'followup_dropped':            ('Ezly — AI Communication Assistant (faster client follow-up)',    'getezly.com/home'),
    'calls_unanswered':            ('Ezly — AI Communication Assistant (never miss a reply)',         'getezly.com/home'),
    'deadline_missed':             ('Ezly — AI Communication Assistant (expectation-setting replies)','getezly.com/home'),
    'scope_drift':                 ('Ezly — AI Communication Assistant (proposal generator)',         'getezly.com/home'),
    'service_quality_in_session':  ('Ezly — AI Communication Assistant (client-comms layer)',         'getezly.com/home'),
    'delivery_quality':            ('Ezly — AI Communication Assistant (client-comms layer)',         'getezly.com/home'),
    'hidden_subcontracting':       ('Ezly — AI Communication Assistant (client-comms layer)',         'getezly.com/home'),
    'booking_friction':            ('Ezly — AI Communication Assistant (proposal generator)',         'getezly.com/home'),
    'billing_or_intake_errors':    ('Ezly — AI Communication Assistant (proposal generator)',         'getezly.com/home'),
}

VENDOR_DOMAINS_EXTRA: frozenset[str] = frozenset({
    'clutch.co',
    'goodfirms.co',
    'designrush.com',
    'manifest.com',
    'sortlist.com',
})

ENRICH_PROFILE = EnrichProfile(
    poc_title_markers_js=r"\b(?:CEO|CTO|COO|CFO|Founder|Co-?Founder|Owner|Principal|Partner|Managing Director|Director)\b",
    jsonld_person_types=("person",),
    practice_name_words=frozenset({
        "software", "digital", "agency", "studio", "lab", "labs",
        "technologies", "tech", "solutions", "systems", "consulting",
        "interactive", "creative",
    }),
    internal_link_gate_js=r"(contact|about|team|leadership|founders|management|people|company|who-we-are)",
    contact_link_pattern=r"/(contact|contact-us|get-in-touch|hello)",
    team_link_pattern=r"/(team|about|leadership|founders|management|people|company|who-we-are)",
)

DSO_TITLE_REGEX = re.compile(
    r'\b('
    r'Accenture|Capgemini|Cognizant|HCL|IBM|Microsoft|Google|Oracle|SAP|'
    r'Deloitte|EY|PwC|KPMG|McKinsey|BCG|Bain'
    r')\b', re.I,
)

DSO_EMAIL_DOMAINS: set[str] = {
    'accenture.com',
    'capgemini.com',
    'cognizant.com',
    'hcl.com',
    'ibm.com',
    'microsoft.com',
    'google.com',
    'oracle.com',
    'sap.com',
    'deloitte.com',
    'ey.com',
    'pwc.com',
    'kpmg.com',
}

GEOGRAPHIC_PREFIXES_GENERIC: set[str] = {
    'web studio', 'web design', 'design studio', 'digital agency',
    'software development', 'software company', 'it company',
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
    "linkedin_url_poc":     'site:linkedin.com/in "{poc_name}" "{city}" software OR CEO OR founder',
    "linkedin_url_company": 'site:linkedin.com/company "{business_name}" "{city}"',
    "social_urls":          '"{business_name}" "{city}" linkedin OR instagram OR facebook',
    "news_mentions":        '"{business_name}" "{city}" news OR press OR launch',
}

OSINT_DEEP_CRAWL_PATHS = [
    "/about", "/about-us", "/team", "/our-team", "/leadership",
    "/founders", "/management", "/people", "/company",
    "/contact", "/contact-us", "/hello",
]

OSINT_INDUSTRY_TERMS = ["software", "digital agency", "web development", "design studio", "outsourcing"]
