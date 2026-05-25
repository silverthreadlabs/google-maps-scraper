"""Tests for outreach/lib/render_queries.py."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestRenderQueries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_substitutes_city_state_into_per_city_file(self):
        from lib.render_queries import render_for_campaign
        templates = '{vertical_keyword} in {city} {state}\n'
        location = {
            'metros': ['austin'],
            'neighborhoods': {'austin': []},
            'cities_state': {'austin': 'TX'},
            'cities_vertical_keyword': {'austin': 'dentist'},
        }
        out_dir = self.root / 'queries'
        render_for_campaign(templates, location, out_dir,
                            vertical_keyword='dentist')
        austin = (out_dir / 'austin.txt').read_text()
        self.assertEqual(austin.strip(), 'dentist in austin TX')

    def test_expands_neighborhood_lines_per_neighborhood(self):
        from lib.render_queries import render_for_campaign
        templates = (
            '{vertical_keyword} in {neighborhood} {city} {state}\n'
            '{vertical_keyword} clinic in {city} {state}\n'
        )
        location = {
            'metros': ['austin'],
            'neighborhoods': {'austin': ['Downtown', 'South Austin']},
            'cities_state': {'austin': 'TX'},
            'cities_vertical_keyword': {'austin': 'dentist'},
        }
        out_dir = self.root / 'queries'
        render_for_campaign(templates, location, out_dir,
                            vertical_keyword='dentist')
        lines = (out_dir / 'austin.txt').read_text().splitlines()
        self.assertIn('dentist in Downtown austin TX', lines)
        self.assertIn('dentist in South Austin austin TX', lines)
        self.assertIn('dentist clinic in austin TX', lines)
        self.assertEqual(len(lines), 3)

    def test_skips_template_with_neighborhood_when_city_has_none(self):
        from lib.render_queries import render_for_campaign
        templates = (
            '{vertical_keyword} in {neighborhood} {city} {state}\n'
            '{vertical_keyword} in {city} {state}\n'
        )
        location = {
            'metros': ['kyiv'],
            'neighborhoods': {'kyiv': []},
            'cities_state': {'kyiv': ''},
            'cities_vertical_keyword': {'kyiv': 'software agency'},
        }
        out_dir = self.root / 'queries'
        render_for_campaign(templates, location, out_dir,
                            vertical_keyword='software agency')
        lines = (out_dir / 'kyiv.txt').read_text().splitlines()
        self.assertEqual(lines, ['software agency in kyiv'])

    def test_writes_one_file_per_city(self):
        from lib.render_queries import render_for_campaign
        templates = '{vertical_keyword} in {city} {state}\n'
        location = {
            'metros': ['austin', 'phoenix'],
            'neighborhoods': {'austin': [], 'phoenix': []},
            'cities_state': {'austin': 'TX', 'phoenix': 'AZ'},
            'cities_vertical_keyword': {'austin': 'dentist', 'phoenix': 'dentist'},
        }
        out_dir = self.root / 'queries'
        render_for_campaign(templates, location, out_dir,
                            vertical_keyword='dentist')
        self.assertTrue((out_dir / 'austin.txt').exists())
        self.assertTrue((out_dir / 'phoenix.txt').exists())

    def test_idempotent_second_render_does_not_change_content(self):
        from lib.render_queries import render_for_campaign
        templates = '{vertical_keyword} in {city} {state}\n'
        location = {
            'metros': ['austin'],
            'neighborhoods': {'austin': []},
            'cities_state': {'austin': 'TX'},
            'cities_vertical_keyword': {'austin': 'dentist'},
        }
        out_dir = self.root / 'queries'
        render_for_campaign(templates, location, out_dir,
                            vertical_keyword='dentist')
        first = (out_dir / 'austin.txt').read_text()
        render_for_campaign(templates, location, out_dir,
                            vertical_keyword='dentist')
        self.assertEqual(first, (out_dir / 'austin.txt').read_text())


if __name__ == '__main__':
    unittest.main()
