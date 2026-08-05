"""Attorney / law-firm vertical — shared template for legal campaigns.

Client fit: LPO (Legal Process Outsourcing). The lead is a law firm; the
ranking axis is **reachability**, not pain — this vertical's campaigns skip
the pain-classification stage entirely. Reviews carry no signal here.
`quality_score` therefore degrades to its reachability half (0-50) plus a
small residual service-fit term (review size + rating gap); reachability,
fed by POC enrichment (decision-makers + osint-enrich + website crawl),
drives the ordering. See lib/ranking.py:score_lead — it handles empty
`agent_pain_hits` cleanly.

Pain taxonomy keys below are the vertical-agnostic STL hierarchy mains, kept
neutral (weight 1) so the classify stage still works if a future legal
campaign opts back into it. They are inert while classify is skipped.

Reachability profile is intentionally left at the config default
('poc_channels' — reach a person via LinkedIn / reachable email / personal
social). Whether the LPO client cold-calls (which would want 'phone_first',
DDD-0002) is a client-outreach question resolved per campaign in overrides.py
BEFORE handoff — not guessed here (the HVAC campaigns learned that the hard
way; see DDD-0002 context).

Chain detection (DSO_TITLE_REGEX / DSO_EMAIL_DOMAINS) is deliberately empty:
national high-volume legal networks are populated from what `analyze`
surfaces in the data, not guessed from memory (CLAUDE.md rule 6). Fill via
campaigns/<c>/overrides.py DSO_TITLE_REGEX_EXTRA once evidence exists.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_OUTREACH_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_OUTREACH_ROOT) not in sys.path:
    sys.path.insert(0, str(_OUTREACH_ROOT))

from lib.enrichers.website_crawl import EnrichProfile

# Neutral — pain is not the ranking axis for LPO (classify is skipped).
# Kept on the STL mains so a future pain-classified legal campaign works.
PAIN_WEIGHTS: dict[str, int] = {
    'calls_unanswered':            1,
    'booking_friction':            1,
    'frontline_communication':     1,
    'followup_dropped':            1,
    'billing_or_intake_errors':    1,
    'service_quality_in_session':  1,
}

# Empty: no pain-driven pitch while classify is skipped. Populate per campaign
# once the LPO offer's per-pain messaging is defined.
SERVICE_MAP: dict[str, tuple[str, str]] = {}

# Legal directories / lead-gen marketplaces / law-firm website-marketing SaaS
# that surface as a firm's "website" or contact email but aren't the firm.
VENDOR_DOMAINS_EXTRA: frozenset[str] = frozenset({
    'avvo.com',
    'findlaw.com',
    'justia.com',
    'lawyers.com',
    'martindale.com',
    'nolo.com',
    'superlawyers.com',
    'lawinfo.com',
    'legalmatch.com',
    'legalzoom.com',
    'rocketlawyer.com',
    'hg.org',
    'expertise.com',
    'yelp.com',
    'thumbtack.com',
    'nextdoor.com',
    'scorpion.co',
    'findlaw.co',
    'lawrank.com',
})

ENRICH_PROFILE = EnrichProfile(
    poc_title_markers_js=r"\b(?:Managing Partner|Founding Partner|Senior Partner|Name Partner|Partner|Of Counsel|Principal|Managing Attorney|Senior Attorney|Attorney|Lawyer|Owner|Founder|Member|Shareholder|Firm Administrator|Office Manager)\b",
    jsonld_person_types=("person", "attorney"),
    practice_name_words=frozenset({
        "law", "laws", "lawyer", "lawyers", "attorney", "attorneys",
        "legal", "firm", "associates", "counsel", "counselors", "esq",
        "esquire", "group", "offices", "office", "partners", "pllc",
        "llp", "pc", "pa", "chartered",
    }),
    internal_link_gate_js=r"(attorneys?|lawyers?|our-team|team|people|about|our-firm|firm|bio|profile|staff|contact)",
    contact_link_pattern=r"/(contact|get-in-touch|reach-us|schedule|consultation|free-consultation)",
    team_link_pattern=r"/(attorneys?|lawyers?|team|our-team|people|about|our-firm|staff|bios?|profiles?)",
)

# Left empty on purpose — national legal networks are evidence-populated from
# analyze output per campaign (CLAUDE.md rule 6). `(?!)` matches nothing.
DSO_TITLE_REGEX = re.compile(r'(?!)')
DSO_EMAIL_DOMAINS: set[str] = set()

GEOGRAPHIC_PREFIXES_GENERIC: set[str] = {
    'law firm', 'law office', 'law offices', 'attorneys at law',
    'attorney at law', 'legal services', 'legal group', 'law group',
    'and associates', '& associates',
}

INDEPENDENT_FILTERS = {
    'max_rating_exclusive': 5.0,
    'min_pain_categories':  0,      # classify skipped — do not require pain
    'exclude_chains':       False,  # LPO can sell to firms of any size
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
    "linkedin_url_poc":     'site:linkedin.com/in "{poc_name}" "{city}" attorney OR lawyer OR partner',
    "linkedin_url_company": 'site:linkedin.com/company "{business_name}" "{city}" law OR attorneys',
    "social_urls":          '"{business_name}" "{city}" instagram OR facebook OR twitter',
    "news_mentions":        '"{business_name}" "{city}" attorney news OR press OR verdict OR settlement',
}

OSINT_DEEP_CRAWL_PATHS = [
    "/attorneys", "/our-attorneys", "/lawyers", "/our-team", "/team",
    "/people", "/about", "/about-us", "/our-firm", "/staff",
    "/bio", "/bios", "/profiles", "/contact", "/contact-us",
]

OSINT_INDUSTRY_TERMS = ["law firm", "attorney", "lawyer", "law office", "legal services"]
