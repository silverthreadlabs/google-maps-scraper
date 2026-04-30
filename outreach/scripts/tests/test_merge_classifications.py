"""Tests for scripts/merge_classifications."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.merge_classifications import merge, write_atomic, PROVENANCE_TAG, main


HIT = {
    'sub': 'missed_calls_during_business_hours',
    'confidence': 0.88,
    'snippet': 'I called five times and nobody picked up.',
    'rating': 1,
    'reviewer': 'Jane D',
    'reasoning': 'direct phone-unreachable language',
}


class TestMerge(unittest.TestCase):
    def test_attaches_hits_to_matching_lead_with_provenance(self):
        master = [{'place_id': 'p1', 'title': 'Acme'}]
        sidecar = {'p1': {'calls_unanswered': [HIT]}}
        stats = merge(master, sidecar)

        self.assertEqual(master[0]['agent_pain_hits']['calls_unanswered'][0], HIT)
        self.assertEqual(master[0]['agent_pain_hits_source'], PROVENANCE_TAG)
        self.assertRegex(master[0]['agent_pain_hits_added_at'],
                         r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$')
        self.assertEqual(stats['master_leads'], 1)
        self.assertEqual(stats['leads_with_hits'], 1)
        self.assertEqual(stats['leads_without_hits'], 0)
        self.assertEqual(stats['orphan_place_ids'], [])

    def test_lead_with_no_sidecar_entry_gets_empty_hits_and_provenance(self):
        # Per CLAUDE.md rule 1: provenance fields are added uniformly so
        # downstream consumers can tell "we ran the classifier and got nothing"
        # apart from "we never ran the classifier on this lead".
        master = [{'place_id': 'p1', 'title': 'Acme'}]
        sidecar = {}
        stats = merge(master, sidecar)

        self.assertEqual(master[0]['agent_pain_hits'], {})
        self.assertEqual(master[0]['agent_pain_hits_source'], PROVENANCE_TAG)
        self.assertIn('agent_pain_hits_added_at', master[0])
        self.assertEqual(stats['leads_with_hits'], 0)
        self.assertEqual(stats['leads_without_hits'], 1)

    def test_orphan_sidecar_place_ids_reported_sorted(self):
        master = [{'place_id': 'p1'}]
        sidecar = {
            'p_orphan_b': {'calls_unanswered': [HIT]},
            'p1':         {'calls_unanswered': [HIT]},
            'p_orphan_a': {'booking_friction':  [HIT]},
        }
        stats = merge(master, sidecar)
        self.assertEqual(stats['orphan_place_ids'], ['p_orphan_a', 'p_orphan_b'])

    def test_lead_without_place_id_gets_empty_hits_not_arbitrary_match(self):
        # A lead missing place_id mustn't accidentally match the first sidecar
        # entry — it gets empty hits and is counted as "without hits".
        master = [{'title': 'no place id'}]
        sidecar = {'p1': {'calls_unanswered': [HIT]}}
        stats = merge(master, sidecar)
        self.assertEqual(master[0]['agent_pain_hits'], {})
        self.assertEqual(stats['orphan_place_ids'], ['p1'])

    def test_existing_legacy_pain_hits_field_is_preserved(self):
        # Per CLAUDE.md rule 1: never replace field values. The legacy
        # SBERT-era pain_hits sticks around so we can audit how rankings
        # changed when we switch from legacy to agent classification.
        master = [{
            'place_id': 'p1',
            'pain_hits': {'missed_calls_unreachable': [{'snippet': 'legacy', 'rating': 2}]},
        }]
        sidecar = {'p1': {'calls_unanswered': [HIT]}}
        merge(master, sidecar)
        self.assertEqual(master[0]['pain_hits']['missed_calls_unreachable'][0]['snippet'], 'legacy')
        self.assertEqual(master[0]['agent_pain_hits']['calls_unanswered'][0]['snippet'], HIT['snippet'])

    def test_multi_main_per_lead(self):
        master = [{'place_id': 'p1'}]
        other_hit = {**HIT, 'sub': 'appointment_unavailable_long_wait'}
        sidecar = {'p1': {
            'calls_unanswered': [HIT],
            'booking_friction':  [other_hit],
        }}
        merge(master, sidecar)
        self.assertEqual(set(master[0]['agent_pain_hits']),
                         {'calls_unanswered', 'booking_friction'})


class TestWriteAtomic(unittest.TestCase):
    def test_writes_then_replaces_no_temp_left_behind(self):
        with tempfile.TemporaryDirectory() as tmpd:
            target = Path(tmpd) / 'sub' / 'master.json'
            write_atomic(target, [{'place_id': 'p1', 'agent_pain_hits': {}}])
            self.assertTrue(target.exists())
            # The .json.tmp sibling must have been renamed away.
            self.assertFalse(target.with_suffix(target.suffix + '.tmp').exists())
            self.assertEqual(json.loads(target.read_text())[0]['place_id'], 'p1')


class TestCli(unittest.TestCase):
    def test_end_to_end_writes_new_master_with_hits(self):
        with tempfile.TemporaryDirectory() as tmpd:
            tmpd = Path(tmpd)
            master_in = tmpd / 'in.json'
            sidecar = tmpd / 'sidecar.json'
            master_out = tmpd / 'out.json'
            master_in.write_text(json.dumps([
                {'place_id': 'p1', 'title': 'A'},
                {'place_id': 'p2', 'title': 'B'},
            ]))
            sidecar.write_text(json.dumps({'p1': {'calls_unanswered': [HIT]}}))

            rc = main(['--master', str(master_in), '--sidecar', str(sidecar), '--out', str(master_out)])
            self.assertEqual(rc, 0)
            out = json.loads(master_out.read_text())
            self.assertEqual(out[0]['agent_pain_hits']['calls_unanswered'][0], HIT)
            self.assertEqual(out[1]['agent_pain_hits'], {})
            for lead in out:
                self.assertEqual(lead['agent_pain_hits_source'], PROVENANCE_TAG)


if __name__ == '__main__':
    unittest.main(verbosity=2)
