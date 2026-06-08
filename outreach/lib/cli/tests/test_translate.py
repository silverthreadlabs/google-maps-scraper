"""Tests for the translate stage's snippet selection."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.cli.translate import snippet_key, select_for_translation


class TestSnippetKey(unittest.TestCase):
    def test_stable_and_whitespace_insensitive(self):
        self.assertEqual(snippet_key('  abc  '), snippet_key('abc'))
        self.assertNotEqual(snippet_key('abc'), snippet_key('abd'))


class TestSelectForTranslation(unittest.TestCase):
    def _lead(self, pid, snippet):
        return {
            'place_id': pid,
            'agent_pain_hits': {
                'frontline_communication': [
                    {'snippet': snippet, 'rating': 1, 'reviewer': 'X'}
                ]
            },
        }

    def test_selects_cyrillic_skips_english(self):
        master = [
            self._lead('p1', 'Заказывал доработку сайта'),
            self._lead('p2', 'The manager never replied'),
        ]
        out = select_for_translation(master, locale='uk-UA',
                                     pain_weights={'frontline_communication': 5})
        self.assertIn('p1', out)
        self.assertNotIn('p2', out)
        (k, v), = out['p1'].items()
        self.assertEqual(v, 'Заказывал доработку сайта')
        self.assertEqual(k, snippet_key('Заказывал доработку сайта'))

    def test_english_locale_yields_empty(self):
        master = [self._lead('p1', 'Заказывал доработку сайта')]
        out = select_for_translation(master, locale='en-US',
                                     pain_weights={'frontline_communication': 5})
        self.assertEqual(out, {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
