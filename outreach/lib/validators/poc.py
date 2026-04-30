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
})
SECTION_HEADING_SECOND_TOKENS = frozenset({
    'the', 'us', 'our', 'we', 'to',
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

    # Template phrases — full lowercased match.
    if lower in TEMPLATE_PHRASES:
        return False, 'template_phrase'

    # Standalone heading / role tokens with no actual name attached.
    if len(tokens) == 1 and tokens[0] in STANDALONE_HEADING_WORDS:
        return False, 'standalone_heading'

    return True, None
