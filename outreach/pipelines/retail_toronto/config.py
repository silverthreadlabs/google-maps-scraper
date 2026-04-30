"""
Retail Toronto campaign — exploratory pipeline.

Scope: small-to-medium independent retail in the GTA. Malls and national
chains get flagged via DSO_TITLE_REGEX so the analyze step excludes them.

Note: STL's product (voice agents, agentic workflow automation) is built
for service businesses with phone-heavy intake. The pain taxonomy in
silverthread/pain_categories.md is vertical-agnostic, so PAIN_WEIGHTS and
SERVICE_MAP are unchanged from dental — but the resulting fit on retail
leads is unproven. Treat this campaign as exploratory until the classify
step shows whether retail pains map onto STL's offerings.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_OUTREACH_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_OUTREACH_ROOT) not in sys.path:
    sys.path.insert(0, str(_OUTREACH_ROOT))

from lib.enrichers.website_crawl import EnrichProfile

# ─────────────────────────────────────────────────────────────────────────────
# Pain ranking weights — unchanged from dental_sunbelt (vertical-agnostic
# taxonomy). Re-tune after the first classify run if retail pain distribution
# differs materially from service-business assumptions.
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# Email validation extras
# ─────────────────────────────────────────────────────────────────────────────
# Retail-specific marketing / e-commerce platforms whose contact emails
# route to the platform, not the store. The lib's generic VENDOR_DOMAINS
# already covers wix/squarespace/shopify; this extends with retail-only.
VENDOR_DOMAINS_EXTRA: frozenset[str] = frozenset({
    'lightspeedhq.com',     # POS/e-commerce platform
    'shoplazza.com',        # Shopify-alternative builder
    'bigcartel.com',        # indie retail storefront builder
})


# ─────────────────────────────────────────────────────────────────────────────
# Website-crawl enrichment profile — retail POC titles
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# Chain detection — retail Canada (national + GTA-heavy chains) + malls
# ─────────────────────────────────────────────────────────────────────────────
# Mall property listings are flagged here too — they show up as "leads"
# in Google Maps but they're properties, not businesses we'd pitch.
DSO_TITLE_REGEX = re.compile(
    r'(?:\b(?:'
    # National department / general retail chains
    r'Walmart|Costco|Canadian Tire|Hudson\'?s Bay|The Bay|Winners|HomeSense|Marshalls|'
    r'Home Depot|Lowe\'?s|RONA|IKEA|Best Buy|Staples|'
    r'Dollarama|Dollar Tree|Dollar General|Giant Tiger|'
    # Grocery / pharmacy crossover into "retail" category
    r'Loblaws|No Frills|Real Canadian Superstore|Metro|Sobeys|FreshCo|Food Basics|'
    r'Shoppers Drug Mart|Rexall|Pharmasave|'
    # Apparel / footwear chains
    r'H&M|Zara|Uniqlo|Old Navy|Gap|Banana Republic|Mark\'?s|Sport Chek|Atmosphere|'
    r'Lululemon|Arc\'?teryx|Nike|Adidas|ALDO|Foot Locker|Champs Sports|'
    r'Roots|Reitmans|Penningtons|Bluenotes|Garage|Suzy Shier|Le Château|'
    r'Aritzia|Urban Outfitters|Anthropologie|Free People|MUJI|'
    r'Once Upon A Child|Plato\'?s Closet|Value Village|Salvation Army|'
    r'Stitches|Kith|CHANEL|Chanel|gravitypope|Fj.llr.ven|'
    # Beauty / specialty
    r'Sephora|MAC|Bath & Body Works|Lush|The Body Shop|'
    # Books / media / electronics
    r'Indigo|Chapters|Coles|Apple Store|Microsoft Store|The Source|'
    # Furniture / home
    r'Leon\'?s|The Brick|Structube|EQ3|Crate & Barrel|Pottery Barn|West Elm|'
    r'Kitchen Stuff Plus|HomeSense|Pier 1|'
    # US chains with Toronto presence
    r'Target|Nordstrom|Saks Fifth Avenue|Holt Renfrew|Williams[- ]Sonoma|'
    # Mall properties — exclude from buyer set
    r'Yorkdale Shopping Centre|Yorkville Village|CF Toronto Eaton Centre|'
    r'CF Shops at Don Mills|Bayview Village|North York Centre|Designer Row|'
    r'Scarborough Town Centre|Sherway Gardens|Fairview Mall|Square One|'
    r'Eaton Centre|Pacific Mall'
    r')\b)'
    # Special-case names with non-word chars at the boundary (\b doesn't fire after `?`):
    r'|(?:\bsize\?)',
    re.I,
)

# Sub-brand sites of a chain whose contact email gives away the parent.
DSO_EMAIL_DOMAINS: set[str] = {
    'walmart.ca', 'walmart.com',
    'costco.ca', 'costco.com',
    'canadiantire.ca',
    'thebay.com', 'hbc.com',
    'winners.ca', 'homesense.ca', 'marshalls.ca',
    'homedepot.ca', 'lowes.ca', 'rona.ca',
    'ikea.com',
    'bestbuy.ca',
    'dollarama.com',
    'loblaws.ca', 'metro.ca', 'sobeys.com',
    'shoppersdrugmart.ca', 'rexall.ca',
    'lululemon.com', 'arcteryx.com', 'nike.com', 'adidas.com',
    'roots.com', 'reitmans.com',
    'sephora.ca', 'sephora.com',
    'indigo.ca', 'chapters.ca',
    'apple.com',
    'leons.ca', 'thebrick.com',
    'cadillacfairview.com',  # mall operator
    'oxfordproperties.com',  # mall operator
}

# Toronto neighborhood prefixes that look like brand prefixes but are just
# location qualifiers ("Yorkville Boutique" vs "Leslieville Boutique" — not
# a chain, just two boutiques in different neighborhoods).
GEOGRAPHIC_PREFIXES: set[str] = {
    'downtown toronto', 'north york', 'scarborough', 'etobicoke',
    'east york', 'york', 'yorkville', 'queen west', 'queen east',
    'kensington market', 'kensington', 'the beaches', 'leslieville',
    'liberty village', 'parkdale', 'bloor west', 'bloor street',
    'king west', 'king east', 'distillery district', 'roncesvalles',
    'church-wellesley', 'cabbagetown', 'rosedale', 'forest hill',
    'st. clair', 'eglinton', 'lawrence', 'don mills',
    'toronto', 'gta',
}


# ─────────────────────────────────────────────────────────────────────────────
# Region / metro configuration
# ─────────────────────────────────────────────────────────────────────────────
# GTA area codes. 416/647/437 are core Toronto; 905/289/365 are surrounding
# 905-belt cities (Mississauga, Brampton, Markham, etc.) — included because
# the scrape's "Toronto region" framing pulls in border neighborhoods.
METRO_AREA_CODES: dict[str, set[str]] = {
    'toronto': {'416', '647', '437', '905', '289', '365'},
}

METROS = ['toronto']

QUERIES_DIR = 'queries'


# ─────────────────────────────────────────────────────────────────────────────
# Filter rules for the "small-to-medium independents" view
# ─────────────────────────────────────────────────────────────────────────────
INDEPENDENT_FILTERS = {
    'max_rating_exclusive': 5.0,
    'min_pain_categories':  1,
    'exclude_chains':       True,
}
