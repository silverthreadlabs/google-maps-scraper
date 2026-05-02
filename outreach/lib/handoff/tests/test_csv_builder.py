"""Tests for csv_builder URL normalization wiring + pain-quote selection."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.handoff.csv_builder import (
    apply_url_normalization,
    HANDOFF_URL_FIELDS,
    FIELDNAMES,
    top_pain_with_quotes,
    _build_row,
)


class TestCsvColumns(unittest.TestCase):
    def test_phone_normalized_column_dropped(self):
        # The phone_normalized column was never used by sales — only `phone`
        # is consumed downstream. Keeping it as an empty column just inflates
        # the CSV and confuses reviewers.
        self.assertNotIn('phone_normalized', FIELDNAMES)

    def test_build_row_does_not_emit_phone_normalized_key(self):
        row = _build_row(
            {'phone': '+1 214-272-8533', 'phone_normalized': '+12142728533'},
            service_map={},
            pain_weights={},
        )
        self.assertEqual(row.get('phone'), '+1 214-272-8533')
        self.assertNotIn('phone_normalized', row)


class TestAllEmailsExcludesInvalid(unittest.TestCase):
    # `best_email` already filters via `trustworthy_emails`; `all_emails` and
    # `email_sources` historically didn't, so flagged junk (e.g. image
    # filenames `*_1440x640@2x.png` ingested from the gosom scraper that
    # `validate_email` already marked `image_artifact`) leaked into the CSV.
    # The CSV is what sales sees — invalid hits should not surface there.

    def _row(self, lead):
        return _build_row(lead, service_map={}, pain_weights={})

    def test_all_emails_skips_items_in_emails_invalid(self):
        lead = {
            'emails': ['real@example.com', 'foo@2x.png', 'bar@3x.jpg'],
            'crawled_emails': [],
            'emails_invalid': [
                {'email': 'foo@2x.png', 'reason': 'image_artifact'},
                {'email': 'bar@3x.jpg', 'reason': 'image_artifact'},
            ],
        }
        row = self._row(lead)
        self.assertEqual(row['all_emails'], 'real@example.com')

    def test_email_sources_pares_to_match_filtered_all_emails(self):
        # email_sources is positional/parallel to all_emails — 1 valid email
        # out → exactly 1 source out, not 3.
        lead = {
            'emails': ['real@example.com', 'foo@2x.png', 'bar@3x.jpg'],
            'emails_source': ['gosom_scraper', 'gosom_scraper', 'gosom_scraper'],
            'crawled_emails': [],
            'emails_invalid': [
                {'email': 'foo@2x.png', 'reason': 'image_artifact'},
                {'email': 'bar@3x.jpg', 'reason': 'image_artifact'},
            ],
        }
        row = self._row(lead)
        self.assertEqual(row['all_emails'].split(';'), ['real@example.com'])
        self.assertEqual(row['email_sources'].split(';'), ['gosom_scraper'])

    def test_all_emails_case_insensitive_match_against_invalid(self):
        # emails_invalid stores the email as captured; comparison must be
        # case-insensitive so capitalization variants don't slip through.
        lead = {
            'emails': ['Foo@2x.png'],
            'emails_invalid': [{'email': 'foo@2x.png', 'reason': 'image_artifact'}],
        }
        row = self._row(lead)
        self.assertEqual(row['all_emails'], '')


class TestPainQuotesNotTruncated(unittest.TestCase):
    def test_pain_quote_passes_through_full_snippet(self):
        # The CSV must ship the full review text — no [:N] truncation in
        # csv_builder. (Truncation upstream in classify is a separate fix.)
        long_snippet = 'A' * 1500 + ' end-marker'
        lead = {
            'agent_pain_hits': {
                'calls_unanswered': [
                    {'snippet': long_snippet, 'rating': 1, 'reviewer': 'X'}
                ]
            }
        }
        _, quotes = top_pain_with_quotes(
            lead, pain_weights={'calls_unanswered': 5}, n_quotes=1,
        )
        self.assertEqual(quotes[0]['snippet'], long_snippet)
        self.assertTrue(quotes[0]['snippet'].endswith('end-marker'))


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

    def test_agent_pain_hits_takes_precedence_over_legacy_pain_hits(self):
        # Same lead carrying both fields. agent_pain_hits is the post-subagent
        # classification (STL hierarchy main names); pain_hits is legacy
        # SBERT output (flat category names). Handoff must read the agent
        # field — otherwise legacy classifications silently win.
        lead = {
            'agent_pain_hits': {
                'high_value_pain': [{'snippet': 'agent quote', 'rating': 1, 'reviewer': 'A'}],
            },
            'pain_hits': {
                'low_value_pain': [{'snippet': 'legacy quote', 'rating': 2, 'reviewer': 'B'}],
            },
        }
        top, quotes = top_pain_with_quotes(lead, pain_weights=PAIN_WEIGHTS, n_quotes=1)
        self.assertEqual(top, 'high_value_pain')
        self.assertEqual([q['snippet'] for q in quotes], ['agent quote'])

    def test_falls_back_to_pain_hits_when_agent_field_absent(self):
        lead = {
            'pain_hits': {
                'medium_value_pain': [{'snippet': 'legacy only', 'rating': 1, 'reviewer': 'A'}],
            },
        }
        top, quotes = top_pain_with_quotes(lead, pain_weights=PAIN_WEIGHTS, n_quotes=1)
        self.assertEqual(top, 'medium_value_pain')
        self.assertEqual([q['snippet'] for q in quotes], ['legacy only'])

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
