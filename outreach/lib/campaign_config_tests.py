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


class TestPythonModuleLoading(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'verticals' / 'dentist').mkdir(parents=True)
        (self.root / 'verticals' / 'dentist' / 'config.py').write_text(
            "PAIN_WEIGHTS = {'calls_unanswered': 5}\n"
            "SERVICE_MAP = {'calls_unanswered': ('Voice AI', 'silverthreadlabs.com/voice')}\n"
            "DSO_TITLE_REGEX = None  # placeholder\n"
            "DSO_EMAIL_DOMAINS = {'aspendental.com'}\n"
            "GEOGRAPHIC_PREFIXES_GENERIC = {'family dental'}\n"
            "VENDOR_DOMAINS_EXTRA = frozenset({'gargle.com'})\n"
            "OSINT_ENABLED = True\n"
        )

    def test_load_vertical_module_returns_module(self):
        from lib.campaign_config import _load_python_module
        mod = _load_python_module(
            self.root / 'verticals' / 'dentist' / 'config.py',
            module_name='outreach_vertical_dentist',
        )
        self.assertEqual(mod.PAIN_WEIGHTS, {'calls_unanswered': 5})

    def test_load_overrides_returns_none_when_file_missing(self):
        from lib.campaign_config import _load_python_module_optional
        mod = _load_python_module_optional(
            self.root / 'campaigns' / 'fake' / 'overrides.py',
            module_name='outreach_overrides_fake',
        )
        self.assertIsNone(mod)

    def test_load_overrides_returns_module_when_present(self):
        (self.root / 'campaigns' / 'with_overrides').mkdir(parents=True)
        (self.root / 'campaigns' / 'with_overrides' / 'overrides.py').write_text(
            "PAIN_WEIGHTS = {'calls_unanswered': 99}\n"
        )
        from lib.campaign_config import _load_python_module_optional
        mod = _load_python_module_optional(
            self.root / 'campaigns' / 'with_overrides' / 'overrides.py',
            module_name='outreach_overrides_with_overrides',
        )
        self.assertIsNotNone(mod)
        self.assertEqual(mod.PAIN_WEIGHTS, {'calls_unanswered': 99})


class TestMergePrimitives(unittest.TestCase):
    def test_concat_regex_alternation(self):
        import re
        from lib.campaign_config import _concat_regex
        a = re.compile(r'\b(Aspen Dental|Heartland)\b', re.I)
        b = re.compile(r'\b(Coast Dental)\b', re.I)
        merged = _concat_regex(a, b)
        self.assertIsNotNone(merged.search('aspen dental'))
        self.assertIsNotNone(merged.search('coast dental'))
        self.assertIsNone(merged.search('mom & pop dentistry'))

    def test_concat_regex_none_extra_returns_base(self):
        import re
        from lib.campaign_config import _concat_regex
        a = re.compile(r'\bAspen Dental\b', re.I)
        merged = _concat_regex(a, None)
        self.assertIs(merged, a)

    def test_concat_regex_none_base_returns_extra(self):
        import re
        from lib.campaign_config import _concat_regex
        b = re.compile(r'\bCoast Dental\b', re.I)
        merged = _concat_regex(None, b)
        self.assertIs(merged, b)

    def test_union_sets(self):
        from lib.campaign_config import _union_sets
        self.assertEqual(_union_sets({'a', 'b'}, {'b', 'c'}), {'a', 'b', 'c'})
        self.assertEqual(_union_sets({'a'}, None), {'a'})
        self.assertEqual(_union_sets(None, {'a'}), {'a'})
        self.assertEqual(_union_sets(None, None), set())

    def test_overlay_dict_replaces_when_present(self):
        from lib.campaign_config import _overlay_dict
        base = {'a': 1, 'b': 2}
        overlay = {'b': 99, 'c': 3}
        self.assertEqual(_overlay_dict(base, overlay), {'a': 1, 'b': 99, 'c': 3})

    def test_overlay_dict_returns_base_when_overlay_none(self):
        from lib.campaign_config import _overlay_dict
        base = {'a': 1}
        result = _overlay_dict(base, None)
        self.assertEqual(result, {'a': 1})
        self.assertIsNot(result, base)


if __name__ == '__main__':
    unittest.main()
