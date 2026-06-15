"""Automotive vertical — shared template for any automotive-services campaign.

Covers the local automotive-services trade: independent repair shops, body /
collision shops, detailing, glass, smog, tires, transmission, parts stores,
upholstery / audio / customization, paint, rental agencies, and used-car
dealers. Owner-/manager-led local service businesses — modeled on the dental
vertical (OSINT on, owner-led enrich markers), NOT retail.

Pain taxonomy is the vertical-agnostic STL hierarchy (mains 1-6 apply
directly: an auto shop that misses calls, can't book you, drops quotes, or
surprise-bills is the bread-and-butter pain). Weights are the proven dental
default. NOTE (tunable, do not hand-edit without review data): for auto repair
specifically, surprise-billing ("quoted X, billed Y") and dropped quotes are
the signature complaints — `billing_or_intake_errors` may deserve a 5. Bump it
via campaigns/<c>/overrides.py:PAIN_WEIGHTS once review data justifies it.

National automotive chains live here; region-specific chains (Bay Area
franchise groups, local multi-location operators) go in
campaigns/<c>/overrides.py under DSO_TITLE_REGEX_EXTRA / DSO_EMAIL_DOMAINS_EXTRA.

Geographic prefixes here are vertical-generic descriptors only
("auto repair", "auto body"). City-name prefixes live in
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

# Automotive shop-management SaaS / marketing-agency domains that show up as
# the "website" or contact email but aren't the business itself. Verified
# against 2025-26 auto-shop software/marketing vendor rankings.
VENDOR_DOMAINS_EXTRA: frozenset[str] = frozenset({
    'kukui.com',
    'autoshopsolutions.com',
    'repairshopwebsites.com',
    'shopmonkey.io',
    'tekmetric.com',
    'autovitals.com',
    'autoleap.com',
    'mitchell1.com',
    'identifix.com',
})

ENRICH_PROFILE = EnrichProfile(
    poc_title_markers_js=r"\b(?:Owner|Founder|Co-?Founder|President|Manager|General Manager|Service Manager|Shop Manager|Service Advisor|Master Technician|Lead Technician)\b",
    jsonld_person_types=("person",),
    practice_name_words=frozenset({
        "auto", "automotive", "autobody", "repair", "service", "garage",
        "motors", "tire", "tires", "collision", "body", "shop", "center",
        "centre", "co", "company", "inc", "llc",
    }),
    internal_link_gate_js=r"(contact|about|team|staff|our-story|story|owner|founder|meet|services|service|location)",
    contact_link_pattern=r"/(contact|get-in-touch|reach-us)",
    team_link_pattern=r"/(team|staff|about|our-story|story|owner|founder|meet|people)",
)

DSO_TITLE_REGEX = re.compile(
    r'\b('
    # Quick-lube / maintenance / general-repair franchises
    r'Jiffy Lube|Valvoline|Valvoline Instant Oil Change|Take 5|Grease Monkey|'
    r'SpeeDee Oil Change|Express Oil Change|Honest-?1|'
    r'Midas|Meineke|Pep Boys|AAMCO|Cottman|Tuffy|Brakes Plus|'
    r'Christian Brothers Automotive|Firestone|Goodyear Auto Service|'
    r'Monro|Mr\.? Tire|Tires Plus|Precision Tune|Car-?X|'
    # Tire chains
    r'Discount Tire|America\'?s Tire|Les Schwab|Big O Tires|Tire Kingdom|'
    r'National Tire & Battery|NTB|Mavis|'
    # Body / collision chains
    r'Maaco|CARSTAR|Caliber Collision|Gerber Collision|Service King|'
    r'Crash Champions|Abra Auto Body|Fix Auto|Ziebart|'
    # Glass
    r'Safelite|Glass Doctor|'
    # Parts retailers
    r'AutoZone|O\'?Reilly|NAPA Auto Parts|Advance Auto Parts|Carquest|LKQ|'
    # Rental agencies
    r'Enterprise Rent-?A-?Car|Enterprise Car|Hertz|Avis|Budget Rent|National Car Rental|'
    r'Alamo Rent|Dollar Rent|Thrifty Car|Sixt|Zipcar|Turo|'
    # Used-car / dealership groups
    r'CarMax|AutoNation|Carvana|Vroom|DriveTime|Penske|Lithia|'
    r'Sonic Automotive|Group 1 Automotive'
    r')\b', re.I,
)

DSO_EMAIL_DOMAINS: set[str] = {
    'jiffylube.com',
    'valvoline.com',
    'take5oilchange.com',
    'midas.com',
    'meineke.com',
    'pepboys.com',
    'aamco.com',
    'christianbrothersauto.com',
    'firestonecompleteautocare.com',
    'goodyearautoservice.com',
    'monro.com',
    'discounttire.com',
    'americastire.com',
    'lesschwab.com',
    'bigotires.com',
    'maaco.com',
    'carstar.com',
    'calibercollision.com',
    'gerbercollision.com',
    'safelite.com',
    'autozone.com',
    'oreillyauto.com',
    'napaonline.com',
    'advanceautoparts.com',
    'enterprise.com',
    'hertz.com',
    'avis.com',
    'budget.com',
    'carmax.com',
    'autonation.com',
    'carvana.com',
}

GEOGRAPHIC_PREFIXES_GENERIC: set[str] = {
    'auto repair', 'auto body', 'automotive', 'auto service',
    'car care', 'collision center', 'tire shop',
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

# The buyer of STL's voice-AI / automation pitch at an auto shop is the
# person who feels the missed-call / dropped-quote pain: the owner, general
# manager, or service manager. Bias the POC LinkedIn search toward those
# roles (mirrors software_ua_v2's decision-maker targeting) plus industry
# terms to disambiguate common names. Campaigns may further widen via
# overrides.py:OSINT_SERP_QUERIES.
OSINT_SERP_QUERIES = {
    "linkedin_url_poc":
        'site:linkedin.com/in "{poc_name}" "{city}" '
        '(owner OR "general manager" OR "service manager" OR automotive OR mechanic OR "auto repair")',
    "linkedin_url_company": 'site:linkedin.com/company "{business_name}" "{city}" auto OR automotive',
    "social_urls":          '"{business_name}" "{city}" instagram OR facebook OR twitter',
    "news_mentions":        '"{business_name}" "{city}" news OR press OR opening',
}

OSINT_DEEP_CRAWL_PATHS = [
    "/about", "/about-us", "/our-team", "/team", "/staff",
    "/meet-the-team", "/owner", "/our-story",
    "/contact", "/contact-us", "/services",
]

OSINT_INDUSTRY_TERMS = ["auto repair", "mechanic", "auto body", "collision", "automotive"]
