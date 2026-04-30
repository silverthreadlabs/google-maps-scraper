"""Tests for outreach.lib.validators.poc (stdlib unittest, no deps)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.validators.poc import validate_poc


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


if __name__ == '__main__':
    unittest.main(verbosity=2)
