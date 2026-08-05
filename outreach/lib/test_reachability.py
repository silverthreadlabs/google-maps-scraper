"""Tests for reachability — channel detection, representative-POC selection,
the no-double-count rule, and the lead-level contact fold."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.reachability import (
    is_personal_linkedin, is_reachable_email, is_personal_social,
    is_personal_email, is_named_business_email,
    usable_contacts, reachability_score,
    W_LINKEDIN, W_EMAIL, W_SOCIAL, W_MULTI, REACH_CAP,
    NO_CHANNEL_MULTI_CAP,
    business_name_coverage, classify_email, email_reach_score,
    phone_first_reachability_score, phone_email_parallel_reachability_score,
    PEP_PHONE_GATE, PEP_E_BLEND, E_PERSON, E_OWNER_INBOX, E_SHOP_INBOX,
    E_UNVERIFIED, E_NONE,
)
from lib.ranking import score_lead, blended_tier


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


class TestEmailClassifiers(unittest.TestCase):
    def test_personal_vs_business_email(self):
        self.assertTrue(is_personal_email('jane.doe@gmail.com'))
        self.assertTrue(is_personal_email('jsmith@yahoo.com'))
        self.assertFalse(is_personal_email('john.doe@acme.com'))   # company domain
        self.assertFalse(is_personal_email('info@gmail.com'))       # generic local
        self.assertTrue(is_named_business_email('john.doe@acme.com'))
        self.assertFalse(is_named_business_email('jane.doe@gmail.com'))
        self.assertFalse(is_named_business_email('info@acme.com'))   # generic local


class TestLpoLadder(unittest.TestCase):
    """DDD-0003: the ladder band IS the tier. A≥75, B 50–74, C 25–49, D<25."""

    def _tier(self, lead):
        r = score_lead(lead, pain_weights={}, reachability_profile='lpo_ladder')
        return r['tier'], r['quality_score']

    def test_A_two_personal_channels(self):
        lead = {'title': 'Acme Law', 'pocs': [
            {'name': 'P1', 'confidence': 0.9, 'socials': ['https://linkedin.com/in/p1'], 'email': None},
            {'name': 'P2', 'confidence': 0.9, 'socials': [], 'email': 'p2@gmail.com'},
        ]}
        t, q = self._tier(lead)
        self.assertEqual(t, 'A')
        self.assertGreaterEqual(q, 75)

    def test_B_one_personal_channel(self):
        lead = {'title': 'Acme Law', 'pocs': [
            {'name': 'P1', 'confidence': 0.9, 'socials': ['https://linkedin.com/in/p1'], 'email': None},
        ]}
        t, q = self._tier(lead)
        self.assertEqual(t, 'B')
        self.assertTrue(50 <= q < 75)

    def test_C_named_business_email_no_personal(self):
        lead = {'title': 'Acme Law', 'phone': '212-555-1000',
                'crawled_emails': ['john.doe@acmelaw.com']}
        t, q = self._tier(lead)
        self.assertEqual(t, 'C')
        self.assertTrue(25 <= q < 50)

    def test_C_personal_social_no_personal_channel(self):
        lead = {'title': 'Acme Law', 'pocs': [
            {'name': 'P1', 'confidence': 0.9, 'socials': ['https://instagram.com/p1_personal'], 'email': None},
        ]}
        self.assertEqual(self._tier(lead)[0], 'C')

    def test_D_generic_email_and_phone(self):
        lead = {'title': 'Acme Law', 'phone': '212-555-1000',
                'crawled_emails': ['info@acmelaw.com']}
        t, q = self._tier(lead)
        self.assertEqual(t, 'D')
        self.assertTrue(0 < q < 25)

    def test_D_phone_only_is_bottom(self):
        lead = {'title': 'Acme Law', 'phone': '212-555-1000'}
        t, q = self._tier(lead)
        self.assertEqual(t, 'D')
        self.assertLess(q, 15)

    def test_unreachable_scores_zero(self):
        t, q = self._tier({'title': 'Acme Law'})
        self.assertEqual(q, 0.0)
        self.assertEqual(t, 'D')

    def test_A_outranks_B_outranks_C_outranks_D(self):
        A = self._tier({'title': 'X', 'pocs': [
            {'name': 'a', 'confidence': 0.9, 'socials': ['https://linkedin.com/in/a'], 'email': 'a@gmail.com'}]})[1]
        B = self._tier({'title': 'X', 'pocs': [
            {'name': 'a', 'confidence': 0.9, 'socials': ['https://linkedin.com/in/a'], 'email': None}]})[1]
        C = self._tier({'title': 'X', 'phone': '212-555-1000', 'crawled_emails': ['j.doe@x.com']})[1]
        D = self._tier({'title': 'X', 'phone': '212-555-1000', 'crawled_emails': ['info@x.com']})[1]
        self.assertGreater(A, B)
        self.assertGreater(B, C)
        self.assertGreater(C, D)

    def test_business_email_does_not_count_as_personal(self):
        # john.doe@firm.com must NOT reach tier A/B — it is a business email (C).
        lead = {'title': 'Firm', 'phone': '212-555-1000',
                'pocs': [{'name': 'John Doe', 'confidence': 0.9, 'socials': [], 'email': 'john.doe@firm.com'}]}
        self.assertEqual(self._tier(lead)[0], 'C')


class TestEmailLadder(unittest.TestCase):
    """DDD-0004 §2: the E-ladder. An address is classified from its domain
    class (freemail / site-aligned / off-site), its local-part class, and its
    provenance (attached to a named POC, or a bare crawl hit)."""

    def _tier(self, lead):
        _, bd = email_reach_score(lead)
        return bd['email_tier']

    def test_E4_person_attributed_poc_email(self):
        lead = {'title': 'Cool Air Tampa', 'website': 'https://coolairtampa.com',
                'pocs': [{'name': 'Rick Torres', 'confidence': 0.9,
                          'email': 'rt@coolairtampa.com', 'socials': []}]}
        self.assertEqual(self._tier(lead), E_PERSON)

    def test_E4_first_last_freemail(self):
        lead = {'title': 'Cool Air Tampa', 'crawled_emails': ['rick.torres@gmail.com']}
        self.assertEqual(self._tier(lead), E_PERSON)

    def test_E4_named_on_own_domain(self):
        lead = {'title': 'Burgess Air', 'website': 'https://burgessair.com',
                'crawled_emails': ['jim.taylor@burgessair.com']}
        self.assertEqual(self._tier(lead), E_PERSON)

    def test_E3_business_name_freemail(self):
        # The brief's headline case: freemail whose local part IS the shop name.
        lead = {'title': 'Bam Air Conditioning Services llc',
                'crawled_emails': ['bamairservices@gmail.com']}
        _, bd = email_reach_score(lead)
        self.assertEqual(bd['email_tier'], E_OWNER_INBOX)
        self.assertEqual(bd['best_reachable_email'], 'bamairservices@gmail.com')

    def test_E3_trade_word_business_name(self):
        # Trade words (hvac / air / comfort) are NOT stripped from the title:
        # they are exactly the evidence that a local part is the business name.
        lead = {'title': 'HVAC Comfort Solutions',
                'crawled_emails': ['hvaccomfortsolutions@yahoo.com']}
        self.assertEqual(self._tier(lead), E_OWNER_INBOX)

    def test_E3_named_mailbox_on_own_domain(self):
        lead = {'title': 'Super Fast AC', 'website': 'https://superfastac.com',
                'crawled_emails': ['jharrell@superfastac.com']}
        self.assertEqual(self._tier(lead), E_OWNER_INBOX)

    def test_E2_role_on_own_domain(self):
        lead = {'title': 'Shop Air', 'website': 'https://shop.com',
                'crawled_emails': ['info@shop.com']}
        _, bd = email_reach_score(lead)
        self.assertEqual(bd['email_tier'], E_SHOP_INBOX)
        self.assertEqual(bd['email_reason'], 'role_site')

    def test_E2_role_prefixed_freemail(self):
        # `is_reachable_email` rejects this outright (the pre-separator token is
        # a role word), but it is Rossi Air's actual inbox — deliverable, E2.
        lead = {'title': 'Rossi Air', 'crawled_emails': ['office.rossiair@gmail.com']}
        self.assertFalse(is_reachable_email('office.rossiair@gmail.com'))
        self.assertEqual(self._tier(lead), E_SHOP_INBOX)

    def test_E1_opaque_freemail_no_attribution(self):
        # Neither is a named person on this lead: E1 "usable, unproven" — the
        # bucket that exists so inference is never promoted to E4.
        for e in ('educationalmargaret3@gmail.com', 'impallari@gmail.com'):
            with self.subTest(email=e):
                lead = {'title': 'Cool Air Tampa', 'crawled_emails': [e]}
                self.assertEqual(self._tier(lead), E_UNVERIFIED)

    def test_E1_partial_business_name_overlap(self):
        # coverage('airluxe', 'Dunedin Air Comfort') = 3/7 = 0.43 — below the
        # 0.5 bar, so "shares a trade word" does not buy E3.
        self.assertAlmostEqual(
            business_name_coverage('airluxe', 'Dunedin Air Comfort'), 3 / 7, places=2)
        lead = {'title': 'Dunedin Air Comfort', 'crawled_emails': ['airluxe@gmail.com']}
        self.assertEqual(self._tier(lead), E_UNVERIFIED)

    def test_E0_off_site_third_party(self):
        # The lead's web developer and a font foundry, not the lead.
        lead = {'title': 'Cool Air Tampa', 'website': 'https://coolairtampa.com',
                'crawled_emails': ['micah@micahrich.com', 'latofonts@latofonts.com']}
        _, bd = email_reach_score(lead)
        self.assertEqual(bd['email_tier'], E_NONE)
        self.assertEqual(bd['best_reachable_email'], '')

    def test_E0_builder_host_not_site_aligned(self):
        # A builder subdomain as the Maps website must not make @webador.com
        # look like the lead's own domain.
        lead = {'title': 'Acme Air', 'website': 'https://acme.webador.com',
                'crawled_emails': ['owner@x.webador.com']}
        self.assertEqual(self._tier(lead), E_NONE)

    def test_freemail_matched_on_registrable_domain(self):
        # tampabay.rr.com is Roadrunner consumer mail, not a third-party domain.
        lead = {'title': 'Cool Air Tampa', 'owner_name': 'Bob Smith',
                'crawled_emails': ['bobsmith@tampabay.rr.com']}
        self.assertIn(self._tier(lead), (E_OWNER_INBOX, E_PERSON))

    def test_invalid_emails_never_scored(self):
        # CLAUDE.md rule 1: the entry stays on the lead, the scorer skips it.
        lead = {'title': 'Cool Air Tampa',
                'crawled_emails': ['rick.torres@gmail.com'],
                'emails_invalid': [{'email': 'rick.torres@gmail.com',
                                    'reason': 'image_artifact'}]}
        score, bd = email_reach_score(lead)
        self.assertEqual(bd['email_tier'], E_NONE)
        self.assertEqual(score, 0.0)
        self.assertEqual(lead['emails_invalid'][0]['email'], 'rick.torres@gmail.com')
        self.assertEqual(lead['crawled_emails'], ['rick.torres@gmail.com'])

    def test_crawled_emails_suspect_caps_at_E1(self):
        lead = {'title': 'Bam Air Conditioning Services llc',
                'crawled_emails': ['bamairservices@gmail.com'],
                'crawled_emails_suspect': True}
        self.assertEqual(self._tier(lead), E_UNVERIFIED)

    def test_second_genuine_email_adds_capped_bonus(self):
        def blend(*emails):
            return email_reach_score({'title': 'Shop Air', 'website': 'https://shop.com',
                                      'crawled_emails': list(emails)})[0]
        one = blend('info@shop.com')
        two = blend('info@shop.com', 'dispatch@shop.com')
        nine = blend(*[f'{r}@shop.com' for r in
                       ('info', 'dispatch', 'billing', 'sales', 'parts', 'claims',
                        'accounting', 'bookings', 'estimating')])
        self.assertGreater(two, one)
        self.assertEqual(nine, two)          # capped — a 9-address crawl is not 9x


class TestPhoneEmailParallelBlend(unittest.TestCase):
    """DDD-0004 §3: the anchored blend. The callable gate keeps DDD-0002's
    25 points exactly; email carries the rest."""

    PROFILE = 'phone_email_parallel'

    def _reach(self, lead):
        return reachability_score(lead, profile=self.PROFILE)[0]

    def test_callable_only_still_clears_C_floor(self):
        # The DDD-0002 guarantee: a callable lead clears the C line at ANY
        # service-fit value, so no model change may dump the corpus into D.
        # rating at the anchor with no pain and no reviews = a zero fit half,
        # so the callable gate is carrying the tier on its own.
        lead = {'title': 'Acme Air', 'phone': '813-555-1000',
                'rating': 4.9, 'review_count': 1}
        self.assertEqual(self._reach(lead), PEP_PHONE_GATE)
        r = score_lead(dict(lead), pain_weights={},
                       reachability_profile=self.PROFILE)
        self.assertEqual(r['service_fit_score'], 0.0)
        self.assertEqual(r['quality_score'], 25.0)
        self.assertEqual(r['tier'], 'C')

    def test_both_channels_beats_either_alone(self):
        base = {'title': 'Bam Air Conditioning Services llc'}
        phone_only = self._reach({**base, 'phone': '813-555-1000'})
        email_only = self._reach({**base, 'crawled_emails': ['bamairservices@gmail.com']})
        both = self._reach({**base, 'phone': '813-555-1000',
                            'crawled_emails': ['bamairservices@gmail.com']})
        self.assertGreater(both, phone_only)
        self.assertGreater(both, email_only)
        # A genuine second channel is worth at least a full E2 band, so it can
        # never be swamped by phone-research ordering points.
        self.assertGreaterEqual(both - phone_only, PEP_E_BLEND[E_SHOP_INBOX])

    def test_email_only_lead_is_not_capped_by_missing_phone(self):
        # phone_first hard-caps this lead at 3.0; once email is an outreach
        # channel, an email-only lead is a real lead.
        lead = {'title': 'Bam Air Conditioning Services llc',
                'phone': '813-555-1000', 'phone_invalid': True,
                'crawled_emails': ['bamairservices@gmail.com']}
        self.assertLessEqual(phone_first_reachability_score(lead)[0], NO_CHANNEL_MULTI_CAP)
        self.assertEqual(self._reach(lead), PEP_E_BLEND[E_OWNER_INBOX])

    def test_no_channel_at_all_capped_at_three(self):
        lead = {'title': 'Acme Air', 'owner_name': 'Rick Torres',
                'pocs': [{'name': 'Dana Lee', 'confidence': 0.9, 'socials': [],
                          'email': None}]}
        self.assertLessEqual(self._reach(lead), NO_CHANNEL_MULTI_CAP)

    def test_reach_never_exceeds_cap(self):
        lead = {'title': 'Bam Air Conditioning Services llc',
                'website': 'https://bamair.com', 'phone': '813-555-1000',
                'owner_name': 'Rick Torres', 'owner_email': 'rick.torres@bamair.com',
                'crawled_emails': ['dana.lee@bamair.com', 'info@bamair.com'],
                'pocs': [{'name': 'Dana Lee', 'confidence': 0.9, 'phone': '813-555-2000',
                          'socials': ['https://linkedin.com/in/danalee'],
                          'email': 'dana.lee@bamair.com'},
                         {'name': 'Sam Ray', 'confidence': 0.9, 'socials': [],
                          'email': 'sam.ray@bamair.com'}]}
        self.assertEqual(self._reach(lead), REACH_CAP)

    def test_phone_research_adds_under_two_points_to_the_blend(self):
        # Research depth carries ORDERING weight only in the blended half: it
        # cannot move a lead across a 25-point tier band on its own. (It still
        # pays for itself through the email leg — a known name is what lifts an
        # address to E4.)
        callable_only = self._reach({'title': 'Acme Air', 'phone': '813-555-1000'})
        researched = self._reach({
            'title': 'Acme Air', 'phone': '813-555-1000', 'owner_name': 'Rick Torres',
            'pocs': [{'name': 'Dana Lee', 'confidence': 0.9, 'phone': '813-555-2000',
                      'socials': [], 'email': None},
                     {'name': 'Sam Ray', 'confidence': 0.9, 'socials': [], 'email': None}]})
        self.assertLess(researched - callable_only, 2.0)


# A table spanning every branch the profiles disagree on: phone-only, phone +
# name, fully-researched, email-only with a dead phone, freemail-only, empty.
ISOLATION_LEADS = [
    {'title': 'Acme Air', 'phone': '813-555-1000'},
    {'title': 'Acme Air', 'phone': '813-555-1000', 'owner_name': 'Rick Torres'},
    {'title': 'Acme Air', 'phone': '813-555-1000', 'owner_name': 'Rick Torres',
     'owner_email': 'rick.torres@gmail.com',
     'pocs': [{'name': 'Dana Lee', 'confidence': 0.9, 'phone': '813-555-2000',
               'socials': ['https://linkedin.com/in/danalee'], 'email': 'dana@acmeair.com'}]},
    {'title': 'Acme Air', 'phone': '813-555-1000', 'phone_invalid': True,
     'crawled_emails': ['info@acmeair.com'], 'website': 'https://acmeair.com'},
    {'title': 'Acme Air', 'crawled_emails': ['bamairservices@gmail.com']},
    {'title': 'Acme Air'},
]


class TestProfileIsolation(unittest.TestCase):
    """The safety net: the fourth profile is additive. Nothing else moves."""

    def test_phone_channel_facts_match_phone_first(self):
        # The new profile reuses phone_first UNCHANGED for its channel
        # detection — this replaced the dropped `phone_arm_tier` column.
        for lead in ISOLATION_LEADS:
            with self.subTest(title=lead.get('phone'), lead=lead):
                _, pf = phone_first_reachability_score(dict(lead))
                _, pep = phone_email_parallel_reachability_score(dict(lead))
                phone_tags = [c for c in pep['channels'] if not c.startswith('email:')]
                self.assertEqual(phone_tags, pf['channels'])
                self.assertEqual(pep['representative'], pf['representative'])
                self.assertEqual(pep['usable_poc_count'], pf['usable_poc_count'])

    def test_other_profiles_unchanged(self):
        # Golden table pinned to today's values — protects attorney_newyork,
        # hvac_phoenix, hvac_dallas, hvac_atlanta and automotive_sanfrancisco
        # from the shared-list edits.
        golden = {
            'poc_channels': [0.0, 0.0, 50.0, 0.0, 0.0, 0.0],
            'phone_first': [25.0, 40.0, 50.0, 0.0, 0.0, 0.0],
            'lpo_ladder': [8.0, 8.0, 88.0, 8.0, 60.0, 0.0],
        }
        golden_channels = {
            'poc_channels': [[], [], ['linkedin', 'email'], [], [], []],
            'phone_first': [['phone'], ['phone', 'named_decision_maker'],
                            ['phone', 'named_decision_maker', 'direct_line',
                             'fallback_contact', 'bonus_channel'], [], [], []],
            'lpo_ladder': [['phone'], ['phone'],
                           ['poc_linkedin', 'personal_email',
                            'named_business_email', 'phone'],
                           ['business_email'], ['personal_email'], []],
        }
        for profile, expected in golden.items():
            got = [reachability_score(dict(l), profile=profile)[0] for l in ISOLATION_LEADS]
            self.assertEqual(got, expected, profile)
            got_ch = [reachability_score(dict(l), profile=profile)[1]['channels']
                      for l in ISOLATION_LEADS]
            self.assertEqual(got_ch, golden_channels[profile], profile)

    def test_unknown_profile_falls_back_to_poc_channels(self):
        for lead in ISOLATION_LEADS:
            self.assertEqual(reachability_score(dict(lead), profile='nonsense'),
                             reachability_score(dict(lead), profile='poc_channels'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
