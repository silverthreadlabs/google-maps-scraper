"""Tests for csv_builder URL normalization wiring."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.handoff.csv_builder import apply_url_normalization, HANDOFF_URL_FIELDS


class TestApplyUrlNormalization(unittest.TestCase):
    def test_strips_tracking_params_from_website_and_records_raw(self):
        raw = 'https://www.example.com/?utm_source=google&sc_cid=GBP%3AO'
        row = {'website': raw}
        apply_url_normalization(row, HANDOFF_URL_FIELDS)
        self.assertEqual(row['website'], 'https://www.example.com')
        self.assertEqual(row['website_raw'], raw)

    def test_unchanged_url_leaves_audit_column_empty(self):
        row = {'website': 'https://www.example.com'}
        apply_url_normalization(row, HANDOFF_URL_FIELDS)
        self.assertEqual(row['website'], 'https://www.example.com')
        self.assertEqual(row.get('website_raw', ''), '')

    def test_strips_gmaps_internal_params(self):
        raw = 'https://www.google.com/maps/place/X?hl=en&authuser=0&rclk=1'
        row = {'google_maps_link': raw}
        apply_url_normalization(row, HANDOFF_URL_FIELDS)
        self.assertEqual(row['google_maps_link'], 'https://www.google.com/maps/place/X')
        self.assertEqual(row['google_maps_link_raw'], raw)

    def test_strips_redirect_target_tracking(self):
        raw = 'https://corp.example.com/loc?utm_campaign=spring'
        row = {'website_redirect_target': raw}
        apply_url_normalization(row, HANDOFF_URL_FIELDS)
        self.assertEqual(row['website_redirect_target'], 'https://corp.example.com/loc')
        self.assertEqual(row['website_redirect_target_raw'], raw)

    def test_none_field_value_becomes_empty_string_no_audit(self):
        row = {'website': None, 'google_maps_link': '', 'website_redirect_target': None}
        apply_url_normalization(row, HANDOFF_URL_FIELDS)
        self.assertEqual(row['website'], '')
        self.assertEqual(row['google_maps_link'], '')
        self.assertEqual(row['website_redirect_target'], '')
        self.assertEqual(row.get('website_raw', ''), '')
        self.assertEqual(row.get('google_maps_link_raw', ''), '')
        self.assertEqual(row.get('website_redirect_target_raw', ''), '')

    def test_invalid_url_passes_through_unchanged_and_no_audit(self):
        row = {'website': 'not-a-url'}
        apply_url_normalization(row, HANDOFF_URL_FIELDS)
        self.assertEqual(row['website'], 'not-a-url')
        self.assertEqual(row.get('website_raw', ''), '')

    def test_handoff_url_fields_covers_three_url_columns(self):
        # The constant must enumerate exactly the three URL columns sales clicks on.
        self.assertEqual(
            {field for field, _ in HANDOFF_URL_FIELDS},
            {'website', 'google_maps_link', 'website_redirect_target'},
        )
        # And each entry pairs a field with its '<field>_raw' audit column.
        for field, audit in HANDOFF_URL_FIELDS:
            self.assertEqual(audit, f'{field}_raw')


if __name__ == '__main__':
    unittest.main(verbosity=2)
