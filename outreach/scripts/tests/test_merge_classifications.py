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

    def test_pain_breadth_and_categories_recomputed_from_agent_hits(self):
        # csv_builder reads pain_breadth_count from `pain_breadth`/`pain_categories`
        # and only recomputes when quality_score is missing. Agent-only pipelines
        # arrive here with quality_score already set (from analyze) and breadth=0,
        # so without this refresh the handoff CSV ships pain_breadth_count=0.
        master = [{'place_id': 'p1', 'pain_breadth': 0, 'pain_categories': []}]
        other_hit = {**HIT, 'sub': 'appointment_unavailable_long_wait'}
        sidecar = {'p1': {
            'calls_unanswered': [HIT],
            'booking_friction': [other_hit],
        }}
        merge(master, sidecar)
        self.assertEqual(master[0]['pain_breadth'], 2)
        self.assertEqual(master[0]['pain_categories'],
                         ['booking_friction', 'calls_unanswered'])

    def test_pain_breadth_falls_back_to_legacy_when_no_agent_hits(self):
        # When the sidecar has no entry for a lead but legacy SBERT pain_hits
        # exist, breadth/categories should reflect the legacy data — matching
        # csv_builder's `_pain_hits_field` preference order.
        master = [{
            'place_id': 'p1',
            'pain_hits': {
                'missed_calls_unreachable': [{'snippet': 'x'}],
                'surprise_billing': [{'snippet': 'y'}],
            },
        }]
        merge(master, sidecar={})
        self.assertEqual(master[0]['pain_breadth'], 2)
        self.assertEqual(master[0]['pain_categories'],
                         ['missed_calls_unreachable', 'surprise_billing'])

    def test_pain_breadth_zero_when_neither_source_has_hits(self):
        master = [{'place_id': 'p1', 'pain_breadth': 5, 'pain_categories': ['stale']}]
        merge(master, sidecar={})
        self.assertEqual(master[0]['pain_breadth'], 0)
        self.assertEqual(master[0]['pain_categories'], [])

    # ── quality_score / weighted_pain / tier recomputation ────────────────
    # Without these, agent-only pipelines (analyze runs with empty pain →
    # score = log10(reviews)*3 + rating_gap*4) silently keep the analyze-time
    # quality_score after merge fills agent_pain_hits, because csv_builder's
    # _backfill_quality_score early-returns when quality_score is set. Making
    # merge the recompute point keeps master.json self-consistent post-merge.

    def test_quality_score_recomputed_from_agent_hits_when_weights_given(self):
        # weighted = 5 * 2 (two calls_unanswered hits at weight 5) = 10
        # breadth  = 1
        # size     = log10(100) = 2.0  →  weight_size 3 → 6
        # rating_gap = max(0, 4.9 - 4.5) = 0.4  →  weight 4 → 1.6
        # score    = 10 + 1*2 + 6 + 1.6 = 19.6  →  tier 'C'
        master = [{
            'place_id': 'p1',
            'review_count': 100,
            'review_rating': 4.5,
            'quality_score': 7.6,        # stale analyze-time score (empty pain)
            'weighted_pain': 0,
            'tier': 'D',
        }]
        sidecar = {'p1': {'calls_unanswered': [HIT, HIT]}}
        merge(master, sidecar, pain_weights={'calls_unanswered': 5})
        self.assertAlmostEqual(master[0]['quality_score'], 19.6, places=2)
        self.assertEqual(master[0]['weighted_pain'], 10)
        self.assertEqual(master[0]['tier'], 'C')

    def test_quality_score_left_alone_when_no_pain_weights_given(self):
        # Backward compat: the old call shape stays no-op for score/tier.
        master = [{
            'place_id': 'p1',
            'review_count': 100,
            'review_rating': 4.5,
            'quality_score': 7.6,
            'weighted_pain': 0,
            'tier': 'D',
        }]
        sidecar = {'p1': {'calls_unanswered': [HIT, HIT]}}
        merge(master, sidecar)
        self.assertEqual(master[0]['quality_score'], 7.6)
        self.assertEqual(master[0]['weighted_pain'], 0)
        self.assertEqual(master[0]['tier'], 'D')

    def test_quality_score_recomputed_falls_back_to_legacy_pain_when_no_agent_hits(self):
        # If a lead has no sidecar entry but legacy SBERT pain_hits exist,
        # the recompute should use those (matching the breadth fallback).
        master = [{
            'place_id': 'p1',
            'review_count': 100,
            'review_rating': 4.5,
            'pain_hits': {'calls_unanswered': [{'snippet': 'legacy'}]},
            'quality_score': 99.0,       # stale; should be replaced
        }]
        merge(master, sidecar={}, pain_weights={'calls_unanswered': 5})
        # weighted = 5*1 = 5; breadth=1; size=6; gap=1.6 → 5 + 2 + 6 + 1.6 = 14.6
        self.assertAlmostEqual(master[0]['quality_score'], 14.6, places=2)
        self.assertEqual(master[0]['weighted_pain'], 5)
        self.assertEqual(master[0]['tier'], 'D')      # 14.6 < 15

    def test_quality_score_recomputed_to_review_only_when_neither_source_has_hits(self):
        # No agent hits, no legacy pain → score reflects only size + rating_gap.
        master = [{
            'place_id': 'p1',
            'review_count': 100,
            'review_rating': 4.5,
            'quality_score': 88.0,       # whatever was there is replaced
            'weighted_pain': 999,
        }]
        merge(master, sidecar={}, pain_weights={'calls_unanswered': 5})
        # weighted=0, breadth=0, size=6, gap=1.6 → 7.6
        self.assertAlmostEqual(master[0]['quality_score'], 7.6, places=2)
        self.assertEqual(master[0]['weighted_pain'], 0)
        self.assertEqual(master[0]['tier'], 'D')

    def test_quality_score_reads_rating_alias(self):
        # csv_builder reads `rating` (post-handoff alias). Master from analyze
        # writes `review_rating`. Recompute should accept either.
        master = [{
            'place_id': 'p1',
            'review_count': 100,
            'rating': 4.5,                # alias used post-handoff
            'quality_score': 0,
        }]
        sidecar = {'p1': {'calls_unanswered': [HIT]}}
        merge(master, sidecar, pain_weights={'calls_unanswered': 5})
        # weighted=5, breadth=1, size=6, gap=1.6 → 14.6
        self.assertAlmostEqual(master[0]['quality_score'], 14.6, places=2)


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
