"""
Dental Sunbelt campaign — single source of truth for industry-specific knobs.

Everything dental-specific lives here. The shared `outreach/lib/` modules are
generic and consume this config. To start a new vertical, copy this file and
edit the values.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Make `lib.*` importable when this config is loaded by orchestration scripts
# that don't already put outreach/ on sys.path.
_OUTREACH_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_OUTREACH_ROOT) not in sys.path:
    sys.path.insert(0, str(_OUTREACH_ROOT))

from lib.enrichers.website_crawl import EnrichProfile

# ─────────────────────────────────────────────────────────────────────────────
# Pain ranking weights (used by lib/ranking.py:quality_score)
# ─────────────────────────────────────────────────────────────────────────────
# NOTE: keys are still the legacy flat category names. The pain-classifier
# subagent (.claude/agents/pain-classifier.md) emits (main, sub) tuples
# against the STL hierarchy in outreach/silverthread/pain_categories.md.
# Re-key to (main, sub) tuples when ranking is rewired against the new
# taxonomy.
PAIN_WEIGHTS: dict[str, int] = {
    'missed_calls_unreachable':         5,
    'after_hours_emergency':            5,
    'insurance_verification_missing':   5,
    'appointment_booking_delay':        4,
    'no_show_reminder_missing':         4,
    'language_barrier_spanish':         3,
    'recall_followup_missing':          3,
    'intake_paperwork_duplication':     3,
    'billing_errors':                   2,
    'long_wait_in_chair':               2,
    'staff_rude_front_desk':            1,
}


# Pain → Silverthread service mapping. Same flat-key shape as PAIN_WEIGHTS;
# both will be re-keyed to (main, sub) tuples once the pain-classifier
# subagent's output is wired into ranking + handoff (TODO.md).
SERVICE_MAP: dict[str, tuple[str, str]] = {
    'missed_calls_unreachable':       ('Voice AI for Dental (AI Receptionist)',         'silverthreadlabs.com/services/voice-agents/dental'),
    'after_hours_emergency':          ('After-Hours Voice Coverage',                    'silverthreadlabs.com/services/voice-agents/after-hours-coverage'),
    'appointment_booking_delay':      ('Voice AI Appointment Booking',                  'silverthreadlabs.com/services/voice-agents/appointment-booking'),
    'long_wait_in_chair':             ('Workflow Automation (Scheduling)',              'silverthreadlabs.com/services/workflow-automation'),
    'insurance_verification_missing': ('Insurance Eligibility Verification Workflow',   'silverthreadlabs.com/services/workflow-automation'),
    'billing_errors':                 ('Billing Automation / Practice Management',      'silverthreadlabs.com/services/agentic-ai'),
    'recall_followup_missing':        ('Outbound Recall Campaigns',                     'silverthreadlabs.com/services/voice-agents/outbound-campaigns'),
    'intake_paperwork_duplication':   ('Patient Intake Automation',                     'silverthreadlabs.com/services/voice-agents/patient-client-intake'),
    'no_show_reminder_missing':       ('Automated Appointment Reminders',               'silverthreadlabs.com/services/voice-agents/outbound-campaigns'),
    'staff_rude_front_desk':          ('AI Receptionist (consistent tone)',             'silverthreadlabs.com/services/voice-agents/ai-receptionist'),
    'language_barrier_spanish':       ('Multilingual (Spanish) Voice Agent',            'silverthreadlabs.com/services/voice-agents/dental'),
}


# ─────────────────────────────────────────────────────────────────────────────
# Email validation extras (consumed by lib/validators/email.py)
# ─────────────────────────────────────────────────────────────────────────────
# Dental-specific marketing / template / forwarding vendors. The lib's
# generic VENDOR_DOMAINS already covers wix/squarespace/hubspot/etc; this
# extends it with vendors only seen on dental sites.
VENDOR_DOMAINS_EXTRA: frozenset[str] = frozenset({
    'gargle.com',           # dental marketing
    'officite.com',         # website builder for medical / dental
    'mydentalmail.com',     # dental template/forwarding service
    'dentalqore.com',       # dental website builder
    'progressivedental.com',# dental marketing / consulting (conservative — drop if real practices use)
})


# ─────────────────────────────────────────────────────────────────────────────
# Website-crawl enrichment profile (consumed by lib/enrichers/website_crawl.py)
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# Chain / DSO detection — dental industry specifics
# ─────────────────────────────────────────────────────────────────────────────
DSO_TITLE_REGEX = re.compile(
    r'\b('
    # Top national DSOs
    r'Aspen Dental|Heartland Dental|Pacific Dental|Smile Direct|SmileDirectClub|'
    r'Western Dental|Great Expressions|Sage Dental|Affordable Dentures|Affordable Care|'
    r'Gentle Dental|Comfort Dental|Monarch Dental|Kool Smiles|Mint Dentistry|'
    r'Dental Depot|Castle Dental|Birner|Jefferson Dental|ClearChoice|Perfect Teeth|'
    # Smile Brands family
    r'Smile Brands|Bright Now|Merit Dental|Midwest Dental|Mondovi Dental|'
    r'Smile Generation|'
    # Other big DSOs
    r'Dental Care Alliance|North American Dental|NADG|Tend Dental|'
    r'Benevis|MB2 Dental|42 North Dental|InterDent|Smile Doctors|'
    r'My Dentist Group|Aspida Dental|'
    # Florida-heavy chains (Tampa)
    r'Coast Dental|Florida Dental Centers|'
    # Arizona/Sunbelt chains (Phoenix)
    r'Risas Dental|Anytime Dental|Smile Dental Clinics|'
    # Multi-state budget chains
    r'Ideal Dental|Rose Dental Group|Advanced Dental Care of|'
    # Other repeat-offender brands
    r'Signature Smiles|Coast Dental Smilecare|Smilecare|Westwind Dental|'
    r'The Smile Design'
    r')\b', re.I,
)

# Sub-brand sites of a DSO often hide the parent name in the title but expose
# it via the email domain (info@<location>@nadentalgroup.com routes to corp).
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

# Geographic prefixes that look like brand prefixes (Phoenix/Mesa/Round Rock
# share-a-prefix but are NOT chains). Excluded from auto-chain detection.
GEOGRAPHIC_PREFIXES: set[str] = {
    # Phoenix metro
    'chandler dental', 'mesa dental', 'gilbert dental', 'tempe dental',
    'scottsdale dental', 'glendale dental', 'phoenix dental',
    # Austin metro
    'south austin', 'north austin', 'east austin', 'west austin',
    'downtown austin', 'austin dental', 'round rock', 'cedar park',
    'pflugerville dental', 'lakeway dental',
    # Tampa metro
    'south tampa', 'north tampa', 'new tampa', 'downtown tampa',
    'tampa dental', 'brandon dental', 'st petersburg', 'st. petersburg',
    'clearwater dental', 'wesley chapel',
    # Generic descriptors
    'family dental', 'general dental', 'cosmetic dental', 'modern dental',
    'advanced dental', 'gentle dental',
}


# ─────────────────────────────────────────────────────────────────────────────
# Region / metro configuration
# ─────────────────────────────────────────────────────────────────────────────
METRO_AREA_CODES: dict[str, set[str]] = {
    'phoenix': {'480', '602', '623', '928'},
    'austin':  {'512', '737'},
    'tampa':   {'813', '727', '941'},
}

METROS = ['phoenix', 'austin', 'tampa']

QUERIES_DIR = 'queries'   # relative to this config's directory


# ─────────────────────────────────────────────────────────────────────────────
# Filter rules for the "local independents" view
# ─────────────────────────────────────────────────────────────────────────────
INDEPENDENT_FILTERS = {
    'max_rating_exclusive': 5.0,        # exclude perfect 5.0★ (no room to improve)
    'min_pain_categories':  1,          # must have at least 1 detected pain
    'exclude_chains':       True,
}
