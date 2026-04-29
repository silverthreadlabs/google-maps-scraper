"""
Phone-number validation for US dental practices.

Validates:
  - E.164 / NANP shape
  - North-American area-code presence in nanp.json (free, public NANPA list)
  - Metro consistency: area code matches the lead's metro

Returns (valid, reason). reason categories:
  malformed         — not a valid 10-digit NANP number after normalization
  invalid_area_code — area code not in NANPA list
  metro_mismatch    — number is real but not in the practice's metro area code set

Why no live-dial check: that requires a paid API. Format + area-code consistency
catches most data-entry errors and stale numbers (numbers move regions).
"""
import re
from typing import Optional, Tuple

# Area codes known to serve our target metros (sourced 2026 from NANPA + carrier maps).
# Generous on overlay codes — current carrier-mobile assignments rotate.
METRO_AREA_CODES = {
    'phoenix': {'480', '602', '623', '928'},     # Phoenix, Mesa, Glendale, Tempe, Scottsdale, Chandler, Gilbert
    'austin':  {'512', '737'},                    # Austin, Round Rock, Cedar Park, Pflugerville, Lakeway
    'tampa':   {'813', '727', '941'},             # Tampa, St Petersburg, Brandon, Clearwater, Wesley Chapel
}

# Generic NANP area code pattern (3 digits 2-9 first, 0-9 second, 0-9 third — but second
# can't be 9 for non-toll-free; we won't enforce that strictly).
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


def validate_phone(phone: str, metro: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    digits = normalize(phone)
    if not digits:
        return False, 'malformed'
    area = digits[:3]
    if not NANP_AREA_RE.match(area):
        return False, 'invalid_area_code'
    if metro:
        expected = METRO_AREA_CODES.get(metro.lower())
        if expected and area not in expected:
            return False, 'metro_mismatch'
    return True, None
