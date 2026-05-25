"""Phase-A gate test: the new loader output must match each existing
pipelines/<x>/config.py module on every field the CLI scripts read.

Skipped when run after Phase B (the old pipelines/ dirs go away).
"""
from __future__ import annotations

import importlib.util as iu
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.campaign_config import load_campaign


MIGRATIONS = [
    # ('dentist_sunbelt', 'dental_sunbelt'),  # migrated in Phase B — old config.py removed
    # ('software_ua', 'software_ua'),  # migrated in Phase C
    # ('cosmetic_surgeons_dallas', 'cosmetic_surgeons_dallas'),  # migrated in Phase C

    ('retail_toronto',            'retail_toronto'),
]


def _load_old(pipeline_name: str):
    path = Path(__file__).resolve().parent.parent / 'pipelines' / pipeline_name / 'config.py'
    spec = iu.spec_from_file_location(f'old_{pipeline_name}', path)
    mod = iu.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestNewLoaderMatchesOldConfigs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        outreach_root = Path(__file__).resolve().parent.parent
        if not (outreach_root / 'pipelines').is_dir():
            raise unittest.SkipTest('pipelines/ already removed — phase B done')
        if not (outreach_root / 'campaigns').is_dir():
            raise unittest.SkipTest('campaigns/ not built yet — phase A incomplete')

    def _assert_equivalent(self, new, old, *, has_overrides=False):
        self.assertEqual(new.pain_weights, old.PAIN_WEIGHTS,
                         msg='PAIN_WEIGHTS diverge')
        self.assertEqual(new.service_map, old.SERVICE_MAP,
                         msg='SERVICE_MAP diverge')
        self.assertEqual(
            new.dso_email_domains,
            set(getattr(old, 'DSO_EMAIL_DOMAINS', set())),
            msg='DSO_EMAIL_DOMAINS diverge',
        )
        self.assertEqual(
            new.vendor_domains_extra,
            frozenset(getattr(old, 'VENDOR_DOMAINS_EXTRA', frozenset())),
            msg='VENDOR_DOMAINS_EXTRA diverge',
        )
        self.assertEqual(
            new.metros, getattr(old, 'METROS', []),
            msg='METROS diverge',
        )
        self.assertEqual(
            {m: set(c) for m, c in new.metro_area_codes.items()},
            {m: set(c) for m, c in getattr(old, 'METRO_AREA_CODES', {}).items()},
            msg='METRO_AREA_CODES diverge',
        )
        self.assertEqual(
            new.geographic_prefixes,
            set(getattr(old, 'GEOGRAPHIC_PREFIXES', set())),
            msg='GEOGRAPHIC_PREFIXES diverge (union of vertical generic + location must equal old)',
        )
        old_profile = getattr(old, 'ENRICH_PROFILE', None)
        if old_profile is not None:
            self.assertEqual(new.enrich_profile, old_profile)
        old_re = getattr(old, 'DSO_TITLE_REGEX', None)
        if old_re is not None:
            for sample in self._regex_samples_for_pipeline(old):
                if old_re.search(sample):
                    self.assertIsNotNone(
                        new.dso_title_regex.search(sample),
                        msg=f'new DSO regex missed {sample!r}',
                    )

    def _regex_samples_for_pipeline(self, old):
        out: list[str] = []
        for alt in re.findall(r'[A-Za-z][A-Za-z &]+', old.DSO_TITLE_REGEX.pattern):
            alt = alt.strip()
            if 4 <= len(alt) <= 30:
                out.append(alt)
        return out[:8]

    def test_each_migration_is_equivalent(self):
        outreach_root = Path(__file__).resolve().parent.parent
        for new_slug, old_name in MIGRATIONS:
            with self.subTest(slug=new_slug):
                old = _load_old(old_name)
                if not (outreach_root / 'campaigns' / new_slug / 'campaign.yaml').exists():
                    self.skipTest(f'campaign {new_slug} not yet built')
                new = load_campaign(new_slug)
                self._assert_equivalent(new, old)


if __name__ == '__main__':
    unittest.main()
