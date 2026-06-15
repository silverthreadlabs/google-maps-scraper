"""Tests for lib.enrichers.poc_filters — review-author / reviews-widget noise.

Regression for the POC-pollution bug: the crawler harvested JSON-LD
Review.author Persons (e.g. 'Padra M - Los Angeles, CA') into pocs[]. On real
data one lead carried 48 such names. They must be flagged invalid (append-only)
so the handoff drops them, while a genuine small team survives.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from lib.enrichers.poc_filters import is_reviewer_label, flag_review_author_pocs


class TestIsReviewerLabel(unittest.TestCase):
    def test_google_review_author_format_is_flagged(self):
        self.assertTrue(is_reviewer_label('Padra M - Los Angeles, CA'))
        self.assertTrue(is_reviewer_label('Ex P - Mountain View, CA'))

    def test_en_dash_variant(self):
        self.assertTrue(is_reviewer_label('Jamie L – San Jose, CA'))

    def test_real_person_name_is_not_flagged(self):
        self.assertFalse(is_reviewer_label('Victor Amaya'))
        self.assertFalse(is_reviewer_label('Gabriel Alcerro'))

    def test_blank_and_none(self):
        self.assertFalse(is_reviewer_label(''))
        self.assertFalse(is_reviewer_label(None))


class TestFlagReviewAuthorPocs(unittest.TestCase):
    def test_reviewer_label_always_flagged_regardless_of_count(self):
        pocs = [{'name': 'Padra M - Los Angeles, CA'}, {'name': 'Victor Amaya'}]
        out = flag_review_author_pocs(pocs)
        self.assertTrue(out[0]['invalid'])
        self.assertEqual(out[0]['invalid_reason'], 'review_author_label')
        self.assertFalse(out[1].get('invalid'))

    def test_few_bare_pocs_are_kept(self):
        # A real small team: 2 bare names, below the widget threshold.
        pocs = [{'name': 'Victor Amaya'}, {'name': 'Carlos Amaya'}]
        out = flag_review_author_pocs(pocs)
        self.assertFalse(any(p.get('invalid') for p in out))

    def test_many_bare_pocs_flagged_as_widget(self):
        pocs = [{'name': f'Person {i}'} for i in range(12)]
        out = flag_review_author_pocs(pocs)
        self.assertTrue(all(p['invalid'] for p in out))
        self.assertEqual(out[0]['invalid_reason'], 'reviews_widget_suspected')

    def test_poc_with_role_is_never_widget_flagged(self):
        # 6 bare + 1 with a role; widget triggers, but the real staffer survives.
        pocs = [{'name': f'Rev {i}'} for i in range(6)]
        pocs.append({'name': 'Gabriel Alcerro', 'role': 'Founder & CEO'})
        out = flag_review_author_pocs(pocs)
        staffer = next(p for p in out if p['name'] == 'Gabriel Alcerro')
        self.assertFalse(staffer.get('invalid'))
        self.assertTrue(all(p['invalid'] for p in out if p['name'] != 'Gabriel Alcerro'))

    def test_poc_with_email_or_socials_is_not_bare(self):
        pocs = [{'name': f'Rev {i}'} for i in range(6)]
        pocs.append({'name': 'A Owner', 'email': 'a@shop.com'})
        pocs.append({'name': 'B Owner', 'socials': ['https://linkedin.com/in/b']})
        out = flag_review_author_pocs(pocs)
        kept = {p['name'] for p in out if not p.get('invalid')}
        self.assertEqual(kept, {'A Owner', 'B Owner'})

    def test_append_only_does_not_mutate_input_or_drop_rows(self):
        pocs = [{'name': f'Person {i}'} for i in range(12)]
        out = flag_review_author_pocs(pocs)
        self.assertEqual(len(out), len(pocs))                 # no rows dropped
        self.assertNotIn('invalid', pocs[0])                  # input untouched
        self.assertEqual(out[0]['name'], 'Person 0')          # name preserved

    def test_already_invalid_passed_through_untouched(self):
        pocs = [{'name': 'X', 'invalid': True, 'invalid_reason': 'prior'}]
        out = flag_review_author_pocs(pocs)
        self.assertEqual(out[0]['invalid_reason'], 'prior')

    def test_threshold_is_configurable(self):
        pocs = [{'name': f'Person {i}'} for i in range(4)]
        # default max_bare=4 -> 4 is NOT > 4, kept
        self.assertFalse(any(p.get('invalid') for p in flag_review_author_pocs(pocs)))
        # max_bare=2 -> 4 > 2, flagged
        self.assertTrue(all(p['invalid'] for p in flag_review_author_pocs(pocs, max_bare=2)))

    def test_non_dict_entries_pass_through(self):
        pocs = ['weird', {'name': 'Padra M - Los Angeles, CA'}]
        out = flag_review_author_pocs(pocs)
        self.assertEqual(out[0], 'weird')
        self.assertTrue(out[1]['invalid'])

    def test_empty_input(self):
        self.assertEqual(flag_review_author_pocs([]), [])
        self.assertEqual(flag_review_author_pocs(None), [])


if __name__ == '__main__':
    unittest.main()
