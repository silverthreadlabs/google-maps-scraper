"""Tests for outreach.lib.validators.phone (stdlib unittest)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.validators.phone import validate_phone, normalize


# Use the dental-sunbelt metro→area-code map as the test fixture.
# It's the only vertical we ship today; if a second one lands, we can pull
# this from pipelines/<name>/config.py.
DENTAL_METRO_AREA_CODES = {
    'phoenix': {'480', '602', '623', '928'},
    'austin':  {'512', '737'},
    'tampa':   {'813', '727', '941'},
}


class TestNormalize(unittest.TestCase):
    def test_strip_formatting(self):
        cases = [
            ('+1 813-636-9400', '8136369400'),
            ('(813) 636-9400',  '8136369400'),
            ('813.636.9400',    '8136369400'),
            ('813 636 9400',    '8136369400'),
            ('+18136369400',    '8136369400'),
            ('18136369400',     '8136369400'),
            ('8136369400',      '8136369400'),
        ]
        for inp, exp in cases:
            with self.subTest(inp=inp):
                self.assertEqual(normalize(inp), exp)

    def test_reject(self):
        for inp in ['', None, '12345', '+44 20 7946 0958', 'abc', '813-636']:
            with self.subTest(inp=inp):
                self.assertIsNone(normalize(inp))


class TestValidate(unittest.TestCase):
    def test_valid_metro_match(self):
        cases = [
            ('+1 813-636-9400', 'tampa'),
            ('(727) 555-1234',  'tampa'),
            ('+1 480-786-1734', 'phoenix'),
            ('+1 512-218-1900', 'austin'),
            ('+1 737-444-5555', 'austin'),
            ('602-266-1776',    'phoenix'),
        ]
        for phone, metro in cases:
            with self.subTest(phone=phone):
                ok, reason = validate_phone(phone, metro, metro_area_codes=DENTAL_METRO_AREA_CODES)
                self.assertTrue(ok, f"expected valid, got {reason}")
                self.assertIsNone(reason)

    def test_metro_mismatch(self):
        cases = [
            ('+1 813-636-9400', 'phoenix'),  # Tampa number, Phoenix lead
            ('+1 480-786-1734', 'austin'),   # Phoenix number, Austin lead
        ]
        for phone, metro in cases:
            with self.subTest(phone=phone):
                ok, reason = validate_phone(phone, metro, metro_area_codes=DENTAL_METRO_AREA_CODES)
                self.assertFalse(ok)
                self.assertEqual(reason, 'metro_mismatch')

    def test_no_metro_skips_metro_check(self):
        ok, reason = validate_phone('+1 813-636-9400', metro=None,
                                    metro_area_codes=DENTAL_METRO_AREA_CODES)
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_no_metro_area_codes_skips_metro_check(self):
        # Caller didn't supply the metro→codes map (e.g. validating a phone
        # before the pipeline config is loaded). Shape check still runs; the
        # metro arg is silently ignored.
        ok, reason = validate_phone('+1 813-636-9400', metro='phoenix',
                                    metro_area_codes=None)
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_unknown_metro_in_codes_skips_check(self):
        # metro_area_codes is provided, but doesn't contain this metro key.
        # Existing dental-pipeline behavior was to skip the check rather than
        # treat it as a mismatch — preserved here.
        ok, reason = validate_phone('+1 813-636-9400', metro='boston',
                                    metro_area_codes=DENTAL_METRO_AREA_CODES)
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_malformed(self):
        for phone in ['', None, '123', 'abc-def-ghij', '813-636']:
            with self.subTest(phone=phone):
                ok, reason = validate_phone(phone)
                self.assertFalse(ok)
                self.assertEqual(reason, 'malformed')

    def test_invalid_area_code(self):
        # Area codes starting with 0 or 1 are not valid NANP.
        for phone in ['+1 013-555-1234', '+1 100-555-1234']:
            with self.subTest(phone=phone):
                ok, reason = validate_phone(phone)
                self.assertFalse(ok)
                self.assertEqual(reason, 'invalid_area_code')


if __name__ == '__main__':
    unittest.main(verbosity=2)
