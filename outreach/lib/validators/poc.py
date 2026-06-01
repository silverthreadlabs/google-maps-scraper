"""
Validate POC (point-of-contact) names extracted from website crawls.

`validate_poc(name) -> (valid, reason)`

`reason` is a short tag suitable for the `invalid_reason` field on a POC
dict. Returns (True, None) for names that look like real human candidates.

Categories of invalid:
  malformed           — empty / non-string / fewer than 3 chars
  section_heading     — page section label captured by the heading-name
                        extractor ('MEET THE', 'OUR TEAM', 'ABOUT US')
  template_phrase     — generic role label that looks name-like
                        ('Our Founder', 'The Owner')
  standalone_heading  — bare heading or role word with no actual name
                        ('Meet', 'About', 'Team', 'CEO')

The heading-name extractor in `lib/enrichers/website_crawl.py` truncates
heading text to the first two tokens, so most of these are 2-token
fragments of longer headings.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

# Standalone heading / role words (lowercased, exact-match) that the heading
# extractor sometimes captures with no actual name attached.
STANDALONE_HEADING_WORDS = frozenset({
    'meet', 'about', 'contact', 'welcome', 'hello',
    'team', 'staff', 'doctors', 'owner', 'founder', 'ceo', 'manager',
    'who', 'what', 'where', 'why',
})

# Two-word fragments where the first token is a section-label opener. The
# heading extractor truncates `MEET THE TEAM` → `MEET THE`, `WHO WE ARE` →
# `WHO WE`, etc. Match on the (first_token_lower, second_token_lower) tuple.
SECTION_HEADING_OPENERS = frozenset({
    'meet', 'about', 'contact', 'welcome', 'who',
    'what', 'why', 'when', 'where', 'how',  # `What We Offer`, `Why Dr.`, etc.
    'in',                                    # `In The News`, `In The Press`
})
SECTION_HEADING_SECOND_TOKENS = frozenset({
    'the', 'us', 'our', 'we', 'to',
    'dr',                                    # `Meet Dr`, `Contact Dr`, `About Dr` (truncated practice headers)
})

# Leading words that no real given name uses — determiners, pronouns,
# question words, and marketing-copy openers. When one of these heads a
# two-token capture it's a heading/marketing fragment the extractor
# truncated, regardless of the (arbitrary) second token: `Your AI-Native`,
# `Why San`, `The DJ`, `Our CEO's`, `App Like`. Matched on the exact first
# token (lowercased), so real names like `Theodore`, `Owen`, `Apple` are
# untouched. The TEMPLATE_PHRASES check runs first, so `Our Founder` /
# `The Owner` keep their more-specific reason.
NON_NAME_LEADING_WORDS = frozenset({
    'your', 'our', 'the', 'app', 'we', 'let', 'this', 'that',
    'why', 'what', 'who', 'how', 'when', 'where', 'whose', 'whom',
})

# Two-word role/section labels that look name-like. Lowercased exact match.
TEMPLATE_PHRASES = frozenset({
    'our founder', 'our ceo', 'our doctor', 'our doctors',
    'our owner', 'our team', 'our staff', 'our story',
    'our mission', 'our values',
    'the owner', 'the founder', 'the team', 'the staff',
    'the ceo', 'the doctor',
})

# A name needs at least one alphabetic char beyond the title prefix and 3+ chars.
_ALPHA_RE = re.compile(r'[A-Za-z]')

MIN_NAME_LEN = 3


# ── Confidence scoring ──────────────────────────────────────────────────
# A 0..1 score so downstream consumers (SDR filters, a future LLM QA pass)
# can RANK POCs instead of a human reading every row. Calibrated on real
# crawl output. This ANNOTATES — it never drops a POC (CLAUDE.md rule 1):
# even a badge scores low rather than being deleted, so a rare false
# penalty only lowers rank.

# Base trust by extraction source — best source wins (max over the set).
# json_ld = schema-declared Person (gold); headings = noisiest (section
# labels, marketing copy); img_alt = mixed (real headshots AND vendor
# badges).
SOURCE_WEIGHTS = {
    'json_ld':    0.70,
    'img_alt':    0.45,
    'heading_h1': 0.25,
    'heading_h2': 0.25,
    'heading_h3': 0.25,
    'heading_h4': 0.25,
}
DEFAULT_SOURCE_WEIGHT = 0.30
ROLE_BOOST = 0.20            # a declared role ('CEO', 'Founder') signals personhood
MULTI_SOURCE_BOOST = 0.10    # corroboration across ≥2 distinct sources
BADGE_PENALTY = 0.45         # name reads as a vendor/certification badge

# Tokens that mark a name as a vendor/certification badge rather than a
# person. PLATFORM names and badge NOUNS that are not plausible surnames.
# Deliberately EXCLUDES ambiguous real surnames (Gold, Top, Member, Stone)
# — the penalty must not silently sink real people.
_BADGE_TOKENS = frozenset({
    # platforms / award bodies
    'google', 'meta', 'facebook', 'microsoft', 'aws', 'amazon', 'shopify',
    'hubspot', 'salesforce', 'adobe', 'clutch', 'webby', 'forbes', 'g2',
    'yelp', 'bing', 'semrush', 'trustpilot',
    # badge nouns (rare/implausible as surnames)
    'partner', 'premier', 'certified', 'accredited', 'sponsor',
    'award', 'awards', 'winning', 'verified',
})


def _looks_like_badge(name: str) -> bool:
    toks = set(_tokenize(name.lower()))
    return bool(toks & _BADGE_TOKENS)


def poc_confidence(poc) -> float:
    """Return a 0..1 confidence that this POC dict is a real, useful contact.

    Signals (all from fields the crawler already captures):
      • extraction source   — json_ld > img_alt > headings
      • declared role        — present → boost
      • corroboration        — ≥2 distinct sources → boost
      • badge vocabulary     — 'Google Partner', 'Webby Awards' → penalty
      • hard-invalid name    — anything validate_poc rejects → 0.0

    Tolerant of missing/malformed fields (returns a low score, never raises).
    """
    if not isinstance(poc, dict):
        return 0.0

    name = poc.get('name')
    # Names validate_poc already rejects aren't worth ranking.
    ok, _ = validate_poc(name)
    if not ok:
        return 0.0

    sources = [s for s in (poc.get('sources') or []) if isinstance(s, str)]
    if sources:
        base = max(SOURCE_WEIGHTS.get(s, DEFAULT_SOURCE_WEIGHT) for s in sources)
    else:
        base = DEFAULT_SOURCE_WEIGHT

    score = base
    if poc.get('role'):
        score += ROLE_BOOST
    if len(set(sources)) >= 2:
        score += MULTI_SOURCE_BOOST
    if _looks_like_badge(name):
        score -= BADGE_PENALTY

    score = max(0.0, min(1.0, score))
    return round(score, 2)


def _tokenize(s: str) -> list[str]:
    """Split on whitespace, keep tokens, drop empty."""
    return [t for t in s.split() if t]


def validate_poc(name) -> Tuple[bool, Optional[str]]:
    """Return (valid, reason). Bare names ('Smith') and titled names
    ('Dr. Patrick') both pass. Section-heading captures and bare role
    words are rejected with a specific reason."""
    if not isinstance(name, str):
        return False, 'malformed'
    n = name.strip()
    if len(n) < MIN_NAME_LEN or not _ALPHA_RE.search(n):
        return False, 'malformed'

    lower = n.lower()
    tokens = _tokenize(lower)

    # Section-heading openers: ('meet', 'the'), ('about', 'us'), ('who', 'we'), …
    if len(tokens) == 2:
        first, second = tokens
        if first in SECTION_HEADING_OPENERS and second in SECTION_HEADING_SECOND_TOKENS:
            return False, 'section_heading'
        if 'meet' == first and second == 'our':
            return False, 'section_heading'
        # "OUR TEAM" / "OUR STAFF" / "OUR STORY" — first token is "our" + filler
        if first == 'our' and second in {'team', 'staff', 'story', 'mission', 'values'}:
            return False, 'section_heading'

    # Template phrases — full lowercased match. Runs BEFORE the broad
    # leading-word rule so `Our Founder` / `The Owner` keep their
    # more-specific 'template_phrase' reason.
    if lower in TEMPLATE_PHRASES:
        return False, 'template_phrase'

    # Two-token captures led by a determiner / pronoun / question word that
    # no real given name uses — heading/marketing fragments with arbitrary
    # second tokens ('Your AI-Native', 'Why San', 'The DJ', 'App Like').
    if len(tokens) == 2 and tokens[0] in NON_NAME_LEADING_WORDS:
        return False, 'section_heading'

    # Standalone heading / role tokens with no actual name attached.
    if len(tokens) == 1 and tokens[0] in STANDALONE_HEADING_WORDS:
        return False, 'standalone_heading'

    return True, None
