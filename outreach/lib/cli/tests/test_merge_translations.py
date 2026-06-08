"""Tests for grafting translations into master."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.cli.merge_translations import merge
from lib.cli.translate import snippet_key


class TestMergeTranslations(unittest.TestCase):
    def _master(self):
        snip = 'Заказывал доработку сайта'
        return [{
            'place_id': 'p1',
            'agent_pain_hits': {
                'frontline_communication': [
                    {'snippet': snip, 'rating': 1, 'reviewer': 'X'}
                ]
            },
        }], snip

    def test_grafts_snippet_en_with_provenance(self):
        master, snip = self._master()
        sidecar = {'p1': {snippet_key(snip): 'Ordered a website revision'}}
        stats = merge(master, sidecar)
        hit = master[0]['agent_pain_hits']['frontline_communication'][0]
        self.assertEqual(hit['snippet_en'], 'Ordered a website revision')
        self.assertEqual(hit['snippet_en_source'], 'translator-subagent')
        self.assertIn('snippet_en_added_at', hit)
        self.assertEqual(stats['snippets_translated'], 1)

    def test_idempotent_and_passthrough(self):
        master, snip = self._master()
        # English-source hit with no matching key is left untouched
        sidecar = {'p1': {}}
        merge(master, sidecar)
        hit = master[0]['agent_pain_hits']['frontline_communication'][0]
        self.assertNotIn('snippet_en', hit)


if __name__ == '__main__':
    unittest.main(verbosity=2)
