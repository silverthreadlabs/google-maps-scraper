"""Tests for outreach.lib.validators.poc (stdlib unittest, no deps)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.validators.poc import validate_poc, poc_confidence


VALID_NAMES = [
    'Patrick Campbell',
    'Dr. Sarah Lee',
    'Maria O\'Brien',
    'Jane Doe',
    'Mark Holmes',
    'Dr. Patrick',          # title + name
    'Sun-Mi Park',          # hyphenated given name
    'Jean-Luc Picard',
    'Ahmad Al-Rashid',
    'Smith',                # single-word surname is plausible
]

# Section-heading captures that the crawler's heading-extractor commonly
# truncates to the first two tokens.
INVALID_SECTION_HEADING = [
    'MEET THE',
    'Meet The',
    'meet the',
    'MEET OUR',
    'Meet Our',
    'OUR TEAM',
    'Our Team',
    'OUR STAFF',
    'OUR STORY',
    'Our Story',
    'ABOUT US',
    'About Us',
    'CONTACT US',
    'Contact Us',
    'WELCOME TO',
    'WHO WE',         # "Who We Are" truncated
]

# Generic label phrases that look name-like but are role/section labels.
INVALID_TEMPLATE_PHRASE = [
    'Our Founder',
    'Our CEO',
    'Our Doctor',
    'Our Doctors',
    'Our Owner',
    'The Owner',
    'The Founder',
    'The Team',
    'The Staff',
]

# Standalone heading words / role tokens with no actual name attached.
INVALID_STANDALONE_HEADING = [
    'Meet',
    'About',
    'Contact',
    'Welcome',
    'Hello',
    'Team',
    'Staff',
    'Doctors',
    'Owner',
    'Founder',
    'CEO',
    'Manager',
    'TEAM',         # caps variants too
    'STAFF',
]

INVALID_TOO_SHORT = ['', '  ', 'A', 'Hi', 'Yo', None]


class TestValidPOCs(unittest.TestCase):
    def test_real_two_word_names_pass(self):
        for name in VALID_NAMES:
            valid, reason = validate_poc(name)
            self.assertTrue(valid, f'expected valid: {name!r} (got reason={reason!r})')
            self.assertIsNone(reason)


class TestSectionHeadings(unittest.TestCase):
    def test_section_heading_truncations_rejected(self):
        for name in INVALID_SECTION_HEADING:
            valid, reason = validate_poc(name)
            self.assertFalse(valid, f'expected invalid: {name!r}')
            self.assertEqual(reason, 'section_heading',
                             f'{name!r} → reason={reason!r}')


class TestTemplatePhrases(unittest.TestCase):
    def test_role_label_phrases_rejected(self):
        for name in INVALID_TEMPLATE_PHRASE:
            valid, reason = validate_poc(name)
            self.assertFalse(valid, f'expected invalid: {name!r}')
            self.assertEqual(reason, 'template_phrase',
                             f'{name!r} → reason={reason!r}')


class TestStandaloneHeadingWords(unittest.TestCase):
    def test_lone_heading_or_role_words_rejected(self):
        for name in INVALID_STANDALONE_HEADING:
            valid, reason = validate_poc(name)
            self.assertFalse(valid, f'expected invalid: {name!r}')
            self.assertEqual(reason, 'standalone_heading',
                             f'{name!r} → reason={reason!r}')


class TestMalformed(unittest.TestCase):
    def test_empty_or_too_short_rejected(self):
        for name in INVALID_TOO_SHORT:
            valid, reason = validate_poc(name)
            self.assertFalse(valid, f'expected invalid: {name!r}')
            self.assertEqual(reason, 'malformed',
                             f'{name!r} → reason={reason!r}')

    def test_non_string_input_rejected(self):
        for value in (123, [], {}, object()):
            valid, reason = validate_poc(value)
            self.assertFalse(valid)
            self.assertEqual(reason, 'malformed')


class TestRetailRegression(unittest.TestCase):
    """The two POCs that leaked through on the retail_toronto run.
    These captured headings that should never have reached the handoff CSV."""

    def test_meet_the_rejected(self):
        # From Over The Rainbow's about page — `<h2>MEET THE TEAM</h2>` truncated.
        valid, reason = validate_poc('MEET THE')
        self.assertFalse(valid)
        self.assertEqual(reason, 'section_heading')

    def test_our_founder_rejected(self):
        # From Province of Canada — `<h2>Our Founder</h2>` section label.
        valid, reason = validate_poc('Our Founder')
        self.assertFalse(valid)
        self.assertEqual(reason, 'template_phrase')


class TestCosmeticSurgeonsDallasRegression(unittest.TestCase):
    """POC patterns that leaked through on the cosmetic_surgeons_dallas run.
    Headings of the form `<X> Dr` (Contact Dr, About Dr, Why Dr, Meet Dr) and
    `<X> We` (What We) need to be caught — the heading extractor truncated
    longer headings ('Meet Dr. Burns', 'What We Treat') to two tokens."""

    def test_contact_dr_rejected(self):
        valid, reason = validate_poc('Contact Dr')
        self.assertFalse(valid)
        self.assertEqual(reason, 'section_heading')

    def test_about_dr_rejected(self):
        valid, reason = validate_poc('About Dr')
        self.assertFalse(valid)
        self.assertEqual(reason, 'section_heading')

    def test_meet_dr_rejected(self):
        # "Meet Dr. Burns" → "Meet Dr" after first-2-tokens truncation.
        valid, reason = validate_poc('Meet Dr')
        self.assertFalse(valid)
        self.assertEqual(reason, 'section_heading')

    def test_why_dr_rejected(self):
        # "Why Dr. Pin?" → "Why Dr" — not a real name.
        valid, reason = validate_poc('Why Dr')
        self.assertFalse(valid)
        self.assertEqual(reason, 'section_heading')

    def test_what_we_rejected(self):
        # "What We Treat" / "What We Offer" → "What We" — not a real name.
        valid, reason = validate_poc('What We')
        self.assertFalse(valid)
        self.assertEqual(reason, 'section_heading')

    def test_in_the_rejected(self):
        # "In The News" / "In The Press" → "In The" prepositional fragment.
        valid, reason = validate_poc('In The')
        self.assertFalse(valid)
        self.assertEqual(reason, 'section_heading')

    def test_real_name_with_dr_suffix_still_passes(self):
        # We're permissive when "Dr" is the FIRST token (the prefix), so
        # passing names like "Dr Burns" must still validate. The reject only
        # fires when the heading-opener pattern matches.
        valid, reason = validate_poc('Dr Burns')
        self.assertTrue(valid, f'reason={reason!r}')


class TestSoftwareSanFranciscoRegression(unittest.TestCase):
    """POC heading/marketing-copy fragments that leaked through on the
    software_sanfrancisco run. The heading extractor truncated longer
    marketing headings to two tokens, leaving a leading determiner /
    pronoun / question word that no real given name uses:
      'Why San Francisco Businesses…' → 'Why San'
      'Your AI-Native Partner'        → 'Your AI-Native'
      'Your Strategic Advantage'      → 'Your Strategic'
      'Your Brand, Amplified'         → 'Your Brand'
      'App Like Uber'                 → 'App Like'
      'Why Partner With Us'           → 'Why Partner'
      'The DJ Booth'                  → 'The DJ'
      'Our CEO's Message'             → 'Our CEO's'
    The existing opener+filler rule missed these because the SECOND token
    is arbitrary copy, not a known filler word."""

    LEAKED = [
        'Why San',
        'Your AI-Native',
        'Your Strategic',
        'Your Brand',
        'App Like',
        'Why Partner',
        'The DJ',
        "Our CEO's",
    ]

    def test_leaked_heading_fragments_rejected(self):
        for name in self.LEAKED:
            valid, reason = validate_poc(name)
            self.assertFalse(valid, f'expected invalid: {name!r}')
            self.assertEqual(reason, 'section_heading',
                             f'{name!r} → reason={reason!r}')

    def test_existing_template_phrases_still_win(self):
        # 'Our Founder' / 'The Owner' start with the same leading words but
        # must keep their MORE-specific 'template_phrase' reason — the broad
        # leading-word rule must not shadow the template-phrase check.
        self.assertEqual(validate_poc('Our Founder')[1], 'template_phrase')
        self.assertEqual(validate_poc('The Owner')[1], 'template_phrase')

    def test_real_two_word_names_with_ordinary_leads_still_pass(self):
        # Guard against over-rejection: real names whose first token is a
        # normal given name must still validate.
        for name in ('Theodore Wu', 'Wendy Chen', 'Owen Park', 'Apple Zhang'):
            valid, reason = validate_poc(name)
            self.assertTrue(valid, f'expected valid: {name!r} (reason={reason!r})')


class TestPOCConfidence(unittest.TestCase):
    """Deterministic 0..1 confidence so downstream consumers (SDR filters,
    a future LLM QA pass) can RANK POCs instead of a human eyeballing each
    row. Calibrated on the software_sanfrancisco crawl: json_ld Person
    schema is the gold source, headings the noisiest, img_alt mixed
    (real headshots AND vendor badges)."""

    # Real people from the actual crawl.
    JSONLD_WITH_ROLE = {'name': 'Kyrylo Lazariev', 'role': 'CEO', 'sources': ['json_ld']}
    JSONLD_NO_ROLE = {'name': 'Laney Silverman', 'role': None, 'sources': ['json_ld']}
    IMG_ALT_PERSON = {'name': 'Jason White', 'role': None, 'sources': ['img_alt']}
    HEADING_PERSON = {'name': 'Michael Terndrup', 'role': None, 'sources': ['heading_h3']}

    # Vendor / certification badges that leaked via img_alt — look exactly
    # like a "Firstname Lastname" pair but are not people.
    BADGE_GOOGLE = {'name': 'Google Partner', 'role': None, 'sources': ['img_alt']}
    BADGE_PREMIER = {'name': 'Google Premier', 'role': None, 'sources': ['img_alt']}
    BADGE_WEBBY = {'name': 'Webby Awards', 'role': None, 'sources': ['img_alt']}

    # A heading fragment validate_poc already rejects.
    INVALID_FRAGMENT = {'name': 'Why San', 'role': None, 'sources': ['heading_h2']}

    def test_returns_float_in_unit_range(self):
        for poc in (self.JSONLD_WITH_ROLE, self.BADGE_GOOGLE, self.INVALID_FRAGMENT,
                    {'name': 'Jane Doe'}, {}):
            c = poc_confidence(poc)
            self.assertIsInstance(c, float)
            self.assertGreaterEqual(c, 0.0)
            self.assertLessEqual(c, 1.0)

    def test_jsonld_person_with_role_is_high(self):
        self.assertGreaterEqual(poc_confidence(self.JSONLD_WITH_ROLE), 0.85)

    def test_jsonld_person_no_role_is_solid(self):
        self.assertGreaterEqual(poc_confidence(self.JSONLD_NO_ROLE), 0.6)

    def test_badges_are_low(self):
        for poc in (self.BADGE_GOOGLE, self.BADGE_PREMIER, self.BADGE_WEBBY):
            self.assertLessEqual(poc_confidence(poc), 0.15,
                                 f'{poc["name"]!r} should be low-confidence')

    def test_invalid_name_is_zero(self):
        # Anything validate_poc rejects bottoms out — no point ranking junk.
        self.assertEqual(poc_confidence(self.INVALID_FRAGMENT), 0.0)

    def test_ranking_order(self):
        # The whole point: a stable gradient downstream can sort on.
        self.assertGreater(poc_confidence(self.JSONLD_WITH_ROLE),
                           poc_confidence(self.JSONLD_NO_ROLE))
        self.assertGreater(poc_confidence(self.JSONLD_NO_ROLE),
                           poc_confidence(self.IMG_ALT_PERSON))
        self.assertGreater(poc_confidence(self.IMG_ALT_PERSON),
                           poc_confidence(self.BADGE_GOOGLE))

    def test_role_boosts_score(self):
        with_role = {'name': 'Sara Kim', 'role': 'Founder', 'sources': ['img_alt']}
        without = {'name': 'Sara Kim', 'role': None, 'sources': ['img_alt']}
        self.assertGreater(poc_confidence(with_role), poc_confidence(without))

    def test_multi_source_corroboration_boosts(self):
        one = {'name': 'Lee Park', 'role': None, 'sources': ['heading_h2']}
        two = {'name': 'Lee Park', 'role': None, 'sources': ['heading_h2', 'json_ld']}
        self.assertGreater(poc_confidence(two), poc_confidence(one))

    def test_real_surname_not_in_badge_set_is_unpenalized(self):
        # 'Gold' is a real surname — must NOT be treated as a badge word, or
        # we'd silently sink real people. json_ld base should stand.
        gold = {'name': 'Sarah Gold', 'role': None, 'sources': ['json_ld']}
        self.assertGreaterEqual(poc_confidence(gold), 0.6)

    def test_handles_missing_or_malformed_fields(self):
        for poc in ({}, {'name': 'Jo'}, {'sources': None, 'role': None}, {'name': None}):
            c = poc_confidence(poc)
            self.assertIsInstance(c, float)


if __name__ == '__main__':
    unittest.main(verbosity=2)
