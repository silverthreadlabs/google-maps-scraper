"""Tests for scripts.osint_enrich."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from lib.cli.osint_enrich import detect_gaps


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
        from lib.cli.osint_enrich import enrich_lead

        whois_result = {'registrant_name': None, 'registrant_email': None, 'registrant_org': None, 'status': 'redacted'}
        deep_result = {'persons': [{'name': 'Dr. John Smith', 'role': 'Owner', 'email': None,
                                    'source': 'deep_site_crawl_jsonld'}],
                       'pages_attempted': 3, 'pages_with_data': 1}

        captured_serp_queries = []
        def fake_serp(query, **kw):
            captured_serp_queries.append(query)
            return {'engine': 'ddg', 'query': query, 'results': [], 'status': 'ok'}

        cfg = MagicMock(
            osint_sources=['whois', 'deep_site_crawl', 'serp'],
            osint_fields_desired=['linkedin_url_poc', 'poc_name'],
            osint_serp_queries={
                'linkedin_url_poc': 'site:linkedin.com/in "{poc_name}" "{city}" dental',
            },
            osint_deep_crawl_paths=['/about'],
            osint_industry_terms=['dentist'],
        )
        lead = {'place_id': 'A', 'business_name': 'Smith Family Dental',
                'website': 'https://smithfamilydental.com', 'city': 'Phoenix', 'domain': 'smithfamilydental.com'}

        with patch('lib.cli.osint_enrich.lookup_domain', return_value=whois_result), \
             patch('lib.cli.osint_enrich.crawl_domain', return_value=deep_result), \
             patch('lib.cli.osint_enrich.run_serp_query_with_fallback', side_effect=fake_serp):
            record = enrich_lead(lead, cfg, already_crawled=set())

        joined = '\n'.join(captured_serp_queries)
        self.assertIn('Dr. John Smith', joined)
        self.assertIn('Phoenix', joined)
        poc_candidates = record['fields']['poc_name']['candidates']
        self.assertEqual(len(poc_candidates), 1)
        self.assertEqual(poc_candidates[0]['value'], 'Dr. John Smith')
        self.assertEqual(poc_candidates[0]['source'], 'deep_site_crawl_jsonld')


class TestEnrichLeadProductionSchema(unittest.TestCase):
    """Regression for the schema-drift bug: real master leads carry
    title / metro / address / owner_name — NOT business_name / city /
    poc_name (0/326 on real data). The SERP wave must still fire with a
    well-formed query; previously every query was malformed or skipped."""

    def _run(self, lead):
        from unittest.mock import patch, MagicMock
        from lib.cli.osint_enrich import enrich_lead
        captured = []

        def fake_serp(query, **kw):
            captured.append(query)
            return {'engine': 'ddg', 'query': query, 'results': [], 'status': 'ok'}

        cfg = MagicMock(
            osint_sources=['serp'],
            osint_fields_desired=['linkedin_url_poc', 'linkedin_url_company', 'social_urls'],
            osint_serp_queries={
                'linkedin_url_poc': 'site:linkedin.com/in "{poc_name}" "{city}" auto',
                'linkedin_url_company': 'site:linkedin.com/company "{business_name}" "{city}"',
                'social_urls': '"{business_name}" "{city}" instagram OR facebook',
            },
            osint_deep_crawl_paths=[],
            osint_industry_terms=['auto repair'],
        )
        with patch('lib.cli.osint_enrich.run_serp_query_with_fallback', side_effect=fake_serp):
            record = enrich_lead(lead, cfg, already_crawled=set())
        return record, captured

    def test_owner_name_drives_poc_query_and_is_not_skipped(self):
        lead = {'place_id': 'A', 'title': 'Bonnie & Clyde Car Stereo',
                'address': '11311 Harry Hines Blvd #104, Dallas, TX 75229, United States',
                'metro': 'dallas', 'owner_name': 'Mazin Awad'}
        record, captured = self._run(lead)
        joined = '\n'.join(captured)
        self.assertEqual(len(captured), 3)            # all three queries fired
        self.assertIn('Mazin Awad', joined)           # owner_name → {poc_name}
        self.assertIn('Bonnie & Clyde Car Stereo', joined)  # title → {business_name}
        self.assertIn('Dallas', joined)               # address → {city}
        # the POC query fired (not skipped for a missing name); 'no_results'
        # here is only because the stubbed SERP returns nothing.
        self.assertNotEqual(record['fields']['linkedin_url_poc']['skipped_reason'],
                            'no_poc_name_known')

    def test_record_carries_resolved_binder_context(self):
        # The osint-binder needs lead context (business_name/city/poc_name_known)
        # to apply its >=2-signal rule. The sidecar record must carry it, built
        # from the resolvers — not the phantom keys.
        lead = {'place_id': 'A', 'title': 'Bonnie & Clyde Car Stereo',
                'address': '11311 Harry Hines Blvd #104, Dallas, TX 75229, United States',
                'metro': 'dallas', 'owner_name': 'Mazin Awad', 'phone': '+1-214-555-0001'}
        record, _ = self._run(lead)
        ctx = record['lead']
        self.assertEqual(ctx['business_name'], 'Bonnie & Clyde Car Stereo')
        self.assertEqual(ctx['city'], 'Dallas')
        self.assertEqual(ctx['poc_name_known'], 'Mazin Awad')
        self.assertEqual(ctx['phone'], '+1-214-555-0001')

    def test_no_name_still_fires_wellformed_company_and_social(self):
        lead = {'place_id': 'B', 'title': 'Buckner Car Audio',
                'address': '2952 Buckner Blvd, Dallas, TX 75227, United States',
                'metro': 'dallas'}
        record, captured = self._run(lead)
        self.assertEqual(record['fields']['linkedin_url_poc']['skipped_reason'],
                         'no_poc_name_known')         # correctly skipped — no name
        self.assertEqual(len(captured), 2)            # company + social still fired
        for q in captured:
            self.assertIn('Buckner Car Audio', q)     # never an empty-anchor query
            self.assertNotIn('""', q)


class TestSelectOsintLeads(unittest.TestCase):
    """Incremental scoping so a feasibility run is minutes, not a 4–5 hr pass
    over the whole master (the reason OSINT was being skipped)."""

    def _leads(self):
        return [
            {'place_id': 'A', 'tier': 'A', 'quality_score': 10},
            {'place_id': 'B', 'tier': 'C', 'quality_score': 99},
            {'place_id': 'C', 'tier': 'B', 'quality_score': 50},
            {'place_id': 'D', 'tier': 'D', 'quality_score': 5},
        ]

    def test_default_keeps_all_in_input_order(self):
        from lib.cli.osint_enrich import select_osint_leads
        out = select_osint_leads(self._leads())
        self.assertEqual([l['place_id'] for l in out], ['A', 'B', 'C', 'D'])

    def test_tier_filter_and_sorts_by_quality_desc(self):
        from lib.cli.osint_enrich import select_osint_leads
        out = select_osint_leads(self._leads(), tiers=['A', 'B'])
        self.assertEqual([l['place_id'] for l in out], ['C', 'A'])  # qs 50 then 10

    def test_limit_takes_top_n_by_quality(self):
        from lib.cli.osint_enrich import select_osint_leads
        out = select_osint_leads(self._leads(), limit=2)
        self.assertEqual([l['place_id'] for l in out], ['B', 'C'])  # qs 99, 50

    def test_tiers_and_limit_compose(self):
        from lib.cli.osint_enrich import select_osint_leads
        out = select_osint_leads(self._leads(), tiers=['A', 'B', 'C'], limit=1)
        self.assertEqual([l['place_id'] for l in out], ['B'])  # highest qs in A/B/C


class TestSidecarResumability(unittest.TestCase):
    def test_load_existing_sidecar_returns_processed_place_ids(self):
        import json
        import tempfile
        from lib.cli.osint_enrich import load_processed_place_ids

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
        from lib.cli.osint_enrich import load_processed_place_ids
        ids = load_processed_place_ids(Path('/nonexistent/path.json'))
        self.assertEqual(ids, set())

    def test_append_record_writes_atomically(self):
        import json
        import tempfile
        from lib.cli.osint_enrich import append_sidecar_record

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'osint.json'
            append_sidecar_record(p, {'place_id': 'A', 'fields': {}})
            append_sidecar_record(p, {'place_id': 'B', 'fields': {}})
            data = json.loads(p.read_text())
            self.assertEqual([r['place_id'] for r in data], ['A', 'B'])


class TestApplyJudgments(unittest.TestCase):
    def test_merges_judgments_into_sidecar_by_place_id_and_field(self):
        from lib.cli.osint_enrich import apply_judgments_to_sidecar
        sidecar = [{
            'place_id': 'A',
            'fields': {
                'linkedin_url_poc': {
                    'candidates': [
                        {'value': 'u1', 'judge_verdict': None, 'judge_confidence': None},
                        {'value': 'u2', 'judge_verdict': None, 'judge_confidence': None},
                    ],
                    'selected_index': None,
                    'selected_confidence': None,
                },
            },
        }]
        judgments = [{
            'place_id': 'A',
            'field': 'linkedin_url_poc',
            'judgments': [
                {'index': 0, 'verdict': 'match', 'confidence': 0.92, 'reasoning': 'r0'},
                {'index': 1, 'verdict': 'rejected', 'confidence': 0.0, 'reasoning': 'r1'},
            ],
            'best_match_index': 0,
            'selected_confidence': 0.92,
        }]
        apply_judgments_to_sidecar(sidecar, judgments)
        f = sidecar[0]['fields']['linkedin_url_poc']
        self.assertEqual(f['selected_index'], 0)
        self.assertEqual(f['selected_confidence'], 0.92)
        self.assertEqual(f['candidates'][0]['judge_verdict'], 'match')
        self.assertEqual(f['candidates'][0]['judge_confidence'], 0.92)
        self.assertEqual(f['candidates'][1]['judge_verdict'], 'rejected')


if __name__ == '__main__':
    unittest.main()
