"""Tests for the shared POC/channel helpers (`lib.cli._pocs`).

These are the pure functions the unified `decision-makers` stage (and its
deprecated `owner-lookup` / `contacts` aliases) build on: channel collection,
identity normalization, primary-buyer designation, owner-scalar projection,
and channel merging (augment-never-drop).
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from lib.cli._pocs import (
    CHANNEL_KEYS,
    channels_from_person,
    is_primary_role,
    merge_channels_into_poc,
    norm_name,
    norm_url,
    owner_scalars_from_poc,
    pick_primary_index,
    poc_from_person,
)


class TestNormalizers(unittest.TestCase):
    def test_norm_name_lowercases_and_collapses_space(self):
        self.assertEqual(norm_name('  Serge   Guzenko '), 'serge guzenko')
        self.assertEqual(norm_name(None), '')

    def test_norm_url_strips_scheme_www_trailing_slash(self):
        self.assertEqual(
            norm_url('https://www.LinkedIn.com/in/Jane/'),
            'linkedin.com/in/jane',
        )
        self.assertEqual(norm_url(None), '')


class TestChannelsFromPerson(unittest.TestCase):
    def test_collects_all_channel_keys_in_priority_order(self):
        person = {
            'linkedin': 'https://linkedin.com/in/j',
            'twitter': 'https://x.com/j',
            'instagram': 'https://instagram.com/j',
            'facebook': 'https://facebook.com/j',
        }
        out = channels_from_person(person)
        self.assertEqual(out[0], 'https://linkedin.com/in/j')  # linkedin first
        self.assertEqual(len(out), 4)

    def test_x_alias_maps_in_too(self):
        out = channels_from_person({'x': 'https://x.com/j'})
        self.assertEqual(out, ['https://x.com/j'])

    def test_merges_freeform_socials_and_dedupes(self):
        person = {
            'linkedin': 'https://linkedin.com/in/j',
            'socials': ['https://linkedin.com/in/j', 'https://github.com/j'],
        }
        out = channels_from_person(person)
        self.assertEqual(out, ['https://linkedin.com/in/j', 'https://github.com/j'])

    def test_empty_when_no_channels(self):
        self.assertEqual(channels_from_person({'name': 'X'}), [])


class TestPocFromPerson(unittest.TestCase):
    def test_maps_role_email_socials_confidence_primary(self):
        poc = poc_from_person(
            {'name': 'Jane', 'role': 'CTO', 'email': 'j@co.com',
             'linkedin': 'https://linkedin.com/in/j', 'confidence': 0.9,
             'primary': True},
            source='decision_maker_research', now_iso='t',
        )
        self.assertEqual(poc['name'], 'Jane')
        self.assertEqual(poc['role'], 'CTO')
        self.assertEqual(poc['email'], 'j@co.com')
        self.assertIn('https://linkedin.com/in/j', poc['socials'])
        self.assertEqual(poc['confidence'], 0.9)
        self.assertTrue(poc['primary'])
        self.assertEqual(poc['source'], 'decision_maker_research')
        self.assertEqual(poc['added_at'], 't')

    def test_role_falls_back_to_title_then_none(self):
        # owner-style sidecar uses `title`, not `role`
        self.assertEqual(
            poc_from_person({'name': 'J', 'title': 'Founder'}, source='s', now_iso='t')['role'],
            'Founder',
        )
        self.assertIsNone(
            poc_from_person({'name': 'J'}, source='s', now_iso='t')['role'],
        )

    def test_primary_defaults_false(self):
        self.assertFalse(
            poc_from_person({'name': 'J'}, source='s', now_iso='t')['primary'],
        )


class TestIsPrimaryRole(unittest.TestCase):
    def test_matches_decision_maker_titles(self):
        for r in ['Founder', 'Co-Founder', 'co founder', 'CEO', 'Owner',
                  'Managing Director', 'Principal']:
            self.assertTrue(is_primary_role(r), r)

    def test_rejects_non_primary_titles(self):
        for r in ['CTO', 'Head of Sales', 'BizDev', 'Engineer', '', None]:
            self.assertFalse(is_primary_role(r), r)


class TestPickPrimaryIndex(unittest.TestCase):
    def test_explicit_primary_flag_wins(self):
        pocs = [{'name': 'A', 'role': 'CEO'}, {'name': 'B', 'role': 'CTO', 'primary': True}]
        self.assertEqual(pick_primary_index(pocs), 1)

    def test_role_keyword_when_no_flag(self):
        pocs = [{'name': 'A', 'role': 'CTO'}, {'name': 'B', 'role': 'Founder'}]
        self.assertEqual(pick_primary_index(pocs), 1)

    def test_first_when_no_flag_or_role(self):
        pocs = [{'name': 'A', 'role': 'CTO'}, {'name': 'B', 'role': 'Sales'}]
        self.assertEqual(pick_primary_index(pocs), 0)

    def test_none_when_empty(self):
        self.assertIsNone(pick_primary_index([]))


class TestOwnerScalarsFromPoc(unittest.TestCase):
    def test_projects_name_title_first_linkedin(self):
        poc = {'name': 'Jane Doe', 'role': 'Founder',
               'socials': ['https://x.com/j', 'https://linkedin.com/in/jane']}
        s = owner_scalars_from_poc(poc)
        self.assertEqual(s['name'], 'Jane Doe')
        self.assertEqual(s['title'], 'Founder')
        self.assertEqual(s['linkedin'], 'https://linkedin.com/in/jane')

    def test_empty_linkedin_when_none_present(self):
        s = owner_scalars_from_poc({'name': 'J', 'role': None, 'socials': ['https://x.com/j']})
        self.assertEqual(s['linkedin'], '')
        self.assertEqual(s['title'], '')


class TestMergeChannelsIntoPoc(unittest.TestCase):
    def test_adds_missing_socials_without_duplicates(self):
        existing = {'name': 'J', 'socials': ['https://linkedin.com/in/j']}
        merge_channels_into_poc(
            existing,
            poc_from_person({'name': 'J', 'twitter': 'https://x.com/j',
                             'linkedin': 'https://linkedin.com/in/j'},
                            source='s', now_iso='t'),
        )
        self.assertEqual(
            existing['socials'],
            ['https://linkedin.com/in/j', 'https://x.com/j'],
        )

    def test_fills_empty_email_role_url_but_does_not_clobber(self):
        existing = {'name': 'J', 'role': 'CTO', 'email': None, 'socials': []}
        merge_channels_into_poc(
            existing,
            poc_from_person({'name': 'J', 'role': 'VP', 'email': 'j@co.com',
                             'url': 'https://co.com/j'}, source='s', now_iso='t'),
        )
        self.assertEqual(existing['email'], 'j@co.com')  # filled
        self.assertEqual(existing['url'], 'https://co.com/j')  # filled
        self.assertEqual(existing['role'], 'CTO')  # NOT clobbered

    def test_ors_in_primary_and_takes_max_confidence(self):
        existing = {'name': 'J', 'socials': [], 'primary': False, 'confidence': 0.6}
        merge_channels_into_poc(
            existing,
            poc_from_person({'name': 'J', 'primary': True, 'confidence': 0.9},
                            source='s', now_iso='t'),
        )
        self.assertTrue(existing['primary'])
        self.assertEqual(existing['confidence'], 0.9)


if __name__ == '__main__':
    unittest.main(verbosity=2)
