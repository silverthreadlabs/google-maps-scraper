"""
Strict doctor-name extraction for dental-practice POCs.

The crawler's in-page JS extracts loose candidates (any heading/alt text matching
"Dr." or a credential). This module is the gate that decides whether a candidate
is a real person-of-contact name.

Two valid patterns:
  1. Title prefix:  "Dr. <Name>"  or  "Dr <Name>"
  2. Credential suffix: "<Name>, DDS"  or  "<Name> DMD"  etc.

Rejected:
  - Bare "Dr" as a street suffix ("Hancock Dr", "123 Maple Dr.")
  - Generic practice/text strings without a clear person name
"""
import re
from typing import Optional

# Medical credentials we recognize as a postnominal that licenses a name.
# The order matters less than completeness; case-insensitive matching.
CREDENTIALS = [
    r'D\.?D\.?S\.?',     # DDS / D.D.S.
    r'D\.?M\.?D\.?',     # DMD / D.M.D.
    r'M\.?D\.?',         # MD
    r'M\.?S\.?',         # MS
    r'Ph\.?D\.?',        # PhD
    r'M\.?P\.?H\.?',     # MPH
    r'D\.?O\.?',         # DO
]
CRED_RE = '(?:' + '|'.join(CREDENTIALS) + ')'

# A name token: starts with capital, contains letters / apostrophes / hyphens.
# Min 2 chars to avoid "Dr" itself qualifying as a name token.
NAME_TOK = r"[A-Z][A-Za-z'‘’—-]{1,}"

# Optional middle initial: "M" or "M."
MIDDLE = r"(?:\s+[A-Z]\.?)?"

# Full first+(middle)+last name.
FULL_NAME = rf"{NAME_TOK}{MIDDLE}\s+{NAME_TOK}(?:\s+{NAME_TOK})?"

# Pattern 1: "Dr. <Name>" or "Dr <Name>" — Dr token must be followed by a real name.
# We require the period or end-of-token after Dr so "Hancock Dr" (suffix) doesn't match.
TITLE_PREFIX = re.compile(
    rf"\bDr\.\s+({FULL_NAME})\b"        # "Dr. John Smith"
    rf"|"
    rf"\bDr\s+(Mr\.|Mrs\.|Ms\.|Miss\s+)?({FULL_NAME})\b",  # "Dr John Smith" — bare Dr followed by name
)

# Pattern 2: "<Name>, DDS" or "<Name> DDS" — a name followed by a recognized credential.
CRED_SUFFIX = re.compile(
    rf"\b({FULL_NAME})\s*,?\s*{CRED_RE}\b",
    re.IGNORECASE,
)

# Strings that look like locations/addresses and should be rejected even if
# they superficially match.
ADDRESS_HINT = re.compile(
    r"(\d+\s|\bsuite\b|\bste\.?\b|\bblvd\b|\bave\b|\bavenue\b|\bstreet\b|\bst\.?\b|"
    r"\broad\b|\brd\.?\b|\bdrive\b|\blane\b|\bln\.?\b|\bcourt\b|\bct\.?\b|"
    r"\bplace\b|\bpl\.?\b|\bparkway\b|\bpkwy\b|\bhighway\b|\bhwy\b)",
    re.IGNORECASE,
)

# Practice-name tokens — when present, the candidate is the practice itself.
PRACTICE_TOKENS = {
    'dental', 'dentistry', 'smiles', 'smile', 'orthodontics', 'orthodontic',
    'clinic', 'office', 'practice', 'family', 'pediatric', 'cosmetic',
    'periodontics', 'endodontics',
}


def looks_like_practice_name(name: str, lead_title: Optional[str] = None) -> bool:
    """True if the candidate is plausibly the practice itself, not a person."""
    if not name:
        return True
    n = name.lower()
    tokens = set(re.split(r"\s+", n))
    if tokens & PRACTICE_TOKENS:
        return True
    if lead_title:
        t = lead_title.lower()
        if n in t or t.startswith(n):
            return True
    return False


def extract_doctor_name(text: str, lead_title: Optional[str] = None) -> Optional[str]:
    """
    Given a raw heading/alt-text string, return a doctor's full name if one is
    confidently present. Returns None otherwise.
    """
    if not text or not isinstance(text, str):
        return None
    text = text.replace(' ', ' ')
    text = text.split('\n', 1)[0].strip()
    if len(text) < 4 or len(text) > 100:
        return None

    if ADDRESS_HINT.search(text):
        return None

    m = TITLE_PREFIX.search(text)
    if m:
        # Two alternatives in TITLE_PREFIX; pick the first non-empty group.
        for g in (m.group(1), m.group(3)):
            if g:
                name = g.strip()
                if not looks_like_practice_name(name, lead_title):
                    return name
                return None

    m = CRED_SUFFIX.search(text)
    if m:
        name = m.group(1).strip()
        if not looks_like_practice_name(name, lead_title):
            return name

    return None
