"""
Dental Sunbelt campaign — single source of truth for industry-specific knobs.

Everything dental-specific lives here. The shared `outreach/lib/` modules are
generic and consume this config. To start a new vertical, copy this file and
edit the values.
"""
from __future__ import annotations

import re

# ─────────────────────────────────────────────────────────────────────────────
# Pain category catalog
# ─────────────────────────────────────────────────────────────────────────────
# Each category maps review-language to a Silverthread service. When the
# classifier (regex / SBERT / LLM) flags a category, the lead is recommended
# this service. Categories marked "universal" apply to most service-business
# verticals; "health-vertical" categories apply to dental/medical/vet/etc.
PAIN_CATEGORIES = [
    'missed_calls_unreachable',         # universal
    'after_hours_emergency',            # cross-vertical (medical/legal/home-services)
    'appointment_booking_delay',        # universal (any appointment-based)
    'long_wait_in_chair',               # universal-ish ("chair" is dental wording)
    'insurance_verification_missing',   # health-vertical
    'billing_errors',                   # universal
    'recall_followup_missing',          # health-vertical ("recall" is dental term)
    'intake_paperwork_duplication',     # health-vertical
    'no_show_reminder_missing',         # universal
    'staff_rude_front_desk',            # universal
    'language_barrier_spanish',         # universal (region-configurable)
]

# ─────────────────────────────────────────────────────────────────────────────
# Pain → Silverthread service mapping
# ─────────────────────────────────────────────────────────────────────────────
SERVICE_MAP: dict[str, tuple[str, str]] = {
    'missed_calls_unreachable':         ('Voice AI for Dental (AI Receptionist)',         'silverthreadlabs.com/services/voice-agents/dental'),
    'after_hours_emergency':            ('After-Hours Voice Coverage',                    'silverthreadlabs.com/services/voice-agents/after-hours-coverage'),
    'appointment_booking_delay':        ('Voice AI Appointment Booking',                  'silverthreadlabs.com/services/voice-agents/appointment-booking'),
    'long_wait_in_chair':               ('Workflow Automation (Scheduling)',              'silverthreadlabs.com/services/workflow-automation'),
    'insurance_verification_missing':   ('Insurance Eligibility Verification Workflow',   'silverthreadlabs.com/services/workflow-automation'),
    'billing_errors':                   ('Billing Automation / Practice Management',      'silverthreadlabs.com/services/agentic-ai'),
    'recall_followup_missing':          ('Outbound Recall Campaigns',                     'silverthreadlabs.com/services/voice-agents/outbound-campaigns'),
    'intake_paperwork_duplication':     ('Patient Intake Automation',                     'silverthreadlabs.com/services/voice-agents/patient-client-intake'),
    'no_show_reminder_missing':         ('Automated Appointment Reminders',               'silverthreadlabs.com/services/voice-agents/outbound-campaigns'),
    'staff_rude_front_desk':            ('AI Receptionist (consistent tone)',             'silverthreadlabs.com/services/voice-agents/ai-receptionist'),
    'language_barrier_spanish':         ('Multilingual (Spanish) Voice Agent',            'silverthreadlabs.com/services/voice-agents/dental'),
}


# ─────────────────────────────────────────────────────────────────────────────
# Pain ranking weights (used by lib/ranking.py:quality_score)
# ─────────────────────────────────────────────────────────────────────────────
PAIN_WEIGHTS: dict[str, int] = {
    'missed_calls_unreachable':         5,   # flagship Silverthread service fit
    'after_hours_emergency':            5,
    'insurance_verification_missing':   5,   # high-margin workflow automation
    'appointment_booking_delay':        4,
    'no_show_reminder_missing':         4,
    'language_barrier_spanish':         3,
    'recall_followup_missing':          3,
    'intake_paperwork_duplication':     3,
    'billing_errors':                   2,
    'long_wait_in_chair':               2,
    'staff_rude_front_desk':            1,   # soft signal, hard to pitch as AI fix
}


# ─────────────────────────────────────────────────────────────────────────────
# REGEX pain patterns (legacy classifier — superseded by SBERT/LLM)
# Kept for corroboration signal in UNION classifier.
# ─────────────────────────────────────────────────────────────────────────────
PAIN_REGEX_PATTERNS: dict[str, list[str]] = {
    'missed_calls_unreachable': [
        r'\bno( ?one)? (ever )?answer', r'never( ?call(s|ed)?)? back',
        r"(didn'?t|did not|won'?t|wouldn'?t|never) (return|call) (my|the) call",
        r"can'?t (get (a )?hold|reach)", r'\bvoice ?mail\b',
        r'unresponsive', r'no response', r'unanswered',
        r'(never|does ?n.?t|dont|doesnt) (answer|pick ?up) (the )?phone',
        r'impossible to (reach|contact|get)', r'tried (calling|to call) (multiple|several|many)',
        r'left (\d+|several|multiple|many) (voicemails?|messages?)',
    ],
    'after_hours_emergency': [
        r'(no|never|couldn\'?t|unable to|refused|denied).{0,20}(emergenc(y|ies))',
        r'(emergenc(y|ies)|urgent).{0,40}(closed|denied|turned away|no one|told to wait|booked up)',
        r'broken tooth.{0,40}(weekend|night|evening)',
        r'(night|evening|sunday|saturday|weekend).{0,40}(no one|couldn\'?t reach|nobody answered)',
        r'no emergency (line|service|coverage|number)', r'closed when (i|we) needed',
        r'only (open|available) (during|weekdays)',
    ],
    'appointment_booking_delay': [
        r'(weeks?|months?) (out|away|wait)', r'next available',
        r"couldn'?t get an appointment", r"can'?t get in",
        r'booked (solid|out|full)',
        r'(waited|wait) .{0,20}(weeks?|months?) .{0,30}(appointment|see|in)',
        r'scheduling (nightmare|issue|problem)',
    ],
    'long_wait_in_chair': [
        r'waited? .{0,20}(hour|30 min|45 min|an hour|two hours)',
        r'(past|after) .{0,20}(appointment|scheduled) time',
        r'overbooked', r'double[- ]?booked',
        r'sat in (the )?(chair|lobby|waiting room) for',
        r'kept (me|us) waiting',
    ],
    'insurance_verification_missing': [
        r'insurance.{0,30}(not verified|didn.?t verify|never verified|never checked)',
        r"didn'?t (verify|check|confirm) (my )?insurance",
        r'surprise (bill|charge)', r'unexpected (bill|charge|cost)',
        r"wasn'?t covered", r"(didn'?t|did not) (tell|inform) me (it|this) (wasn'?t|was not) covered",
        r'estimate (was )?wrong', r'quoted .{0,30}(different|more|less)',
        r'told .{0,20}covered.{0,30}(but|then)',
        r'out[- ]of[- ]network (without|and) (telling|warning)',
        r'pre[- ]?auth(orization)?',
        r'insurance (denied|rejected)',
    ],
    'billing_errors': [
        r'billed? (twice|two times|multiple times)',
        r'double[- ]?(billed|charged?)', r'(wrong|incorrect) (bill|charge|amount)',
        r'charged .{0,20}(twice|wrong|too much)',
        r'sent to collections', r'refused to refund',
        r"(won'?t|wouldn'?t|never) refund",
    ],
    'recall_followup_missing': [
        r'no (one )?(ever )?(called|contacted) .{0,20}(back|follow)',
        r"never (called|heard) back",
        r'6 ?month (cleaning|checkup|visit).{0,30}(never|forgot|no)',
        r'follow[- ]?up (never|was never|missing)',
        r"didn'?t (follow up|check in)",
        r'treatment plan (never|was never).{0,20}(sent|received|called)',
        r'forgot about (me|us)',
    ],
    'intake_paperwork_duplication': [
        r'(filled? out|filling out) .{0,20}(same|multiple|twice|again)',
        r'(same|multiple|many) forms?',
        r'paper(work)? .{0,20}(again|twice|over)',
        r'had to (re-?)?(fill|submit|send) .{0,20}(again|twice)',
        r'lost (my|our) (records|paperwork|info|forms|x-?rays)',
        r'no (online|digital) (form|intake|check-?in)',
    ],
    'no_show_reminder_missing': [
        r'no (reminder|confirmation)', r'never (reminded|confirmed)',
        r"didn'?t (remind|confirm)",
        r'forgot (about )?(my|the) appointment',
        r'missed (my|the) appointment because',
    ],
    'staff_rude_front_desk': [
        r'front desk.{0,40}(rude|unprofessional|dismissive|condescending)',
        r'receptionist.{0,40}(rude|unprofessional|dismissive|condescending|mean)',
        r'(rude|unprofessional|dismissive|condescending).{0,40}(front desk|receptionist|staff)',
        r'\brude\b', r'unprofessional', r'condescending',
    ],
    'language_barrier_spanish': [
        r'spanish', r'español', r'no (one )?(spoke|speaks) spanish',
        r'language barrier', r'only (speaks|spoke) english',
        r'translator', r'bilingual', r'habla español',
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# SBERT anchor sentences (used by lib/pain/sbert.py)
# ─────────────────────────────────────────────────────────────────────────────
SBERT_ANCHORS: dict[str, list[str]] = {
    'missed_calls_unreachable': [
        "I called multiple times and no one ever answered the phone.",
        "I left several voicemails and they never called me back.",
        "Their phone goes straight to voicemail and they never return calls.",
        "Impossible to reach anyone at this office.",
        "I have called repeatedly and nobody picks up.",
        "They do not answer the phone or return messages.",
    ],
    'after_hours_emergency': [
        "I had a dental emergency on the weekend and the office was closed with no after-hours coverage.",
        "Called for an urgent dental issue at night and there was no emergency line or way to reach a dentist.",
        "Broke a tooth on a Sunday but they had no way to help me until Monday.",
        "Severe pain over the weekend and they refused to see me as an emergency.",
        "There is no after-hours emergency coverage at this practice.",
        "When I had a dental emergency they turned me away and offered no urgent care.",
    ],
    'appointment_booking_delay': [
        "The next available appointment is months away.",
        "I tried to schedule an appointment but they had no availability for weeks.",
        "Couldn't get in to be seen for a long time.",
        "They are booked solid and I had to wait over a month.",
        "Scheduling is a nightmare, they keep rescheduling me.",
        "I called to schedule and was told the next opening was three months out.",
    ],
    'long_wait_in_chair': [
        "I waited over an hour past my appointment time before being seen.",
        "I sat in the waiting room for two hours past my scheduled appointment.",
        "They are always overbooked, I waited 90 minutes in the chair.",
        "Showed up on time and waited an hour past my scheduled time.",
        "Kept me waiting in the chair forever, they were running way behind.",
    ],
    'insurance_verification_missing': [
        "They didn't verify my insurance up front and I got a surprise bill.",
        "Was told it was covered, then got charged a huge unexpected amount.",
        "They never confirmed my coverage and now I owe hundreds.",
        "They said the procedure was in network but it turned out to be out of network.",
        "Insurance was not verified before the visit so I got billed unexpectedly.",
        "Quote was completely different from the actual bill after insurance.",
    ],
    'billing_errors': [
        "I was billed twice for the same procedure.",
        "They charged my card the wrong amount and refused to refund.",
        "Sent me to collections without warning over a billing dispute.",
        "Got hit with hidden fees that were never disclosed up front.",
        "The billing department is impossible to reach to resolve issues.",
        "There was a random charge on my account that nobody could explain.",
    ],
    'recall_followup_missing': [
        "I never heard back from them after my procedure.",
        "Treatment plan was never sent to me after my visit.",
        "They never called to follow up on my surgery.",
        "Forgot about me — never reached out for my six-month checkup.",
        "After my appointment, no one followed up about next steps.",
        "I was supposed to receive a treatment plan and it never came.",
    ],
    'intake_paperwork_duplication': [
        "Had to fill out the same forms multiple times.",
        "They lost my paperwork and made me redo it.",
        "No online intake forms — had to do everything on paper at the office.",
        "I filled out the same patient form three times for one visit.",
        "They couldn't find my records and made me start the paperwork over.",
    ],
    'no_show_reminder_missing': [
        "I never got a reminder for my appointment so I missed it.",
        "They didn't remind me and I forgot about the appointment.",
        "No confirmation call and no text reminder before my visit.",
        "Showed up to a closed office because they cancelled my appointment without telling me.",
        "They cancelled my appointment but never sent me any notice.",
    ],
    'staff_rude_front_desk': [
        "The front desk staff was rude and dismissive.",
        "The receptionist was condescending and unprofessional.",
        "Everyone at the front desk acted like I was bothering them.",
        "Staff at reception treated me poorly and gave me attitude.",
        "The office manager was rude when I tried to ask a question.",
        "The staff were unfriendly and made me feel unwelcome.",
    ],
    'language_barrier_spanish': [
        "Nobody at the office spoke Spanish.",
        "There was a language barrier — no Spanish-speaking staff.",
        "I struggled because no one could communicate in Spanish.",
        "They had no bilingual staff and I had trouble understanding instructions.",
        "Wish there was a Spanish-speaking dentist.",
    ],
}

SBERT_PER_CATEGORY_THRESHOLD: dict[str, float] = {
    'after_hours_emergency':         0.60,
    'no_show_reminder_missing':      0.55,
    'staff_rude_front_desk':         0.40,
    'recall_followup_missing':       0.50,
    'intake_paperwork_duplication':  0.50,
    'billing_errors':                0.45,
    'insurance_verification_missing':0.45,
    'appointment_booking_delay':     0.45,
    'long_wait_in_chair':            0.45,
    'missed_calls_unreachable':      0.45,
    'language_barrier_spanish':      0.50,
}

SBERT_TITLE_DENY_RULES: dict[str, re.Pattern] = {
    'after_hours_emergency': re.compile(r'(emergency|walk[- ]?in|24[- ]?hour|24/7|weekend dental)', re.I),
}


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
