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


class TestEnrichLeadTwoWave(unittest.TestCase):
    def test_serp_wave_uses_poc_name_discovered_in_wave1(self):
        from unittest.mock import patch, MagicMock
        from scripts.osint_enrich import enrich_lead

        whois_result = {'registrant_name': None, 'registrant_email': None, 'registrant_org': None, 'status': 'redacted'}
        deep_result = {'persons': [{'name': 'Dr. John Smith', 'role': 'Owner', 'email': None,
                                    'source': 'deep_site_crawl_jsonld'}],
                       'pages_attempted': 3, 'pages_with_data': 1}

        captured_serp_queries = []
        def fake_serp(query, **kw):
            captured_serp_queries.append(query)
            return {'engine': 'ddg', 'query': query, 'results': [], 'status': 'ok'}

        cfg = MagicMock(
            OSINT_SOURCES=['whois', 'deep_site_crawl', 'serp'],
            OSINT_FIELDS_DESIRED=['linkedin_url_poc', 'poc_name'],
            OSINT_SERP_QUERIES={
                'linkedin_url_poc': 'site:linkedin.com/in "{poc_name}" "{city}" dental',
            },
            OSINT_DEEP_CRAWL_PATHS=['/about'],
            OSINT_INDUSTRY_TERMS=['dentist'],
        )
        lead = {'place_id': 'A', 'business_name': 'Smith Family Dental',
                'website': 'https://smithfamilydental.com', 'city': 'Phoenix', 'domain': 'smithfamilydental.com'}

        with patch('scripts.osint_enrich.lookup_domain', return_value=whois_result), \
             patch('scripts.osint_enrich.crawl_domain', return_value=deep_result), \
             patch('scripts.osint_enrich.run_serp_query_with_fallback', side_effect=fake_serp):
            record = enrich_lead(lead, cfg, already_crawled=set())

        joined = '\n'.join(captured_serp_queries)
        self.assertIn('Dr. John Smith', joined)
        self.assertIn('Phoenix', joined)
        poc_candidates = record['fields']['poc_name']['candidates']
        self.assertEqual(len(poc_candidates), 1)
        self.assertEqual(poc_candidates[0]['value'], 'Dr. John Smith')
        self.assertEqual(poc_candidates[0]['source'], 'deep_site_crawl_jsonld')


class TestSidecarResumability(unittest.TestCase):
    def test_load_existing_sidecar_returns_processed_place_ids(self):
        import json
        import tempfile
        from scripts.osint_enrich import load_processed_place_ids

        with tempfile.NamedTemporaryFile(suffix='.json', mode='w', delete=False) as f:
            json.dump([
                {'place_id': 'A', 'fields': {}},
                {'place_id': 'B', 'fields': {}},
            ], f)
            p = Path(f.name)
        try:
            ids = load_processed_place_ids(p)
            self.assertEqual(ids, {'A', 'B'})
        finally:
            p.unlink()

    def test_load_processed_returns_empty_set_when_file_missing(self):
        from scripts.osint_enrich import load_processed_place_ids
        ids = load_processed_place_ids(Path('/nonexistent/path.json'))
        self.assertEqual(ids, set())

    def test_append_record_writes_atomically(self):
        import json
        import tempfile
        from scripts.osint_enrich import append_sidecar_record

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'osint.json'
            append_sidecar_record(p, {'place_id': 'A', 'fields': {}})
            append_sidecar_record(p, {'place_id': 'B', 'fields': {}})
            data = json.loads(p.read_text())
            self.assertEqual([r['place_id'] for r in data], ['A', 'B'])


if __name__ == '__main__':
    unittest.main()
