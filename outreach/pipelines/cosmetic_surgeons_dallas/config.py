"""
Cosmetic Surgeons Dallas campaign — exploratory pipeline.

Scope: cosmetic + plastic surgery practices across the Dallas / Plano /
Frisco metroplex. Data is heavily independent-practice (52 plastic
surgeons, 12 plastic surgery clinics, 4 cosmetic surgeons, 1 medspa,
1 dermatologist in the seed scrape) — DSO/chain coverage is light by
design and will grow as new chain hits appear.

Note: the STL pain taxonomy in silverthread/pain_categories.md is
vertical-agnostic, so PAIN_WEIGHTS and SERVICE_MAP are unchanged from
dental_sunbelt. Re-tune after the first classify run if the cosmetic
surgery pain distribution differs materially from general service-
business assumptions.
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
# Pain ranking weights — vertical-agnostic STL hierarchy.
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
# Cosmetic-surgery / medical-aesthetics marketing vendors. Conservative —
# extend as new vendor patterns appear in scraped emails.
VENDOR_DOMAINS_EXTRA: frozenset[str] = frozenset({
    'rosemontmedia.com',     # cosmetic surgery website / marketing vendor
    'influxmarketing.com',   # medspa / cosmetic marketing
    'studioiii.com',         # medical aesthetics websites
})


# ─────────────────────────────────────────────────────────────────────────────
# Website-crawl enrichment profile — cosmetic / plastic surgery POC titles
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# Chain / DSO detection — national cosmetic / plastic surgery chains
# ─────────────────────────────────────────────────────────────────────────────
# Light by design — most Dallas-metro cosmetic surgery is independent
# practice. Add brands here as repeat-offender chain hits appear in
# scrape output.
DSO_TITLE_REGEX = re.compile(
    r'\b('
    # National cosmetic / plastic surgery chains
    r'Sono Bello|SonoBello|'
    r'LaserAway|Laser Away|'
    r'Ideal Image|'
    r'Skinney Medspa|'
    r'Athena Cosmetic|'
    # National dermatology DSOs (Dallas presence)
    r'US Dermatology Partners|USDP|'
    r'Schweiger Dermatology|'
    r'Forefront Dermatology|'
    r'Pinnacle Dermatology|'
    r'Epiphany Dermatology|'
    r'Westlake Dermatology|'      # 21 TX locations — Austin HQ, corporate-run

    # Hair / cosmetic chains
    r'Bosley|Hair Club|'
    # Generic chain markers
    r'Plastic Surgery Group of'
    r')\b', re.I,
)

# Sub-brand sites of a chain often hide the parent in the title but expose
# it via the email domain.
DSO_EMAIL_DOMAINS: set[str] = {
    'sonobello.com',
    'laseraway.com',
    'idealimage.com',
    'usdermatologypartners.com',
    'schweigerderm.com',
    'forefrontdermatology.com',
    'pinnacleskin.com',
    'epiphanydermatology.com',
    'westlakedermatology.com',
    'bosley.com',
    'hairclub.com',
}

# Dallas-metro neighborhood / city prefixes that look like brand prefixes
# but are just location qualifiers ("Plano Plastic Surgery" vs "Frisco
# Plastic Surgery" — different practices, not a chain).
GEOGRAPHIC_PREFIXES: set[str] = {
    # Dallas core + neighborhoods
    'dallas', 'north dallas', 'downtown dallas', 'uptown dallas',
    'oak lawn', 'oak cliff', 'lakewood', 'deep ellum', 'bishop arts',
    'knox-henderson', 'lower greenville', 'design district',
    'victory park', 'west village', 'preston hollow',
    'park cities', 'highland park', 'university park',
    # Surrounding / DFW metroplex
    'plano', 'frisco', 'mckinney', 'allen', 'prosper',
    'richardson', 'addison', 'garland', 'mesquite',
    'irving', 'las colinas', 'lewisville', 'flower mound',
    'southlake', 'grapevine', 'colleyville',
    'fort worth', 'arlington',
    # State-level qualifiers
    'north texas', 'texas', 'dfw', 'metroplex',
    # Generic descriptors that look like brand prefixes
    'advanced cosmetic', 'modern cosmetic', 'premier plastic',
    'advanced plastic', 'modern plastic', 'aesthetic',
    'family cosmetic',
}


# ─────────────────────────────────────────────────────────────────────────────
# Region / metro configuration
# ─────────────────────────────────────────────────────────────────────────────
# DFW metroplex area codes. 214/469/972 cover Dallas/Plano/Frisco/Irving;
# 945 is the newer Dallas overlay; 817/682 cover Fort Worth / Arlington
# (included for border practices).
METRO_AREA_CODES: dict[str, set[str]] = {
    'dallas': {'214', '469', '972', '945', '817', '682'},
}

METROS = ['dallas']

QUERIES_DIR = 'queries'


# ─────────────────────────────────────────────────────────────────────────────
# Filter rules for the "local independents" view
# ─────────────────────────────────────────────────────────────────────────────
INDEPENDENT_FILTERS = {
    'max_rating_exclusive': 5.0,        # exclude perfect 5.0★ (no room to improve)
    'min_pain_categories':  1,          # must have at least 1 detected pain
    'exclude_chains':       True,
}
