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


if __name__ == '__main__':
    unittest.main()
