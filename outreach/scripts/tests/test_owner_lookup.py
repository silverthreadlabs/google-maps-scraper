"""Tests for scripts/owner_lookup."""
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.owner_lookup import (
    OWNER_SOURCE,
    apply_sidecar,
    print_queue,
    select_queue,
)


def _lead(**kw):
    base = {
        'place_id': 'p1', 'title': 'Acme', 'tier': 'A', 'quality_score': 50.0,
        'metro': 'dallas', 'website': 'https://acme.example', 'owner_name': '',
    }
    base.update(kw)
    return base


class TestSelectQueue(unittest.TestCase):
    def test_filters_by_tier_and_skips_existing_owner(self):
        master = [
            _lead(place_id='p1', tier='A', owner_name='Already Set'),  # skip
            _lead(place_id='p2', tier='A', quality_score=80),
            _lead(place_id='p3', tier='B', quality_score=40),
            _lead(place_id='p4', tier='C', quality_score=20),          # tier filter
            _lead(place_id='p5', tier='A', quality_score=30, owner_name='   '),  # whitespace = empty
        ]
        q = select_queue(master, tiers={'A', 'B'})
        self.assertEqual([l['place_id'] for l in q], ['p2', 'p3', 'p5'])

    def test_sorts_by_quality_score_descending(self):
        master = [
            _lead(place_id='p1', quality_score=10),
            _lead(place_id='p2', quality_score=99),
            _lead(place_id='p3', quality_score=50),
        ]
        q = select_queue(master, tiers={'A', 'B'})
        self.assertEqual([l['place_id'] for l in q], ['p2', 'p3', 'p1'])

    def test_limit_caps_at_top_n(self):
        master = [_lead(place_id=f'p{i}', quality_score=100 - i) for i in range(5)]
        q = select_queue(master, tiers={'A', 'B'}, limit=2)
        self.assertEqual(len(q), 2)
        self.assertEqual(q[0]['place_id'], 'p0')


class TestPrintQueue(unittest.TestCase):
    def test_emits_search_query_with_title_and_metro(self):
        buf = io.StringIO()
        print_queue([_lead(title='John Burns MD', metro='dallas')], file=buf)
        output = buf.getvalue()
        self.assertIn('John Burns MD', output)
        self.assertIn('dallas', output)
        self.assertIn('place_id=p1', output)
        self.assertIn('linkedin', output)


class TestApplySidecar(unittest.TestCase):
    def test_patches_lead_with_owner_fields_and_provenance(self):
        master = [_lead(place_id='p1')]
        sidecar = {
            'p1': {'name': 'Jane Doe', 'title': 'Founder',
                   'linkedin': 'https://linkedin.com/in/jane'},
        }
        stats = apply_sidecar(master, sidecar, now_iso='2026-05-01T00:00:00+00:00')
        self.assertEqual(master[0]['owner_name'], 'Jane Doe')
        self.assertEqual(master[0]['owner_title'], 'Founder')
        self.assertEqual(master[0]['owner_linkedin'], 'https://linkedin.com/in/jane')
        self.assertEqual(master[0]['owner_source'], OWNER_SOURCE)
        self.assertEqual(master[0]['owner_added_at'], '2026-05-01T00:00:00+00:00')
        self.assertEqual(stats['patched'], 1)
        self.assertEqual(stats['skipped_set'], 0)
        self.assertEqual(stats['orphan'], 0)

    def test_idempotent_skip_when_owner_already_set(self):
        # Re-running --apply against a master that already carries owner data
        # must not overwrite — protects against multi-rep stomp.
        master = [_lead(place_id='p1', owner_name='Existing')]
        sidecar = {'p1': {'name': 'New Owner', 'title': 'CEO', 'linkedin': ''}}
        stats = apply_sidecar(master, sidecar)
        self.assertEqual(master[0]['owner_name'], 'Existing')
        self.assertEqual(stats['patched'], 0)
        self.assertEqual(stats['skipped_set'], 1)

    def test_orphan_place_ids_reported_not_silently_dropped(self):
        master = [_lead(place_id='p1')]
        sidecar = {
            'p1': {'name': 'Real', 'title': '', 'linkedin': ''},
            'p_orphan': {'name': 'Other', 'title': '', 'linkedin': ''},
        }
        stats = apply_sidecar(master, sidecar)
        self.assertEqual(stats['patched'], 1)
        self.assertEqual(stats['orphan'], 1)
        self.assertEqual(stats['orphan_pids'], ['p_orphan'])

    def test_missing_optional_fields_become_empty_strings(self):
        master = [_lead(place_id='p1')]
        sidecar = {'p1': {'name': 'Jane Doe'}}   # title + linkedin missing
        apply_sidecar(master, sidecar)
        self.assertEqual(master[0]['owner_name'], 'Jane Doe')
        self.assertEqual(master[0]['owner_title'], '')
        self.assertEqual(master[0]['owner_linkedin'], '')


if __name__ == '__main__':
    unittest.main(verbosity=2)
