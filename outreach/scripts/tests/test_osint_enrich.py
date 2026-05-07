"""Tests for scripts.osint_enrich."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.osint_enrich import detect_gaps


FIELDS_DESIRED = [
    'linkedin_url_company', 'linkedin_url_poc', 'social_urls',
    'poc_name', 'poc_email', 'poc_role', 'news_mentions',
]


class TestDetectGaps(unittest.TestCase):
    def test_empty_lead_has_all_fields_as_gaps(self):
        lead = {'place_id': 'A', 'business_name': 'X', 'website': 'https://x.com/', 'city': 'Phoenix'}
        gaps = detect_gaps(lead, FIELDS_DESIRED)
        self.assertEqual(set(gaps), set(FIELDS_DESIRED))

    def test_lead_with_some_fields_filled_only_gaps_remain(self):
        lead = {
            'place_id': 'A',
            'linkedin_url_company': 'https://linkedin.com/company/x',
            'poc_name': 'Dr. John Smith',
        }
        gaps = detect_gaps(lead, FIELDS_DESIRED)
        self.assertNotIn('linkedin_url_company', gaps)
        self.assertNotIn('poc_name', gaps)
        self.assertIn('linkedin_url_poc', gaps)
        self.assertIn('poc_email', gaps)

    def test_empty_string_and_empty_list_are_gaps(self):
        lead = {
            'place_id': 'A',
            'linkedin_url_poc': '',
            'social_urls': [],
        }
        gaps = detect_gaps(lead, FIELDS_DESIRED)
        self.assertIn('linkedin_url_poc', gaps)
        self.assertIn('social_urls', gaps)


if __name__ == '__main__':
    unittest.main()
