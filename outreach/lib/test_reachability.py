"""Tests for reachability — channel detection, representative-POC selection,
the no-double-count rule, and the lead-level contact fold."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.reachability import (
    is_personal_linkedin, is_reachable_email, is_personal_social,
    usable_contacts, reachability_score,
    W_LINKEDIN, W_EMAIL, W_SOCIAL, W_MULTI, REACH_CAP,
)


class TestChannelDetectors(unittest.TestCase):
    def test_personal_linkedin_only_in_profiles(self):
        self.assertTrue(is_personal_linkedin('https://www.linkedin.com/in/jane-doe-123'))
        self.assertFalse(is_personal_linkedin('https://linkedin.com/company/acme'))
        self.assertFalse(is_personal_linkedin(''))
        self.assertFalse(is_personal_linkedin(None))

    def test_reachable_email_rejects_role_mailboxes(self):
        for ok in ('john-doe@acme.com', 'jdoe@gmail.com', 'j.smith@firm.io'):
            self.assertTrue(is_reachable_email(ok), ok)
        for bad in ('info@acme.com', 'contact@acme.com', 'sales.team@acme.com',
                    'office@x.com', 'not-an-email', '', None):
            self.assertFalse(is_reachable_email(bad), bad)

    def test_personal_social_excludes_business_pages(self):
        self.assertTrue(is_personal_social('https://facebook.com/john.doe.5', 'Acme Tires'))
        self.assertTrue(is_personal_social('https://instagram.com/janedoe', 'Acme Tires'))
        # business's own page (handle ~ business name) is not a POC social
        self.assertFalse(is_personal_social('https://www.facebook.com/AcmeTires', 'Acme Tires'))
        self.assertFalse(is_personal_social('https://facebook.com/pages/Acme/123', 'Acme'))
        # linkedin is scored separately, never via this detector
        self.assertFalse(is_personal_social('https://linkedin.com/in/x', 'Acme'))


class TestUsableContacts(unittest.TestCase):
    def test_excludes_invalid_and_low_confidence(self):
        lead = {'title': 'Acme', 'pocs': [
            {'name': 'Real', 'confidence': 0.7, 'socials': [], 'email': None},
            {'name': 'Badge', 'confidence': 0.1, 'socials': [], 'email': None},
            {'name': 'Flagged', 'invalid': True, 'confidence': 0.9, 'socials': [], 'email': None},
        ]}
        names = [c.name for c in usable_contacts(lead)]
        self.assertEqual(names, ['Real'])

    def test_folds_lead_level_owner_linkedin_with_no_matching_poc(self):
        # owner-research writes owner_linkedin at the LEAD level; it must count
        # even when there is no pocs[] entry for that person.
        lead = {'title': 'Acme', 'owner_name': 'Pat Lee',
                'owner_linkedin': 'https://linkedin.com/in/patlee'}
        cs = usable_contacts(lead)
        self.assertEqual(len(cs), 1)
        self.assertTrue(cs[0].has_linkedin)

    def test_folds_lead_level_channels_into_matching_poc(self):
        lead = {'title': 'Acme',
                'pocs': [{'name': 'Pat Lee', 'confidence': 0.7, 'socials': [], 'email': None}],
                'owner_name': 'Pat Lee', 'owner_linkedin': 'https://linkedin.com/in/patlee'}
        cs = usable_contacts(lead)
        self.assertEqual(len(cs), 1)            # not duplicated
        self.assertTrue(cs[0].has_linkedin)


class TestReachabilityScore(unittest.TestCase):
    def _lead(self, pocs):
        return {'title': 'Acme', 'pocs': pocs}

    def test_no_contacts_scores_zero(self):
        score, bd = reachability_score({'title': 'Acme'})
        self.assertEqual(score, 0.0)
        self.assertEqual(bd['usable_poc_count'], 0)

    def test_single_poc_linkedin(self):
        score, bd = reachability_score(self._lead(
            [{'name': 'A', 'confidence': 0.9, 'socials': ['https://linkedin.com/in/a'], 'email': None}]))
        self.assertEqual(score, W_LINKEDIN)            # 30, no multi (n=1)
        self.assertEqual(bd['channels'], ['linkedin'])

    def test_channels_stack_within_one_poc_then_cap(self):
        score, _ = reachability_score(self._lead(
            [{'name': 'A', 'confidence': 0.9,
              'socials': ['https://linkedin.com/in/a', 'https://instagram.com/a_personal'],
              'email': 'a.person@firm.com'}]))
        # 30 + 18 + 8 = 56 -> capped at 50 (single POC, no multi)
        self.assertEqual(score, REACH_CAP)

    def test_no_double_count_socials_across_pocs(self):
        # B-1 example: P1 and P2 each have personal socials. Only one POC's
        # socials are credited (W_SOCIAL); the second contributes ONLY via the
        # capped multi-POC boost — never a second W_SOCIAL.
        score, bd = reachability_score(self._lead([
            {'name': 'P1', 'confidence': 0.9,
             'socials': ['https://instagram.com/p1', 'https://facebook.com/p1.personal'], 'email': None},
            {'name': 'P2', 'confidence': 0.9,
             'socials': ['https://instagram.com/p2'], 'email': None},
        ]))
        expected = W_SOCIAL + W_MULTI * (1 - 1/2)      # 8 + 5 = 13
        self.assertAlmostEqual(score, expected, places=2)
        self.assertNotAlmostEqual(score, W_SOCIAL * 2, places=2)  # NOT 16
        self.assertEqual(bd['usable_poc_count'], 2)

    def test_multi_poc_boost_diminishes_and_caps(self):
        def lead_n(n):
            return self._lead([{'name': f'P{i}', 'confidence': 0.9,
                                'socials': ['https://linkedin.com/in/p%d' % i], 'email': None}
                               for i in range(n)])
        s1, _ = reachability_score(lead_n(1))
        s2, _ = reachability_score(lead_n(2))
        s50, _ = reachability_score(lead_n(50))
        self.assertEqual(s1, W_LINKEDIN)                       # 30
        self.assertLess(s2 - s1, W_MULTI)                      # 2nd POC < full multi
        self.assertLessEqual(s50, REACH_CAP)                   # capped
        self.assertGreater(s50, s2)                            # but more is still more

    def test_channel_less_contacts_capped_at_three(self):
        # Named, above-confidence POCs with NO reachable channel (no personal
        # LinkedIn, reachable email, or personal social) can't actually be
        # reached. Extra such contacts add a little (a research starting point)
        # but the boost is capped low (3) — never the full multi-POC boost.
        # A lead we can't reach by any channel is only marginally better than
        # one with no contacts at all. See DDD-0001.
        def channelless(k):
            return self._lead([{'name': f'N{i}', 'confidence': 0.9,
                                'socials': [], 'email': None} for i in range(k)])
        self.assertEqual(reachability_score(channelless(1))[0], 0.0)   # one name → still 0
        self.assertEqual(reachability_score(channelless(2))[0], 3.0)   # capped (was 5)
        self.assertEqual(reachability_score(channelless(9))[0], 3.0)   # never climbs
        _, bd2 = reachability_score(channelless(2))
        self.assertEqual(bd2['channels'], [])                          # genuinely unreachable


if __name__ == '__main__':
    unittest.main(verbosity=2)
