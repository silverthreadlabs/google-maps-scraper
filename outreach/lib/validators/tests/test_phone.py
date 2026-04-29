"""Tests for outreach.lib.validators.phone (stdlib unittest)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.validators.phone import validate_phone, normalize


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
            ('+1 813-636-9400', 'tampa'),    # Tampa
            ('(727) 555-1234',  'tampa'),    # St Petersburg
            ('+1 480-786-1734', 'phoenix'),  # Chandler
            ('+1 512-218-1900', 'austin'),   # Round Rock
            ('+1 737-444-5555', 'austin'),   # Austin overlay
            ('602-266-1776',    'phoenix'),  # Phoenix
        ]
        for phone, metro in cases:
            with self.subTest(phone=phone):
                ok, reason = validate_phone(phone, metro)
                self.assertTrue(ok, f"expected valid, got {reason}")
                self.assertIsNone(reason)

    def test_metro_mismatch(self):
        # Real number, wrong metro
        cases = [
            ('+1 813-636-9400', 'phoenix'),  # Tampa number, Phoenix lead
            ('+1 480-786-1734', 'austin'),   # Phoenix number, Austin lead
        ]
        for phone, metro in cases:
            with self.subTest(phone=phone):
                ok, reason = validate_phone(phone, metro)
                self.assertFalse(ok)
                self.assertEqual(reason, 'metro_mismatch')

    def test_no_metro_skips_metro_check(self):
        ok, reason = validate_phone('+1 813-636-9400', metro=None)
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_malformed(self):
        for phone in ['', None, '123', 'abc-def-ghij', '813-636']:
            with self.subTest(phone=phone):
                ok, reason = validate_phone(phone)
                self.assertFalse(ok)
                self.assertEqual(reason, 'malformed')

    def test_invalid_area_code(self):
        # Area codes starting with 0 or 1 are not valid NANP
        cases = ['+1 013-555-1234', '+1 100-555-1234']
        for phone in cases:
            with self.subTest(phone=phone):
                ok, reason = validate_phone(phone)
                self.assertFalse(ok)
                self.assertEqual(reason, 'invalid_area_code')


if __name__ == '__main__':
    unittest.main(verbosity=2)
