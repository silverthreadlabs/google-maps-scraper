"""Tests for scripts/merge_crawl_into_master."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.merge_crawl_into_master import (
    CRAWLED_EMAIL_SOURCE,
    POCS_SOURCE,
    graft,
    index_crawl_by_hostname,
)


CRAWL_OK = {
    'website':            'https://acme.example/',
    'emails':             ['info@acme.example'],
    'socials':            ['https://www.facebook.com/acme'],
    'pocs':               [{'name': 'Jane Doe', 'role': 'Owner'}],
    'pages':              [{'url': 'https://acme.example/', 'title': 'Acme'}],
    'status':             'ok',
    'cloudflare_blocked': False,
}


class TestIndexCrawlByHostname(unittest.TestCase):
    def test_indexes_one_row_per_hostname(self):
        rows = [CRAWL_OK, {**CRAWL_OK, 'website': 'https://other.example/'}]
        idx = index_crawl_by_hostname(rows)
        self.assertEqual(set(idx.keys()), {'acme.example', 'other.example'})

    def test_prefers_ok_over_error_when_hostname_collides(self):
        # If the same hostname appears with status=ok and status=error,
        # the ok row wins so downstream consumers see useful data.
        err_row = {**CRAWL_OK, 'status': 'open_error', 'emails': []}
        idx = index_crawl_by_hostname([err_row, CRAWL_OK])
        self.assertEqual(idx['acme.example']['status'], 'ok')

    def test_skips_rows_with_no_resolvable_hostname(self):
        rows = [{**CRAWL_OK, 'website': ''}]
        self.assertEqual(index_crawl_by_hostname(rows), {})


class TestGraft(unittest.TestCase):
    def test_match_attaches_crawl_fields_with_provenance(self):
        master = [{'place_id': 'p1', 'website': 'https://acme.example/foo?utm=x'}]
        idx = index_crawl_by_hostname([CRAWL_OK])
        stats = graft(master, idx, now_iso='2026-05-01T00:00:00+00:00')

        l = master[0]
        self.assertEqual(l['crawled_emails'], ['info@acme.example'])
        self.assertEqual(l['crawled_emails_source'], [CRAWLED_EMAIL_SOURCE])
        self.assertEqual(l['crawled_emails_added_at'], '2026-05-01T00:00:00+00:00')
        self.assertEqual(l['crawled_socials'], ['https://www.facebook.com/acme'])
        self.assertEqual(l['pocs'][0]['name'], 'Jane Doe')
        self.assertEqual(l['pocs_source'], POCS_SOURCE)
        self.assertEqual(l['crawl_status'], 'ok')
        self.assertEqual(l['crawl_pages_visited'][0]['title'], 'Acme')
        self.assertTrue(l['crawl_attempted'])
        self.assertNotIn('cloudflare_blocked', l)
        self.assertEqual(stats, {
            'master_leads': 1, 'matched': 1, 'unmatched': 0, 'unique_hosts': 1,
        })

    def test_shared_hostname_attaches_same_payload_to_each_lead(self):
        # Two listings with the same hostname (e.g. clinic + eponymous doctor
        # listing) both get the same crawl payload — single fetch, multi-row
        # benefit. Mirrors the queue's hostname-dedup contract.
        master = [
            {'place_id': 'p1', 'website': 'https://acme.example/'},
            {'place_id': 'p2', 'website': 'https://acme.example/team'},
        ]
        idx = index_crawl_by_hostname([CRAWL_OK])
        graft(master, idx, now_iso='2026-05-01T00:00:00+00:00')
        for l in master:
            self.assertEqual(l['crawled_emails'], ['info@acme.example'])

    def test_unmatched_lead_marked_crawl_attempted_false(self):
        # A lead whose hostname has no crawl row gets crawl_attempted=False
        # so consumers can distinguish never-crawled from crawled-empty.
        master = [{'place_id': 'p1', 'website': 'https://novomad.example/'}]
        graft(master, {}, now_iso='2026-05-01T00:00:00+00:00')
        self.assertEqual(master[0].get('crawl_attempted'), False)
        self.assertNotIn('crawled_emails', master[0])

    def test_cloudflare_blocked_propagates_only_when_true(self):
        master = [{'place_id': 'p1', 'website': 'https://acme.example/'}]
        cf_row = {**CRAWL_OK, 'cloudflare_blocked': True, 'status': 'cloudflare_blocked'}
        idx = index_crawl_by_hostname([cf_row])
        graft(master, idx, now_iso='2026-05-01T00:00:00+00:00')
        self.assertTrue(master[0]['cloudflare_blocked'])
        self.assertEqual(master[0]['crawl_status'], 'cloudflare_blocked')

    def test_lead_without_website_is_unmatched_not_crash(self):
        master = [{'place_id': 'p1'}]                # no website key at all
        graft(master, {'acme.example': CRAWL_OK})
        self.assertEqual(master[0]['crawl_attempted'], False)


if __name__ == '__main__':
    unittest.main(verbosity=2)
