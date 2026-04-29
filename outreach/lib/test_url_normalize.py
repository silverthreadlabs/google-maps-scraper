"""Tests for url_normalize — covers all known tracking-param classes from the dental campaign."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.url_normalize import normalize_url


class TestNormalizeURL(unittest.TestCase):
    def test_strip_utm(self):
        cases = [
            ('https://www.example.com/?utm_source=google&utm_medium=cpc',
             'https://www.example.com'),
            ('https://www.example.com/page?utm_campaign=spring&id=42',
             'https://www.example.com/page?id=42'),
        ]
        for inp, expected in cases:
            with self.subTest(inp=inp):
                self.assertEqual(normalize_url(inp), expected)

    def test_strip_gbp_yext(self):
        # Real example from the dental campaign (Round Rock Modern Dentistry)
        cases = [
            ('https://www.roundrockmoderndentistry.com/?sc_cid=GBP%3AO%3AGP%3A782%3AOrganic_Search%3AGeneral%3Ana&_vsrefdom=organic_gbp&y_source=1_MTkyOTcxOC03MTUtbG9jYXRpb24ud2Vic2l0ZQ%3D%3D',
             'https://www.roundrockmoderndentistry.com'),
        ]
        for inp, expected in cases:
            with self.subTest(inp=inp[:40]):
                self.assertEqual(normalize_url(inp), expected)

    def test_strip_gmaps_internal(self):
        cases = [
            ('https://www.google.com/maps/place/X/data=!4m7?authuser=0&hl=en&rclk=1',
             'https://www.google.com/maps/place/X/data=!4m7'),
        ]
        for inp, expected in cases:
            with self.subTest(inp=inp):
                self.assertEqual(normalize_url(inp), expected)

    def test_strip_ad_click_ids(self):
        cases = [
            ('https://example.com/?gclid=abc123', 'https://example.com'),
            ('https://example.com/?fbclid=xyz', 'https://example.com'),
            ('https://example.com/?msclkid=q&page=1', 'https://example.com?page=1'),
        ]
        for inp, expected in cases:
            with self.subTest(inp=inp):
                self.assertEqual(normalize_url(inp), expected)

    def test_lowercase_host(self):
        self.assertEqual(
            normalize_url('https://WWW.Example.COM/About'),
            'https://www.example.com/About',
        )

    def test_keep_real_query_params(self):
        cases = [
            ('https://example.com/search?q=dentist',
             'https://example.com/search?q=dentist'),
            ('https://example.com/post?id=42&utm_source=email',
             'https://example.com/post?id=42'),
        ]
        for inp, expected in cases:
            with self.subTest(inp=inp):
                self.assertEqual(normalize_url(inp), expected)

    def test_preserve_fragment(self):
        self.assertEqual(
            normalize_url('https://example.com/page?utm_source=google#section'),
            'https://example.com/page#section',
        )

    def test_empty_and_none(self):
        for inp in [None, '', '   ']:
            with self.subTest(inp=repr(inp)):
                self.assertIsNone(normalize_url(inp))

    def test_invalid_url(self):
        # Non-URL strings pass through (defensive)
        self.assertEqual(normalize_url('not-a-url'), 'not-a-url')
        self.assertEqual(normalize_url('javascript:void(0)'), 'javascript:void(0)')


if __name__ == '__main__':
    unittest.main(verbosity=2)
