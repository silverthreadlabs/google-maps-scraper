"""Tests for scripts.merge_osint_into_master."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.merge_osint_into_master import graft


CANDIDATE_HIGH = {
    'value': 'https://linkedin.com/in/john-smith-phoenix-dds',
    'source': 'serp_google',
    'query': 'site:linkedin.com/in "Dr. John Smith" "Phoenix" dental',
    'snippet': 'Dr. John Smith — Owner at Smith Family Dental',
    'judge_verdict': 'match',
    'judge_confidence': 0.95,
    'judge_reasoning': 'snippet directly names lead\'s business and city',
}


class TestGraftConfidentHits(unittest.TestCase):
    def test_grafts_above_threshold_with_provenance(self):
        master = [{'place_id': 'A'}]
        sidecar = [{
            'place_id': 'A',
            'enriched_at': '2026-05-07T15:00:00Z',
            'fields': {
                'linkedin_url_poc': {
                    'candidates': [CANDIDATE_HIGH],
                    'selected_index': 0,
                    'selected_confidence': 0.95,
                },
            },
        }]
        stats = graft(master, sidecar, threshold=0.85)
        lead = master[0]
        self.assertEqual(lead['linkedin_url_poc'], CANDIDATE_HIGH['value'])
        self.assertEqual(lead['linkedin_url_poc_source'], 'osint_serp_google')
        self.assertEqual(lead['linkedin_url_poc_confidence'], 0.95)
        self.assertEqual(lead['linkedin_url_poc_query'], CANDIDATE_HIGH['query'])
        self.assertEqual(lead['linkedin_url_poc_judge_reasoning'], CANDIDATE_HIGH['judge_reasoning'])
        self.assertEqual(stats['grafted'], 1)


if __name__ == '__main__':
    unittest.main()
