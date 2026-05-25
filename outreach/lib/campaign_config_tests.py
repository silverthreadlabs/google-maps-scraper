"""Tests for outreach/lib/campaign_config.py."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestImports(unittest.TestCase):
    def test_can_import_campaign_config_dataclass(self):
        from lib.campaign_config import CampaignConfig
        self.assertTrue(hasattr(CampaignConfig, '__dataclass_fields__'))

    def test_can_import_load_function(self):
        from lib.campaign_config import load_campaign
        self.assertTrue(callable(load_campaign))


class TestCampaignYamlParsing(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'campaigns' / 'dentist_sunbelt').mkdir(parents=True)
        (self.root / 'campaigns' / 'dentist_sunbelt' / 'campaign.yaml').write_text(
            "vertical: dentist\n"
            "location: sunbelt\n"
            "slug: dentist_sunbelt\n"
            "display_name: Dental Sunbelt\n"
        )

    def test_reads_vertical_location_slug(self):
        from lib.campaign_config import _read_campaign_yaml
        meta = _read_campaign_yaml(
            self.root / 'campaigns' / 'dentist_sunbelt' / 'campaign.yaml'
        )
        self.assertEqual(meta['vertical'], 'dentist')
        self.assertEqual(meta['location'], 'sunbelt')
        self.assertEqual(meta['slug'], 'dentist_sunbelt')

    def test_missing_file_raises_filenotfound(self):
        from lib.campaign_config import _read_campaign_yaml
        with self.assertRaises(FileNotFoundError):
            _read_campaign_yaml(self.root / 'campaigns' / 'nonexistent.yaml')

    def test_missing_required_key_raises_valueerror(self):
        (self.root / 'campaigns' / 'broken').mkdir()
        (self.root / 'campaigns' / 'broken' / 'campaign.yaml').write_text(
            "vertical: dentist\n"  # no location, no slug
        )
        from lib.campaign_config import _read_campaign_yaml
        with self.assertRaises(ValueError) as cm:
            _read_campaign_yaml(self.root / 'campaigns' / 'broken' / 'campaign.yaml')
        self.assertIn('location', str(cm.exception))


class TestLocationYamlParsing(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'locations').mkdir()
        (self.root / 'locations' / 'sunbelt.yaml').write_text(
            "country: US\n"
            "locale: en-US\n"
            "cities:\n"
            "  - name: austin\n"
            "    state: TX\n"
            "    metro_area_codes: ['512', '737']\n"
            "    geographic_prefixes:\n"
            "      - south austin\n"
            "      - round rock\n"
            "    neighborhoods:\n"
            "      - Downtown\n"
            "      - South Austin\n"
            "  - name: phoenix\n"
            "    state: AZ\n"
            "    metro_area_codes: ['480', '602']\n"
            "    geographic_prefixes:\n"
            "      - chandler\n"
            "    neighborhoods:\n"
            "      - Downtown Phoenix\n"
        )

    def test_extracts_metros_in_order(self):
        from lib.campaign_config import _read_location_yaml
        loc = _read_location_yaml(self.root / 'locations' / 'sunbelt.yaml')
        self.assertEqual(loc['metros'], ['austin', 'phoenix'])

    def test_extracts_metro_area_codes_as_sets(self):
        from lib.campaign_config import _read_location_yaml
        loc = _read_location_yaml(self.root / 'locations' / 'sunbelt.yaml')
        self.assertEqual(loc['metro_area_codes']['austin'], {'512', '737'})
        self.assertEqual(loc['metro_area_codes']['phoenix'], {'480', '602'})

    def test_unions_geographic_prefixes_across_cities(self):
        from lib.campaign_config import _read_location_yaml
        loc = _read_location_yaml(self.root / 'locations' / 'sunbelt.yaml')
        self.assertEqual(
            loc['geographic_prefixes'],
            {'south austin', 'round rock', 'chandler'},
        )

    def test_keeps_per_city_neighborhoods(self):
        from lib.campaign_config import _read_location_yaml
        loc = _read_location_yaml(self.root / 'locations' / 'sunbelt.yaml')
        self.assertEqual(
            loc['neighborhoods']['austin'],
            ['Downtown', 'South Austin'],
        )
        self.assertEqual(
            loc['neighborhoods']['phoenix'],
            ['Downtown Phoenix'],
        )


if __name__ == '__main__':
    unittest.main()
