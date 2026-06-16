"""Tests for the blended-rating additions to ranking: fit normalization,
the 0–100 blended tier, and the score_lead entry point."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.ranking import service_fit_norm, blended_tier, score_lead, FIT_FULL


class TestServiceFitNorm(unittest.TestCase):
    def test_linear_below_full_and_capped_above(self):
        self.assertEqual(service_fit_norm(0), 0.0)
        self.assertEqual(service_fit_norm(None), 0.0)
        self.assertEqual(service_fit_norm(FIT_FULL / 2), 25.0)
        self.assertEqual(service_fit_norm(FIT_FULL), 50.0)
        self.assertEqual(service_fit_norm(FIT_FULL * 5), 50.0)   # capped
        self.assertEqual(service_fit_norm(-10), 0.0)             # clamped


class TestBlendedTier(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(blended_tier(None), 'unranked')
        self.assertEqual(blended_tier(75), 'A')
        self.assertEqual(blended_tier(74.99), 'B')
        self.assertEqual(blended_tier(50), 'B')
        self.assertEqual(blended_tier(49.99), 'C')
        self.assertEqual(blended_tier(25), 'C')
        self.assertEqual(blended_tier(24.99), 'D')


class TestScoreLead(unittest.TestCase):
    # pain weight chosen so weighted+breadth*2 = 60 (raw fit) -> fit_norm = 50
    PW = {'p': 58}

    def _maxfit_lead(self, **extra):
        lead = {'title': 'Acme', 'agent_pain_hits': {'p': [{}]},
                'review_count': 1, 'rating': 5.0}
        lead.update(extra)
        return lead

    def test_unreachable_maxfit_lead_caps_at_B(self):
        lead = self._maxfit_lead()
        out = score_lead(lead, pain_weights=self.PW)
        self.assertEqual(out['service_fit_score'], 50.0)
        self.assertEqual(out['reachability_score'], 0.0)
        self.assertEqual(out['quality_score'], 50.0)
        self.assertEqual(out['tier'], 'B')               # never A without reach

    def test_reachable_maxfit_lead_reaches_A(self):
        lead = self._maxfit_lead(pocs=[
            {'name': 'Owner', 'confidence': 0.9,
             'socials': ['https://linkedin.com/in/owner'], 'email': None}])
        out = score_lead(lead, pain_weights=self.PW)
        self.assertEqual(out['reachability_score'], 30.0)
        self.assertEqual(out['quality_score'], 80.0)
        self.assertEqual(out['tier'], 'A')

    def test_keeps_raw_fit_as_tiebreaker(self):
        # two leads both saturate fit_norm at 50 but differ in raw fit
        a = score_lead(self._maxfit_lead(), pain_weights={'p': 200})
        b = score_lead(self._maxfit_lead(), pain_weights={'p': 58})
        self.assertEqual(a['service_fit_score'], b['service_fit_score'])  # both 50
        self.assertGreater(a['service_fit_raw'], b['service_fit_raw'])    # raw differs


if __name__ == '__main__':
    unittest.main(verbosity=2)
