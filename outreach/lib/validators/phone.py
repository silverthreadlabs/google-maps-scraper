"""
Phone-number validation for North-American numbers, vertical-agnostic.

Validates:
  - E.164 / NANP shape
  - Optional: that the area code is in a caller-supplied metro→codes map.

Returns (valid, reason). reason categories:
  malformed         — not a valid 10-digit NANP number after normalization
  invalid_area_code — area code not a valid NANP form (first digit must be 2-9)
  metro_mismatch    — number is real but not in the lead's metro area-code set

Why no live-dial check: that requires a paid API. Format + area-code consistency
catches most data-entry errors and stale numbers (numbers move regions).

Vertical / region knobs (e.g. dental sunbelt's `{phoenix, austin, tampa}` →
area-code sets) live in `pipelines/<vertical>/config.py:METRO_AREA_CODES`
and are passed in by the caller.
"""
import re
from typing import Optional, Tuple

# Generic NANP area-code shape (3 digits, first 2-9).
NANP_AREA_RE = re.compile(r'^[2-9]\d{2}$')


def normalize(phone: str) -> Optional[str]:
    """Strip formatting and return digits-only string, or None if not a 10/11-digit NANP number."""
    if not phone or not isinstance(phone, str):
        return None
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    if len(digits) != 10:
        return None
    return digits


def validate_phone(
    phone: str,
    metro: Optional[str] = None,
    *,
    metro_area_codes: Optional[dict[str, set[str]]] = None,
) -> Tuple[bool, Optional[str]]:
    """Validate `phone` shape and (if both `metro` and `metro_area_codes` are
    provided) that its area code matches the metro.

    If `metro_area_codes` is None or doesn't contain `metro`, the metro check
    is skipped — shape validation still runs.
    """
    digits = normalize(phone)
    if not digits:
        return False, 'malformed'
    area = digits[:3]
    if not NANP_AREA_RE.match(area):
        return False, 'invalid_area_code'
    if metro and metro_area_codes:
        expected = metro_area_codes.get(metro.lower())
        if expected and area not in expected:
            return False, 'metro_mismatch'
    return True, None
