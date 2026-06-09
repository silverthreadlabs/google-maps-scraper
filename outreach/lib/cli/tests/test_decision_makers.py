"""Tests for the unified `decision-makers` stage.

Collapses the old owner-lookup + contacts stages: one research pass per
company captures the owner AND the rest of the reachable team, each as a
`pocs[]` entry with all channels. Exactly one person is designated primary
(explicit `primary:true` -> role keyword -> first); the `owner_*` scalars
become a derived projection of that primary POC.

Hard rules under test:
  * CLAUDE.md rule 1 — existing pocs preserved; re-found people MERGE
    channels (augment), never drop.
  * Idempotency keyed on "is there an owner POC?", NOT "is owner_name set?"
    — so leads that already have owner scalars (the live 173) still gain a
    primary POC.
  * Scalar overwrite is guarded: an existing owner_name is never clobbered.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from lib.cli.decision_makers import (
    apply_sidecar,
    backfill_owner_pocs,
    select_queue,
)


def _lead(pid, *, tier='A', website='https://x.com', qs=10.0, **extra):
    base = {'place_id': pid, 'tier': tier, 'website': website,
            'quality_score': qs, 'title': f'Co {pid}'}
    base.update(extra)
    return base


def _names(lead):
    return [p['name'] for p in lead.get('pocs') or []]


def _by_name(lead, name):
    return next(p for p in lead['pocs'] if p['name'] == name)


class TestSelectQueue(unittest.TestCase):
    def test_filters_by_tier(self):
        master = [_lead('a', tier='A'), _lead('d', tier='D')]
        q = select_queue(master, tiers=('A', 'B', 'C'))
        self.assertEqual([l['place_id'] for l in q], ['a'])

    def test_requires_website_when_asked(self):
        master = [_lead('a', website='https://a.com'), _lead('b', website='')]
        q = select_queue(master, tiers=('A',), require_website=True)
        self.assertEqual([l['place_id'] for l in q], ['a'])

    def test_sorted_by_quality_desc_and_limited(self):
        master = [_lead('lo', qs=1.0), _lead('hi', qs=9.0), _lead('mid', qs=5.0)]
        q = select_queue(master, tiers=('A',), limit=2)
        self.assertEqual([l['place_id'] for l in q], ['hi', 'mid'])


class TestApplyAppendAndPreserve(unittest.TestCase):
    def test_appends_new_people_to_pocs(self):
        master = [_lead('a', pocs=[])]
        sidecar = {'a': [{'name': 'Jane Doe', 'role': 'CTO',
                          'linkedin': 'https://linkedin.com/in/jane', 'confidence': 0.9}]}
        stats = apply_sidecar(master, sidecar, min_confidence=0.5, now_iso='t')
        self.assertEqual(stats['appended'], 1)
        self.assertIn('Jane Doe', _names(master[0]))

    def test_preserves_existing_pocs(self):
        master = [_lead('a', pocs=[{'name': 'Existing', 'confidence': 0.4, 'socials': []}])]
        sidecar = {'a': [{'name': 'New Person', 'role': 'CTO', 'confidence': 0.9}]}
        apply_sidecar(master, sidecar, min_confidence=0.5, now_iso='t')
        self.assertEqual(set(_names(master[0])), {'Existing', 'New Person'})

    def test_skips_below_confidence_floor(self):
        master = [_lead('a', pocs=[])]
        sidecar = {'a': [{'name': 'Low Conf', 'role': 'CTO', 'confidence': 0.3}]}
        stats = apply_sidecar(master, sidecar, min_confidence=0.5, now_iso='t')
        self.assertEqual(master[0]['pocs'], [])
        self.assertEqual(stats['skipped_lowconf'], 1)

    def test_skips_nameless_person(self):
        master = [_lead('a', pocs=[])]
        sidecar = {'a': [{'name': '', 'role': 'CTO', 'confidence': 0.9}]}
        apply_sidecar(master, sidecar, min_confidence=0.5, now_iso='t')
        self.assertEqual(master[0]['pocs'], [])

    def test_counts_orphan_place_ids(self):
        master = [_lead('a', pocs=[])]
        sidecar = {'ghost': [{'name': 'X', 'role': 'CTO', 'confidence': 0.9}]}
        stats = apply_sidecar(master, sidecar, min_confidence=0.5, now_iso='t')
        self.assertEqual(stats['orphan'], 1)
        self.assertEqual(stats['orphan_pids'], ['ghost'])


class TestApplyMergeNotDrop(unittest.TestCase):
    """Re-found people augment the existing POC with new channels (rule 1)."""

    def test_merges_channels_onto_existing_poc_by_name(self):
        master = [_lead('a', pocs=[
            {'name': 'Jane Doe', 'role': 'CTO', 'email': None,
             'socials': ['https://linkedin.com/in/jane'], 'confidence': 0.5}])]
        sidecar = {'a': [{'name': 'jane doe', 'role': 'CTO',
                          'twitter': 'https://x.com/jane', 'email': 'jane@co.com',
                          'confidence': 0.9}]}
        stats = apply_sidecar(master, sidecar, min_confidence=0.5, now_iso='t')
        self.assertEqual(len(master[0]['pocs']), 1)            # no duplicate
        poc = _by_name(master[0], 'Jane Doe')
        self.assertIn('https://x.com/jane', poc['socials'])    # channel added
        self.assertEqual(poc['email'], 'jane@co.com')          # email filled
        self.assertEqual(stats['merged'], 1)

    def test_merges_by_linkedin_url(self):
        master = [_lead('a', pocs=[
            {'name': 'J. D.', 'socials': ['https://linkedin.com/in/jane'], 'confidence': 0.5}])]
        sidecar = {'a': [{'name': 'Jane Doe', 'role': 'CTO',
                          'linkedin': 'https://linkedin.com/in/jane',
                          'instagram': 'https://instagram.com/jane', 'confidence': 0.9}]}
        apply_sidecar(master, sidecar, min_confidence=0.5, now_iso='t')
        self.assertEqual(len(master[0]['pocs']), 1)
        self.assertIn('https://instagram.com/jane', master[0]['pocs'][0]['socials'])

    def test_merges_duplicates_within_batch(self):
        master = [_lead('a', pocs=[])]
        sidecar = {'a': [
            {'name': 'Same Guy', 'role': 'CTO', 'linkedin': 'https://linkedin.com/in/sg',
             'confidence': 0.9},
            {'name': 'same guy', 'role': 'Sales', 'twitter': 'https://x.com/sg',
             'confidence': 0.8},
        ]}
        apply_sidecar(master, sidecar, min_confidence=0.5, now_iso='t')
        self.assertEqual(len(master[0]['pocs']), 1)
        poc = master[0]['pocs'][0]
        self.assertIn('https://linkedin.com/in/sg', poc['socials'])
        self.assertIn('https://x.com/sg', poc['socials'])


class TestPrimaryDesignation(unittest.TestCase):
    def test_explicit_primary_flag_becomes_owner_and_first(self):
        master = [_lead('a', pocs=[])]
        sidecar = {'a': [
            {'name': 'CTO Carl', 'role': 'CTO', 'confidence': 0.9},
            {'name': 'Boss Beth', 'role': 'CTO', 'primary': True,
             'linkedin': 'https://linkedin.com/in/beth', 'confidence': 0.9},
        ]}
        apply_sidecar(master, sidecar, min_confidence=0.5, now_iso='t')
        self.assertEqual(master[0]['pocs'][0]['name'], 'Boss Beth')   # primary first
        self.assertTrue(master[0]['pocs'][0]['primary'])
        self.assertEqual(master[0]['owner_name'], 'Boss Beth')
        self.assertEqual(master[0]['owner_linkedin'], 'https://linkedin.com/in/beth')

    def test_role_keyword_designates_primary_when_no_flag(self):
        master = [_lead('a', pocs=[])]
        sidecar = {'a': [
            {'name': 'CTO Carl', 'role': 'CTO', 'confidence': 0.9},
            {'name': 'Founder Fay', 'role': 'Founder', 'confidence': 0.9},
        ]}
        apply_sidecar(master, sidecar, min_confidence=0.5, now_iso='t')
        self.assertEqual(master[0]['owner_name'], 'Founder Fay')
        self.assertEqual(master[0]['owner_title'], 'Founder')

    def test_first_person_primary_when_no_flag_or_role(self):
        master = [_lead('a', pocs=[])]
        sidecar = {'a': [
            {'name': 'Alpha', 'role': 'Sales', 'confidence': 0.9},
            {'name': 'Beta', 'role': 'Support', 'confidence': 0.9},
        ]}
        apply_sidecar(master, sidecar, min_confidence=0.5, now_iso='t')
        self.assertEqual(master[0]['owner_name'], 'Alpha')

    def test_sets_owner_provenance(self):
        master = [_lead('a', pocs=[])]
        sidecar = {'a': [{'name': 'Fay', 'role': 'Founder', 'confidence': 0.9}]}
        apply_sidecar(master, sidecar, min_confidence=0.5, now_iso='2026-06-08T00:00:00Z')
        self.assertTrue(master[0]['owner_source'])
        self.assertEqual(master[0]['owner_added_at'], '2026-06-08T00:00:00Z')


class TestOwnerScalarGuard(unittest.TestCase):
    def test_existing_owner_name_not_clobbered_but_poc_ensured(self):
        # The live-173 case: owner scalar set by an old run, no owner POC yet.
        # A matching researched person must MATERIALIZE the owner POC with
        # channels, while the manually-set scalar is preserved.
        master = [_lead('a', owner_name='Serge Guzenko', owner_title='CEO',
                        owner_linkedin='https://linkedin.com/in/serge', pocs=[])]
        sidecar = {'a': [
            {'name': 'serge guzenko', 'role': 'CEO',
             'twitter': 'https://x.com/serge', 'email': 'serge@co.com',
             'confidence': 0.9},
            {'name': 'CTO Carl', 'role': 'CTO', 'confidence': 0.9},
        ]}
        apply_sidecar(master, sidecar, min_confidence=0.5, now_iso='t')
        self.assertEqual(master[0]['owner_name'], 'Serge Guzenko')  # NOT clobbered
        owner_poc = master[0]['pocs'][0]
        self.assertEqual(owner_poc['name'].lower(), 'serge guzenko')
        self.assertTrue(owner_poc['primary'])
        self.assertIn('https://x.com/serge', owner_poc['socials'])  # channels gained
        # owner_linkedin was set; merge fills nothing it already had, keeps it
        self.assertEqual(master[0]['owner_linkedin'], 'https://linkedin.com/in/serge')

    def test_empty_owner_name_is_derived_from_primary(self):
        master = [_lead('a', owner_name='', pocs=[])]
        sidecar = {'a': [{'name': 'Fay', 'role': 'Founder',
                          'linkedin': 'https://linkedin.com/in/fay', 'confidence': 0.9}]}
        apply_sidecar(master, sidecar, min_confidence=0.5, now_iso='t')
        self.assertEqual(master[0]['owner_name'], 'Fay')
        self.assertEqual(master[0]['owner_linkedin'], 'https://linkedin.com/in/fay')


class TestIdempotency(unittest.TestCase):
    def test_reapply_is_stable(self):
        master = [_lead('a', pocs=[])]
        sidecar = {'a': [
            {'name': 'Fay', 'role': 'Founder', 'linkedin': 'https://linkedin.com/in/fay',
             'confidence': 0.9},
            {'name': 'Carl', 'role': 'CTO', 'twitter': 'https://x.com/carl', 'confidence': 0.9},
        ]}
        apply_sidecar(master, sidecar, min_confidence=0.5, now_iso='t')
        first = [dict(p) for p in master[0]['pocs']]
        apply_sidecar(master, sidecar, min_confidence=0.5, now_iso='t')
        self.assertEqual(len(master[0]['pocs']), len(first))   # no growth
        self.assertEqual(_names(master[0]).count('Fay'), 1)
        self.assertEqual(master[0]['owner_name'], 'Fay')


class TestBackcompatDictSidecar(unittest.TestCase):
    def test_old_owner_dict_entry_treated_as_single_primary(self):
        # owner-lookup's legacy sidecar shape: {place_id: {name,title,linkedin}}
        master = [_lead('a', pocs=[])]
        sidecar = {'a': {'name': 'Jane Doe', 'title': 'Founder',
                         'linkedin': 'https://linkedin.com/in/jane'}}
        apply_sidecar(master, sidecar, min_confidence=0.5, now_iso='t')
        self.assertEqual(master[0]['owner_name'], 'Jane Doe')
        self.assertEqual(master[0]['owner_title'], 'Founder')
        self.assertTrue(master[0]['pocs'][0]['primary'])


class TestBackfillOwnerPocs(unittest.TestCase):
    def test_synthesizes_owner_poc_from_scalars_when_missing(self):
        master = [_lead('a', owner_name='Jane Doe', owner_title='Founder',
                        owner_linkedin='https://linkedin.com/in/jane', pocs=[])]
        stats = backfill_owner_pocs(master, now_iso='t')
        self.assertEqual(stats['synthesized'], 1)
        poc = master[0]['pocs'][0]
        self.assertEqual(poc['name'], 'Jane Doe')
        self.assertEqual(poc['role'], 'Founder')
        self.assertTrue(poc['primary'])
        self.assertIn('https://linkedin.com/in/jane', poc['socials'])

    def test_idempotent_when_owner_already_a_poc(self):
        master = [_lead('a', owner_name='Jane Doe',
                        pocs=[{'name': 'Jane Doe', 'socials': [], 'primary': True}])]
        stats = backfill_owner_pocs(master, now_iso='t')
        self.assertEqual(stats['synthesized'], 0)
        self.assertEqual(len(master[0]['pocs']), 1)

    def test_skips_leads_without_owner_name(self):
        master = [_lead('a', owner_name='', pocs=[])]
        stats = backfill_owner_pocs(master, now_iso='t')
        self.assertEqual(stats['synthesized'], 0)
        self.assertEqual(master[0]['pocs'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
