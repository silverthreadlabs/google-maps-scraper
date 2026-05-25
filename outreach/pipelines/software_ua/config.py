"""
Software UA campaign — single source of truth for industry-specific knobs.

Targets Ukrainian software/design/digital agencies (Kyiv, Lviv, Dnipro)
as prospects for Ezly (https://www.getezly.com/home) — an AI reply
assistant for client communication.

Honest fit note: Ezly's ICP is solo freelancers on Upwork/Fiverr; this
list is small/mid agencies. Pain extraction will skew weaker than the
dental gold set (F1 ~0.78) because Google Maps reviews for B2B software
agencies discuss project-delivery pain, not response-speed pain. Pipeline
proceeds anyway per user direction.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_OUTREACH_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_OUTREACH_ROOT) not in sys.path:
    sys.path.insert(0, str(_OUTREACH_ROOT))

from lib.enrichers.website_crawl import EnrichProfile

VERTICAL = 'software'

# ─────────────────────────────────────────────────────────────────────────────
# Pain ranking weights (used by lib/ranking.py:quality_score and the handoff
# CSV's top-pain selection).
# ─────────────────────────────────────────────────────────────────────────────
# Re-weighted for Ezly's communication-quality pitch. The mains most aligned
# with Ezly's value prop (reply speed + tone + personalization) are
# frontline_communication and followup_dropped. calls_unanswered is adjacent
# (reachability). Booking / billing pains are unlikely to fire on B2B
# software-agency reviews and are de-prioritized.
PAIN_WEIGHTS: dict[str, int] = {
    # Direct Ezly fit — what Ezly actually solves
    'frontline_communication':     5,  # tone, professionalism, replies
    'followup_dropped':            5,  # ghosting clients post-pitch
    'calls_unanswered':            4,  # reachability / response latency
    # Adjacent — Ezly helps indirectly (proposals, expectation-setting)
    'deadline_missed':             2,  # better client comms reduces deadline-shock
    'scope_drift':                 2,  # cleaner proposals reduce drift
    # Supporting pain — evidence that the lead is unhappy with current ops,
    # but Ezly is not the direct fix. Low weight; surfaces in handoff for context.
    'service_quality_in_session':  1,
    'delivery_quality':            1,
    'hidden_subcontracting':       1,
    'booking_friction':            1,
    'billing_or_intake_errors':    1,
}


# All pain mains route to Ezly. Labels are tuned per main so the handoff CSV
# carries an honest "why we're reaching out" line — direct vs adjacent vs
# supporting evidence.
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


# ─────────────────────────────────────────────────────────────────────────────
# Email validation extras (consumed by lib/validators/email.py)
# ─────────────────────────────────────────────────────────────────────────────
# B2B-software-vertical vendors / aggregators. Generic VENDOR_DOMAINS in
# lib already covers wix/squarespace/hubspot/mailchimp/etc; this extends
# with B2B agency-directory domains that often leak into scraped emails.
VENDOR_DOMAINS_EXTRA: frozenset[str] = frozenset({
    'clutch.co',
    'goodfirms.co',
    'designrush.com',
    'manifest.com',
    'sortlist.com',
})


# ─────────────────────────────────────────────────────────────────────────────
# Website-crawl enrichment profile (consumed by lib/enrichers/website_crawl.py)
# ─────────────────────────────────────────────────────────────────────────────
# Looking for software-agency leadership markers, not dentist credentials.
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


# ─────────────────────────────────────────────────────────────────────────────
# Chain / enterprise-outsourcer detection
# ─────────────────────────────────────────────────────────────────────────────
# Big IT services firms / enterprise outsourcers. These are NOT Ezly buyers —
# they have BD orgs, sales teams, and procurement processes. Flag and exclude
# so outreach focuses on small/mid shops that might actually use Ezly.
DSO_TITLE_REGEX = re.compile(
    r'\b('
    # Ukraine-based enterprise outsourcers
    r'EPAM|GlobalLogic|SoftServe|Luxoft|Ciklum|N-?iX|Sigma Software|'
    r'Intellias|ELEKS|Miratech|Infopulse|DataArt|Daxx|Beetroot|'
    r'Astound Commerce|Edvantis|Symphony Solutions|Innovecs|Plexteq|'
    r'TEAM International|AltexSoft|Provectus|Devoteam|'
    # Global big-IT
    r'Accenture|Capgemini|Wipro|Infosys|TCS|Tata Consultancy|'
    r'Cognizant|HCL|IBM|Microsoft|Google|Oracle|SAP|Deloitte|'
    r'EY|PwC|KPMG|McKinsey|BCG|Bain|'
    # Big SaaS / product cos that show up in maps
    r'Wix\.com|Grammarly|MacPaw|GitLab|JetBrains|Reply'
    r')\b', re.I,
)

# Corp-routing email domains for enterprise outsourcers.
DSO_EMAIL_DOMAINS: set[str] = {
    'epam.com',
    'globallogic.com',
    'softserveinc.com',
    'luxoft.com',
    'ciklum.com',
    'n-ix.com',
    'sigma.software',
    'intellias.com',
    'eleks.com',
    'miratech.com',
    'infopulse.com',
    'dataart.com',
    'daxx.com',
    'beetroot.se',
    'astoundcommerce.com',
    'innovecs.com',
    'symphony-solutions.eu',
    'accenture.com',
    'capgemini.com',
    'wipro.com',
    'infosys.com',
    'tcs.com',
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
    'wix.com',
    'grammarly.com',
    'macpaw.com',
    'gitlab.com',
    'jetbrains.com',
}

# Geographic prefixes that look like brand prefixes but aren't. Less of an
# issue for software agencies (they don't usually replicate a brand across
# cities the way dental DSOs do), but include city names + common
# transliterations so single shops indexed in multiple grid cells aren't
# auto-flagged as a chain.
GEOGRAPHIC_PREFIXES: set[str] = {
    'kyiv', 'kiev', 'київ',
    'lviv', 'lvov', 'львів',
    'dnipro', 'dnepr', 'дніпро',
    'ukraine', 'україна',
    # Generic agency descriptors that recur across unrelated shops
    'web studio', 'web design', 'design studio', 'digital agency',
    'software development', 'software company', 'it company',
}


# ─────────────────────────────────────────────────────────────────────────────
# Region / metro configuration
# ─────────────────────────────────────────────────────────────────────────────
# Ukrainian area codes after stripping the `+380` E.164 country code and the
# domestic trunk-0 prefix. Each metro carries its landline area code AND the
# major nationwide mobile prefixes — without mobiles, every business mobile
# number would flag as metro_mismatch (most software shops list mobile contact
# numbers, not landlines). The metro check then meaningfully fires only when a
# lead has a LANDLINE for a different metro.
_UA_MOBILE_PREFIXES = {
    '50', '63', '66', '67', '68', '73',
    '93', '95', '96', '97', '98', '99',
}
METRO_AREA_CODES: dict[str, set[str]] = {
    'kyiv':   {'44'} | _UA_MOBILE_PREFIXES,
    'lviv':   {'32'} | _UA_MOBILE_PREFIXES,
    'dnipro': {'56'} | _UA_MOBILE_PREFIXES,
}

METROS = ['kyiv', 'lviv', 'dnipro']

QUERIES_DIR = 'queries'


# ─────────────────────────────────────────────────────────────────────────────
# Filter rules for the "small independents" view
# ─────────────────────────────────────────────────────────────────────────────
# Ezly's ICP is small. Exclude chains aggressively; require some pain signal.
INDEPENDENT_FILTERS = {
    'max_rating_exclusive': 5.0,
    'min_pain_categories':  1,
    'exclude_chains':       True,
}


# ─────────────────────────────────────────────────────────────────────────────
# OSINT enrichment
# ─────────────────────────────────────────────────────────────────────────────
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
    "linkedin_url_poc":     'site:linkedin.com/in "{poc_name}" "{city}" Ukraine software OR CEO OR founder',
    "linkedin_url_company": 'site:linkedin.com/company "{business_name}" "{city}" Ukraine',
    "social_urls":          '"{business_name}" "{city}" linkedin OR instagram OR facebook',
    "news_mentions":        '"{business_name}" "{city}" news OR press OR launch',
}

OSINT_DEEP_CRAWL_PATHS = [
    "/about", "/about-us", "/team", "/our-team", "/leadership",
    "/founders", "/management", "/people", "/company",
    "/contact", "/contact-us", "/hello",
]

OSINT_INDUSTRY_TERMS = ["software", "digital agency", "web development", "design studio", "outsourcing"]
