"""
Phone-number validation, region-agnostic.

Currently supports:
  - NANP (US/Canada): 10-digit, optionally prefixed with `+1` / `1`.
    Area code shape: 3 digits, first digit 2-9.
  - Ukraine (UA):     9-digit national, E.164 prefixed with `+380` / `380`.
    Area code shape: 2 digits.

Validates:
  - Shape (length + area-code rules per region)
  - Optional: that the area code is in a caller-supplied metro→codes map.

Returns (valid, reason). reason categories:
  malformed         — couldn't normalize to a known regional shape
  invalid_area_code — NANP area code not first-digit 2-9
  metro_mismatch    — number is real but not in the lead's metro area-code set

Region knobs (metro→area-code maps) live in
`pipelines/<vertical>/config.py:METRO_AREA_CODES` and are passed in by the
caller. Area-code strings must match the region's native shape (3-digit NANP,
2-digit UA without the trunk-0).
"""
import re
from typing import Optional, Tuple

# NANP area-code shape: 3 digits, first 2-9.
NANP_AREA_RE = re.compile(r'^[2-9]\d{2}$')

# Region marker — `normalize` tags this as a sidecar of the digits string by
# returning a 9- or 10-digit string. validate_phone() routes on length.
NANP_NATIONAL_LEN = 10
UA_NATIONAL_LEN = 9


def normalize(phone: str) -> Optional[str]:
    """Strip formatting; return national-digits-only string for any supported region,
    or None if the input doesn't match a known regional shape.

    - Ukrainian E.164: 12 digits starting with `380` → strip `380` → 9 digits.
    - NANP: 11 digits starting with `1` → strip → 10 digits; or already 10 digits.
    """
    if not phone or not isinstance(phone, str):
        return None
    digits = re.sub(r'\D', '', phone)
    # Ukrainian first: 380 prefix unambiguously identifies UA E.164.
    if len(digits) == 12 and digits.startswith('380'):
        return digits[3:]
    # NANP.
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    if len(digits) == NANP_NATIONAL_LEN:
        return digits
    return None


def validate_phone(
    phone: str,
    metro: Optional[str] = None,
    *,
    metro_area_codes: Optional[dict[str, set[str]]] = None,
) -> Tuple[bool, Optional[str]]:
    """Validate `phone` shape and (if `metro` and `metro_area_codes` are
    provided) that its area code matches the metro.

    Region is detected from the normalized digit length (NANP=10, UA=9).
    """
    digits = normalize(phone)
    if not digits:
        return False, 'malformed'
    if len(digits) == NANP_NATIONAL_LEN:
        area = digits[:3]
        if not NANP_AREA_RE.match(area):
            return False, 'invalid_area_code'
    elif len(digits) == UA_NATIONAL_LEN:
        area = digits[:2]
        # UA area codes include 04X landlines and mobile prefixes (50, 63, 66-68,
        # 73, 93, 95-99). No analog of NANP's "first digit must be 2-9" applies.
    else:
        return False, 'malformed'  # unreachable given normalize's contract
    if metro and metro_area_codes:
        expected = metro_area_codes.get(metro.lower())
        if expected and area not in expected:
            return False, 'metro_mismatch'
    return True, None
