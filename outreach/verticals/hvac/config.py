"""HVAC vertical — shared template for any HVAC-services campaign.

Client fit: AssistantDial AI (AI phone receptionist for HVAC — 24/7 inbound
answering, lead qualification, appointment booking). The ideal lead is a small
independent owner-operated shop whose reviews show phone pain: unanswered
calls, no after-hours coverage, hard to book. PE platforms and franchises
already run call centers, so chain exclusion matters more here than in most
verticals.

Pain taxonomy is the vertical-agnostic STL hierarchy. Weights deviate from
the dental default deliberately: AssistantDial is INBOUND-ONLY (no outbound
follow-up, no SMS campaigns), so `calls_unanswered` and `booking_friction`
carry the offer and `followup_dropped` is de-weighted — a shop whose only
pain is dropped follow-up is a weak fit. Tunable per campaign via
overrides.py:PAIN_WEIGHTS once review data justifies it.

National/PE HVAC brands live here; region-specific multi-location operators
(Phoenix's Parker & Sons, DFW's A#1 Air, …) go in campaigns/<c>/overrides.py
under DSO_TITLE_REGEX_EXTRA / DSO_EMAIL_DOMAINS_EXTRA — populate from what
analyze surfaces, don't guess (CLAUDE.md rule 6).

Geographic prefixes here are vertical-generic descriptors only
("air conditioning", "heating and cooling"). City-name prefixes live in
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
    'booking_friction':            5,
    'frontline_communication':     3,
    'followup_dropped':            2,
    'billing_or_intake_errors':    1,
    'service_quality_in_session':  1,
}

# Maps pain mains to the AssistantDial feature that answers them — the
# handoff CSV surfaces these to the client's sales team as the pitch angle.
SERVICE_MAP: dict[str, tuple[str, str]] = {
    'calls_unanswered':            ('AssistantDial 24/7 AI Receptionist — every call answered', 'assistantdial.ai'),
    'booking_friction':            ('AssistantDial Appointment Booking + Calendar Sync',        'assistantdial.ai'),
    'frontline_communication':     ('AssistantDial AI Receptionist — consistent frontline',     'assistantdial.ai'),
    'followup_dropped':            ('AssistantDial Call Summaries + Auto Contact Creation',     'assistantdial.ai'),
    'billing_or_intake_errors':    ('AssistantDial structured call intake',                     'assistantdial.ai'),
    'service_quality_in_session':  ('AssistantDial demo line',                                  'assistantdial.ai'),
}

# Directories / lead-gen marketplaces / HVAC website-marketing SaaS that show
# up as a lead's "website" or contact email but aren't the business itself.
VENDOR_DOMAINS_EXTRA: frozenset[str] = frozenset({
    'angi.com',
    'homeadvisor.com',
    'thumbtack.com',
    'yelp.com',
    'servicetitan.com',
    'housecallpro.com',
    'rynoss.com',
    'mediagistic.com',
    'hvacwebsites.com',
    'blueconduit.com',
    'carrier.com',
    'trane.com',
    'lennox.com',
    'rheem.com',
    'goodmanmfg.com',
})

ENRICH_PROFILE = EnrichProfile(
    poc_title_markers_js=r"\b(?:Owner|Founder|Co-?Founder|President|General Manager|Office Manager|Operations Manager|Service Manager|Master Technician|Lead Technician|Lead Installer)\b",
    jsonld_person_types=("person",),
    practice_name_words=frozenset({
        "hvac", "heating", "cooling", "air", "conditioning", "ac",
        "climate", "comfort", "mechanical", "refrigeration", "services",
        "service", "solutions", "co", "company", "inc", "llc",
    }),
    internal_link_gate_js=r"(contact|about|team|staff|our-story|story|owner|founder|meet|services|service|location)",
    contact_link_pattern=r"/(contact|get-in-touch|reach-us|schedule)",
    team_link_pattern=r"/(team|staff|about|our-story|story|owner|founder|meet|people)",
)

# National / multi-state PE-backed HVAC brands and franchises. These run
# call centers or franchise phone systems — dead leads for an AI-receptionist
# pitch. Region-specific platforms go in campaign overrides.
DSO_TITLE_REGEX = re.compile(
    r'\b('
    r'One Hour (?:Heating|Air)|ARS[ /-]?Rescue Rooter|American Residential Services|'
    r'Service Experts|Aire Serv|TemperaturePro|Sila (?:Heating|Services)|'
    r'Horizon Services|Goettl|Air Pros|Any Hour|'
    r'Sears (?:Heating|Home Services)|Lee Company|F\.?H\.? Furr|Airtron|'
    r'Mister Sparky|Benjamin Franklin Plumbing|'  # Authority Brands siblings that co-brand HVAC
    r'A[- ]?U[- ]?S Air Conditioning|Del[- ]?Air'
    r')\b', re.I,
)

DSO_EMAIL_DOMAINS: set[str] = {
    'onehourair.com',
    'onehourheatandair.com',
    'ars.com',
    'serviceexperts.com',
    'aireserv.com',
    'temperaturepro.com',
    'silaservices.com',
    'horizonservices.com',
    'goettl.com',
    'airprosusa.com',
    'anyhour.com',
    'delair.com',
    'airtron.com',
}

GEOGRAPHIC_PREFIXES_GENERIC: set[str] = {
    'air conditioning', 'air conditioning and heating',
    'heating and air conditioning', 'heating and cooling',
    'heating & cooling', 'heating & air', 'ac repair',
    'air conditioning repair', 'hvac services', 'comfort',
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
    "linkedin_url_poc":     'site:linkedin.com/in "{poc_name}" "{city}" HVAC OR "air conditioning" owner OR president',
    "linkedin_url_company": 'site:linkedin.com/company "{business_name}" "{city}" HVAC',
    "social_urls":          '"{business_name}" "{city}" instagram OR facebook OR twitter',
    "news_mentions":        '"{business_name}" "{city}" news OR press OR opening',
}

OSINT_DEEP_CRAWL_PATHS = [
    "/about", "/about-us", "/our-team", "/team", "/staff",
    "/our-story", "/owner", "/meet-the-team",
    "/contact", "/contact-us",
]

OSINT_INDUSTRY_TERMS = ["HVAC", "air conditioning", "heating and cooling", "HVAC contractor"]
