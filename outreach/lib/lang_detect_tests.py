"""Tests for the translate-stage language gate."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.lang_detect import needs_translation


class TestNeedsTranslation(unittest.TestCase):
    def test_cyrillic_snippet_needs_translation(self):
        s = "Заказывал доработку сайта, взяли аванс и ничего не сделали"
        self.assertTrue(needs_translation(s, 'uk-UA'))

    def test_english_snippet_in_ua_campaign_skipped(self):
        s = "The program isn't bad, but the manager acts like a debt collector"
        self.assertFalse(needs_translation(s, 'uk-UA'))

    def test_english_locale_always_skips(self):
        s = "Заказывал доработку"  # even Cyrillic is skipped for en campaigns
        self.assertFalse(needs_translation(s, 'en-US'))

    def test_empty_snippet_skipped(self):
        self.assertFalse(needs_translation('', 'uk-UA'))
        self.assertFalse(needs_translation('   ', 'uk-UA'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
