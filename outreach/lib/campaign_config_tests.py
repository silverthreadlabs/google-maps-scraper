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


if __name__ == '__main__':
    unittest.main()
