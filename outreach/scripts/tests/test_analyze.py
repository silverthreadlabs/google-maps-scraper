"""Tests for scripts/analyze."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.analyze import (
    analyze,
    build_lead,
    dedupe_by_place_id,
    main as analyze_main,
    merge_reviews,
    partition_emails,
    write_atomic,
)


PAIN_WEIGHTS = {'calls_unanswered': 5, 'booking_friction': 4}
DSO_TITLE_REGEX = re.compile(r'\b(Aspen Dental|Sono Bello)\b', re.I)
DSO_EMAIL_DOMAINS = {'aspendental.com'}
GEOGRAPHIC_PREFIXES = {'dallas', 'plano'}


def _raw(**kw):
    """Minimal raw-row factory."""
    base = {
        'place_id': 'p1',
        'title': 'Acme Plastic Surgery',
        'web_site': 'https://acme.example.com/',
        'phone': '+1 555-555-1234',
        'address': '1 Main St, Dallas, TX',
        'category': 'Plastic surgeon',
        'review_count': 100,
        'review_rating': 4.5,
        'emails': [],
        'user_reviews': [],
        'user_reviews_extended': [],
    }
    base.update(kw)
    return base


# ─── partition_emails ─────────────────────────────────────────────────────

class TestPartitionEmails(unittest.TestCase):
    def test_image_artifacts_routed_to_invalid(self):
        # CLAUDE.md rule 1: never drop. Bad emails get a sibling reason,
        # never silently disappear — even at ingest.
        valid, invalid = partition_emails([
            'real@drburns.com', 'foo@2x.png', 'bar@3x.jpg',
        ])
        self.assertEqual(valid, ['real@drburns.com'])
        self.assertEqual(len(invalid), 2)
        self.assertEqual(invalid[0]['reason'], 'image_artifact')

    def test_placeholder_routed_to_invalid(self):
        valid, invalid = partition_emails(['your@email.com', 'real@office.com'])
        self.assertEqual(valid, ['real@office.com'])
        self.assertEqual(invalid[0]['email'], 'your@email.com')
        self.assertEqual(invalid[0]['reason'], 'placeholder')

    def test_dedupes_case_insensitively(self):
        valid, invalid = partition_emails(['Real@Drburns.com', 'real@drburns.com'])
        self.assertEqual(len(valid), 1)
        self.assertEqual(invalid, [])

    def test_extra_vendor_domain_rejected(self):
        valid, invalid = partition_emails(
            ['hello@vendor.example'],
            extra_vendor_domains=frozenset({'vendor.example'}),
        )
        self.assertEqual(valid, [])
        self.assertEqual(invalid[0]['reason'], 'vendor_marketing')

    def test_skips_blank_and_non_string(self):
        valid, invalid = partition_emails(['', '   ', None, 'real@x.com'])
        self.assertEqual(valid, ['real@x.com'])
        self.assertEqual(invalid, [])


# ─── merge_reviews + dedupe_by_place_id ────────────────────────────────────

class TestMergeReviews(unittest.TestCase):
    def test_merges_both_review_fields_dedup_by_reviewer_and_text_prefix(self):
        raw = {
            'user_reviews': [
                {'description': 'Great place but waited too long', 'rating': '3', 'reviewer_name': 'Ann'},
            ],
            'user_reviews_extended': [
                {'Description': 'Great place but waited too long', 'Rating': '3', 'Name': 'Ann'},  # dup
                {'Description': 'Front desk was rude', 'Rating': '1', 'Name': 'Bob'},
            ],
        }
        out = merge_reviews(raw)
        self.assertEqual(len(out), 2)
        names = {r['reviewer'] for r in out}
        self.assertEqual(names, {'Ann', 'Bob'})

    def test_skips_empty_text(self):
        raw = {'user_reviews': [{'description': '', 'rating': '1', 'reviewer_name': 'X'}]}
        self.assertEqual(merge_reviews(raw), [])


class TestDedupeByPlaceId(unittest.TestCase):
    def test_drops_rows_without_place_id_keeps_first_occurrence(self):
        rows = [
            {'place_id': 'p1', 'title': 'A'},
            {'place_id': 'p1', 'title': 'A-dup'},
            {'place_id': 'p2', 'title': 'B'},
            {'title': 'no-pid'},
        ]
        out = dedupe_by_place_id(rows)
        self.assertEqual([r['title'] for r in out], ['A', 'B'])


# ─── build_lead / analyze ─────────────────────────────────────────────────

class TestBuildLead(unittest.TestCase):
    def _detector(self, leads):
        from lib.chain_detection import ChainDetector
        d = ChainDetector(
            title_dso_regex=DSO_TITLE_REGEX,
            dso_email_domains=DSO_EMAIL_DOMAINS,
            geographic_prefixes=GEOGRAPHIC_PREFIXES,
        )
        d.fit(leads)
        return d

    def test_clean_lead_carries_provenance_and_score(self):
        leads = [_raw()]
        lead = build_lead(
            leads[0],
            chain_detector=self._detector(leads),
            pain_weights=PAIN_WEIGHTS,
            metro='dallas',
            extra_vendor_domains=frozenset(),
            now_iso='2026-05-01T00:00:00+00:00',
        )
        self.assertEqual(lead['place_id'], 'p1')
        self.assertEqual(lead['place_id_source'], 'gosom_scraper')
        self.assertEqual(lead['metro'], 'dallas')
        self.assertEqual(lead['emails'], [])
        self.assertNotIn('emails_invalid', lead)   # absent when nothing invalid
        self.assertEqual(lead['analyzed_at'], '2026-05-01T00:00:00+00:00')
        self.assertGreater(lead['quality_score'], 0)
        self.assertEqual(lead['tier'], 'D')        # no pain hits yet → low tier

    def test_invalid_emails_partition_at_ingest(self):
        # Image-artifact and placeholder addresses go to emails_invalid;
        # only the real one stays in `emails`. Source list mirrors filtered length.
        leads = [_raw(emails=[
            'real@drburns.com', 'shutterstock_x_1440x640@2x.jpg', 'your@email.com',
        ])]
        lead = build_lead(
            leads[0],
            chain_detector=self._detector(leads),
            pain_weights=PAIN_WEIGHTS,
            metro='dallas',
            extra_vendor_domains=frozenset(),
            now_iso='2026-05-01T00:00:00+00:00',
        )
        self.assertEqual(lead['emails'], ['real@drburns.com'])
        self.assertEqual(lead['emails_source'], ['gosom_scraper'])
        self.assertEqual(len(lead['emails_invalid']), 2)

    def test_known_dso_in_title_flags_chain(self):
        leads = [_raw(title='Aspen Dental of Plano')]
        lead = build_lead(
            leads[0],
            chain_detector=self._detector(leads),
            pain_weights=PAIN_WEIGHTS,
            metro='dallas',
            extra_vendor_domains=frozenset(),
            now_iso='2026-05-01T00:00:00+00:00',
        )
        self.assertTrue(lead['is_chain_or_dso'])
        self.assertEqual(lead['chain_reason'], 'known_dso')


class TestAnalyzeOrchestration(unittest.TestCase):
    def test_dedupes_sorts_and_emits_stats(self):
        raw_rows = [
            _raw(place_id='p1', title='Acme', review_count=100, review_rating=4.0),
            _raw(place_id='p1', title='Acme dup'),                                     # dropped
            _raw(place_id='p2', title='Brico Pharm', review_count=10, review_rating=4.9),
            {'title': 'no place_id'},                                                  # dropped
        ]
        master, stats = analyze(
            raw_rows,
            pain_weights=PAIN_WEIGHTS,
            dso_title_regex=DSO_TITLE_REGEX,
            dso_email_domains=DSO_EMAIL_DOMAINS,
            geographic_prefixes=GEOGRAPHIC_PREFIXES,
        )
        self.assertEqual(len(master), 2)
        self.assertEqual(stats['raw_rows'], 4)
        self.assertEqual(stats['unique_place_ids'], 2)
        # higher quality_score first (rating gap × 4 dominates here)
        self.assertGreaterEqual(master[0]['quality_score'], master[1]['quality_score'])


# ─── CLI integration ──────────────────────────────────────────────────────

class TestCli(unittest.TestCase):
    def _make_pipeline(self, tmpd: Path) -> Path:
        """Spin up a minimal `outreach/pipelines/<x>/` shape that
        load_pipeline_config can import. Returns the outreach root the test
        should add to sys.path."""
        outreach_root = tmpd / 'outreach'
        pipelines = outreach_root / 'pipelines'
        pdir = pipelines / 'test_pipeline'
        (pdir / 'raw').mkdir(parents=True)
        (pdir / 'outputs').mkdir()
        (pipelines / '__init__.py').write_text('')
        (pdir / '__init__.py').write_text('')
        (pdir / 'config.py').write_text(
            'import re\n'
            f'PAIN_WEIGHTS = {PAIN_WEIGHTS!r}\n'
            'DSO_TITLE_REGEX = re.compile(r"\\b(Aspen Dental)\\b", re.I)\n'
            'DSO_EMAIL_DOMAINS = {"aspendental.com"}\n'
            'GEOGRAPHIC_PREFIXES = {"dallas"}\n'
            'METROS = ["dallas"]\n'
        )
        # write 2 raw rows
        raw = pdir / 'raw' / 'test.json'
        rows = [_raw(place_id='pA', title='A'), _raw(place_id='pB', title='B')]
        raw.write_text('\n'.join(json.dumps(r) for r in rows))
        return outreach_root

    def test_cli_writes_master_under_outputs_date(self):
        with tempfile.TemporaryDirectory() as tmpd:
            outreach_root = self._make_pipeline(Path(tmpd))

            # Patch the OUTREACH_ROOT scripts._common resolved to so the
            # CLI talks to the temp pipeline. Easiest path: monkey-patch
            # both the constant and pipeline_dir's lookup base.
            from scripts import _common
            from scripts import analyze as analyze_mod
            saved_root = _common.OUTREACH_ROOT
            saved_paths = list(sys.path)
            _common.OUTREACH_ROOT = outreach_root
            sys.path.insert(0, str(outreach_root))
            try:
                rc = analyze_main(['test_pipeline', '--output-date', '2026-05-01'])
            finally:
                _common.OUTREACH_ROOT = saved_root
                sys.path[:] = saved_paths

            self.assertEqual(rc, 0)
            out = json.loads(
                (outreach_root / 'pipelines' / 'test_pipeline'
                 / 'outputs' / '2026-05-01' / 'master.json').read_text()
            )
            self.assertEqual(len(out), 2)
            self.assertEqual({l['place_id'] for l in out}, {'pA', 'pB'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
