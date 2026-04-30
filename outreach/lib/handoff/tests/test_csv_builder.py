"""Tests for csv_builder URL normalization wiring + pain-quote selection."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.handoff.csv_builder import (
    apply_url_normalization,
    HANDOFF_URL_FIELDS,
    top_pain_with_quotes,
)


PAIN_WEIGHTS = {
    'high_value_pain':   5,
    'medium_value_pain': 3,
    'low_value_pain':    1,
}


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


class TestTopPainWithQuotes(unittest.TestCase):
    def test_picks_highest_weight_x_count_category_as_top(self):
        # high_value_pain: weight 5 × 1 hit = 5
        # medium_value_pain: weight 3 × 2 hits = 6  ← wins
        lead = {
            'pain_hits': {
                'high_value_pain': [{'snippet': 'one big complaint', 'rating': 1, 'reviewer': 'A'}],
                'medium_value_pain': [
                    {'snippet': 'first medium complaint', 'rating': 2, 'reviewer': 'B'},
                    {'snippet': 'second medium complaint', 'rating': 2, 'reviewer': 'C'},
                ],
            },
        }
        top, quotes = top_pain_with_quotes(lead, pain_weights=PAIN_WEIGHTS, n_quotes=2)
        self.assertEqual(top, 'medium_value_pain')
        self.assertEqual([q['snippet'] for q in quotes],
                         ['first medium complaint', 'second medium complaint'])

    def test_returns_at_most_n_quotes_dedupd_by_snippet(self):
        lead = {
            'pain_hits': {
                'high_value_pain': [
                    {'snippet': 'alpha', 'rating': 1, 'reviewer': 'A'},
                    {'snippet': 'alpha', 'rating': 1, 'reviewer': 'B'},  # dup snippet
                    {'snippet': 'beta',  'rating': 2, 'reviewer': 'C'},
                    {'snippet': 'gamma', 'rating': 2, 'reviewer': 'D'},  # exceeds n_quotes
                ],
            },
        }
        top, quotes = top_pain_with_quotes(lead, pain_weights=PAIN_WEIGHTS, n_quotes=2)
        self.assertEqual(top, 'high_value_pain')
        self.assertEqual([q['snippet'] for q in quotes], ['alpha', 'beta'])

    def test_no_pain_hits_returns_none_and_empty(self):
        self.assertEqual(
            top_pain_with_quotes({'pain_hits': {}}, pain_weights=PAIN_WEIGHTS),
            (None, []),
        )
        self.assertEqual(
            top_pain_with_quotes({}, pain_weights=PAIN_WEIGHTS),
            (None, []),
        )

    def test_unknown_category_defaults_to_weight_one(self):
        # Unknown category gets default weight 1; known low_value_pain also has
        # weight 1. With equal weights × equal hits, tie-break is by sort order.
        lead = {
            'pain_hits': {
                'unknown_category': [{'snippet': 'x', 'rating': 1, 'reviewer': 'A'}],
                'low_value_pain':   [{'snippet': 'y', 'rating': 1, 'reviewer': 'B'}],
            },
        }
        top, _ = top_pain_with_quotes(lead, pain_weights=PAIN_WEIGHTS, n_quotes=1)
        self.assertIn(top, {'unknown_category', 'low_value_pain'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
