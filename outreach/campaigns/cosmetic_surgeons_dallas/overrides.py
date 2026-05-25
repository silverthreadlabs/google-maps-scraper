"""Cosmetic Surgeons Dallas — regional dermatology DSO overrides."""
from __future__ import annotations

import re

DSO_TITLE_REGEX_EXTRA = re.compile(
    r'\b('
    r'US Dermatology Partners|USDP|'
    r'Schweiger Dermatology|'
    r'Forefront Dermatology|'
    r'Pinnacle Dermatology|'
    r'Epiphany Dermatology|'
    r'Westlake Dermatology'
    r')\b', re.I,
)

DSO_EMAIL_DOMAINS_EXTRA = {
    'usdermatologypartners.com',
    'schweigerderm.com',
    'forefrontdermatology.com',
    'pinnacleskin.com',
    'epiphanydermatology.com',
    'westlakedermatology.com',
}
