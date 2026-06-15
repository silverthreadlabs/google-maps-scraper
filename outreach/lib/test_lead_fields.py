"""Tests for lead_fields — canonical resolution of the real master schema.

Regression guard for the schema-drift bug: the OSINT SERP templates and the
handoff contact logic referenced `business_name`/`city`/`poc_name`, but the
gosom/master schema stores those under `title`/`metro`+`address`/
`owner_name`+`pocs[]` (the literal keys are 0/326 on real data). These tests
pin the mapping so every read-site resolves the same way.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.lead_fields import (
    resolve_business_name,
    resolve_city,
    resolve_poc_name,
)


class TestResolveBusinessName(unittest.TestCase):
    def test_prefers_explicit_business_name(self):
        self.assertEqual(
            resolve_business_name({'business_name': 'Foo Inc', 'title': 'Bar'}),
            'Foo Inc')

    def test_falls_back_to_title(self):
        self.assertEqual(resolve_business_name({'title': 'TX Transmission Repair'}),
                         'TX Transmission Repair')

    def test_empty_when_neither_present(self):
        self.assertEqual(resolve_business_name({}), '')

    def test_strips_whitespace_and_skips_blank(self):
        self.assertEqual(resolve_business_name({'business_name': '  ', 'title': ' Bonnie & Clyde '}),
                         'Bonnie & Clyde')


class TestResolveCity(unittest.TestCase):
    def test_prefers_explicit_city(self):
        self.assertEqual(resolve_city({'city': 'Phoenix', 'metro': 'dallas'}), 'Phoenix')

    def test_parses_city_from_us_address(self):
        lead = {'address': '7020 Cedar Springs Rd, Dallas, TX 75235, United States',
                'metro': 'dallas'}
        self.assertEqual(resolve_city(lead), 'Dallas')

    def test_parses_real_city_not_metro_slug(self):
        # Raul Baray's shop is in Terrell, not the Dallas metro slug.
        lead = {'address': '8723 FM 2728, Terrell, TX 75161, United States',
                'metro': 'dallas'}
        self.assertEqual(resolve_city(lead), 'Terrell')

    def test_parses_city_when_street_has_suite_comma(self):
        lead = {'address': '11311 Harry Hines Blvd #104, Dallas, TX 75229, United States'}
        self.assertEqual(resolve_city(lead), 'Dallas')

    def test_falls_back_to_humanized_metro_when_no_address(self):
        self.assertEqual(resolve_city({'metro': 'dallas'}), 'Dallas')
        self.assertEqual(resolve_city({'metro': 'san_francisco'}), 'San Francisco')

    def test_international_address_falls_back_to_second_part(self):
        # Non-US postal code won't match the strict state+ZIP rule.
        lead = {'address': '123 King St W, Toronto, ON M5H 1A1, Canada'}
        self.assertEqual(resolve_city(lead), 'Toronto')

    def test_empty_when_nothing_present(self):
        self.assertEqual(resolve_city({}), '')


class TestResolvePocName(unittest.TestCase):
    def test_prefers_explicit_poc_name(self):
        self.assertEqual(resolve_poc_name({'poc_name': 'A', 'owner_name': 'B'}), 'A')

    def test_falls_back_to_owner_name(self):
        self.assertEqual(resolve_poc_name({'owner_name': 'Mazin Awad'}), 'Mazin Awad')

    def test_falls_back_to_primary_poc(self):
        lead = {'pocs': [
            {'name': 'Tammy V', 'primary': False},
            {'name': 'Shaw', 'primary': True},
        ]}
        self.assertEqual(resolve_poc_name(lead), 'Shaw')

    def test_falls_back_to_first_named_poc_when_no_primary(self):
        lead = {'pocs': [{'name': 'Dina Maldonado'}, {'name': 'Angelo Minell'}]}
        self.assertEqual(resolve_poc_name(lead), 'Dina Maldonado')

    def test_ignores_non_dict_and_nameless_pocs(self):
        lead = {'pocs': ['junk', {}, {'name': '  '}, {'name': 'Real Person'}]}
        self.assertEqual(resolve_poc_name(lead), 'Real Person')

    def test_empty_when_no_name_anywhere(self):
        self.assertEqual(resolve_poc_name({'pocs': []}), '')
        self.assertEqual(resolve_poc_name({}), '')


if __name__ == '__main__':
    unittest.main(verbosity=2)
