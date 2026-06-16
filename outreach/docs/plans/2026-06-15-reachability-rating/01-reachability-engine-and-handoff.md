---
node: 01-reachability-engine-and-handoff
feature: reachability-rating
depends_on: []
owns:
  - lib/reachability.py
  - lib/ranking.py
  - lib/handoff/**
spec: docs/specs/2026-06-15-reachability-rating.md
adrs: [DDD-0001]
---

# Reachability engine + ranking + handoff — Implementation Plan

> **For auto-pipeline:** This node is the input to Phase 1. Load `CONTEXT.md` and `docs/adr/0001-blended-service-fit-reachability-rating.md` alongside it.
> **ADR references:** DDD-0001

**Goal:** Compute a 0–50 reachability sub-score from per-person contact data, blend it with a 0–50-normalized service-fit half into a 0–100 grade, and surface that grade plus its sub-scores in the sales handoff CSV.

**Architecture:** A new industry-agnostic `lib/reachability.py` unifies `pocs[]` and lead-level owner/OSINT contact fields into one usable-contact list, detects qualifying channels, picks the best-reachable representative POC, and returns a 0–50 score. `lib/ranking.py` gains `service_fit_norm`, a `blended_tier` for the 0–100 scale, and a single `score_lead` entry point. `lib/handoff/csv_builder.py` computes the blended grade authoritatively at output time and emits the new columns. Existing `ranking.tier` / `ranking.quality_score` are left untouched so no current stage test breaks.

**Tech Stack:** Python 3.11, `unittest` (run each test file directly: `python lib/<test>.py`), per `TDD-RULES.md`.

**Calibration constants (validated against the 5,237-lead corpus — A=14 / B=170 / C=218):**
`W_LINKEDIN=30`, `W_EMAIL=18`, `W_SOCIAL=8`, `W_MULTI=10`, `NO_CHANNEL_MULTI_CAP=3`, `REACH_CAP=50`, `POC_MIN_CONFIDENCE=0.30`, `FIT_FULL=60`, tiers `A≥75 / B≥50 / C≥25`.

> **D1 (2026-06-15, implementation refinement):** when no usable POC carries a reachable channel, the multi-POC boost is capped at `NO_CHANNEL_MULTI_CAP=3` (not the full ~10). Added during node-01 Phase 7 after review surfaced that 2+ named-but-unreachable contacts could otherwise score 5–10 reachability and flip a lead C→B with an empty channels column. See `reachability_score` and `test_channel_less_contacts_capped_at_three`. Spec Q9 + DDD-0001 updated.

---

### Task 1: Reachability scorer

**Files:**
- Create: `lib/reachability.py`
- Test: `lib/test_reachability.py`

- [x] **Step 1: Write the failing test**
```python
"""Tests for reachability — channel detection, representative-POC selection,
the no-double-count rule, and the lead-level contact fold."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.reachability import (
    is_personal_linkedin, is_reachable_email, is_personal_social,
    usable_contacts, reachability_score,
    W_LINKEDIN, W_EMAIL, W_SOCIAL, W_MULTI, REACH_CAP,
)


class TestChannelDetectors(unittest.TestCase):
    def test_personal_linkedin_only_in_profiles(self):
        self.assertTrue(is_personal_linkedin('https://www.linkedin.com/in/jane-doe-123'))
        self.assertFalse(is_personal_linkedin('https://linkedin.com/company/acme'))
        self.assertFalse(is_personal_linkedin(''))
        self.assertFalse(is_personal_linkedin(None))

    def test_reachable_email_rejects_role_mailboxes(self):
        for ok in ('john-doe@acme.com', 'jdoe@gmail.com', 'j.smith@firm.io'):
            self.assertTrue(is_reachable_email(ok), ok)
        for bad in ('info@acme.com', 'contact@acme.com', 'sales.team@acme.com',
                    'office@x.com', 'not-an-email', '', None):
            self.assertFalse(is_reachable_email(bad), bad)

    def test_personal_social_excludes_business_pages(self):
        self.assertTrue(is_personal_social('https://facebook.com/john.doe.5', 'Acme Tires'))
        self.assertTrue(is_personal_social('https://instagram.com/janedoe', 'Acme Tires'))
        # business's own page (handle ~ business name) is not a POC social
        self.assertFalse(is_personal_social('https://www.facebook.com/AcmeTires', 'Acme Tires'))
        self.assertFalse(is_personal_social('https://facebook.com/pages/Acme/123', 'Acme'))
        # linkedin is scored separately, never via this detector
        self.assertFalse(is_personal_social('https://linkedin.com/in/x', 'Acme'))


class TestUsableContacts(unittest.TestCase):
    def test_excludes_invalid_and_low_confidence(self):
        lead = {'title': 'Acme', 'pocs': [
            {'name': 'Real', 'confidence': 0.7, 'socials': [], 'email': None},
            {'name': 'Badge', 'confidence': 0.1, 'socials': [], 'email': None},
            {'name': 'Flagged', 'invalid': True, 'confidence': 0.9, 'socials': [], 'email': None},
        ]}
        names = [c.name for c in usable_contacts(lead)]
        self.assertEqual(names, ['Real'])

    def test_folds_lead_level_owner_linkedin_with_no_matching_poc(self):
        # owner-research writes owner_linkedin at the LEAD level; it must count
        # even when there is no pocs[] entry for that person.
        lead = {'title': 'Acme', 'owner_name': 'Pat Lee',
                'owner_linkedin': 'https://linkedin.com/in/patlee'}
        cs = usable_contacts(lead)
        self.assertEqual(len(cs), 1)
        self.assertTrue(cs[0].has_linkedin)

    def test_folds_lead_level_channels_into_matching_poc(self):
        lead = {'title': 'Acme',
                'pocs': [{'name': 'Pat Lee', 'confidence': 0.7, 'socials': [], 'email': None}],
                'owner_name': 'Pat Lee', 'owner_linkedin': 'https://linkedin.com/in/patlee'}
        cs = usable_contacts(lead)
        self.assertEqual(len(cs), 1)            # not duplicated
        self.assertTrue(cs[0].has_linkedin)


class TestReachabilityScore(unittest.TestCase):
    def _lead(self, pocs):
        return {'title': 'Acme', 'pocs': pocs}

    def test_no_contacts_scores_zero(self):
        score, bd = reachability_score({'title': 'Acme'})
        self.assertEqual(score, 0.0)
        self.assertEqual(bd['usable_poc_count'], 0)

    def test_single_poc_linkedin(self):
        score, bd = reachability_score(self._lead(
            [{'name': 'A', 'confidence': 0.9, 'socials': ['https://linkedin.com/in/a'], 'email': None}]))
        self.assertEqual(score, W_LINKEDIN)            # 30, no multi (n=1)
        self.assertEqual(bd['channels'], ['linkedin'])

    def test_channels_stack_within_one_poc_then_cap(self):
        score, _ = reachability_score(self._lead(
            [{'name': 'A', 'confidence': 0.9,
              'socials': ['https://linkedin.com/in/a', 'https://instagram.com/a_personal'],
              'email': 'a.person@firm.com'}]))
        # 30 + 18 + 8 = 56 -> capped at 50 (single POC, no multi)
        self.assertEqual(score, REACH_CAP)

    def test_no_double_count_socials_across_pocs(self):
        # B-1 example: P1 and P2 each have personal socials. Only one POC's
        # socials are credited (W_SOCIAL); the second contributes ONLY via the
        # capped multi-POC boost — never a second W_SOCIAL.
        score, bd = reachability_score(self._lead([
            {'name': 'P1', 'confidence': 0.9,
             'socials': ['https://instagram.com/p1', 'https://facebook.com/p1.personal'], 'email': None},
            {'name': 'P2', 'confidence': 0.9,
             'socials': ['https://instagram.com/p2'], 'email': None},
        ]))
        expected = W_SOCIAL + W_MULTI * (1 - 1/2)      # 8 + 5 = 13
        self.assertAlmostEqual(score, expected, places=2)
        self.assertNotAlmostEqual(score, W_SOCIAL * 2, places=2)  # NOT 16
        self.assertEqual(bd['usable_poc_count'], 2)

    def test_multi_poc_boost_diminishes_and_caps(self):
        def lead_n(n):
            return self._lead([{'name': f'P{i}', 'confidence': 0.9,
                                'socials': ['https://linkedin.com/in/p%d' % i], 'email': None}
                               for i in range(n)])
        s1, _ = reachability_score(lead_n(1))
        s2, _ = reachability_score(lead_n(2))
        s50, _ = reachability_score(lead_n(50))
        self.assertEqual(s1, W_LINKEDIN)                       # 30
        self.assertLess(s2 - s1, W_MULTI)                      # 2nd POC < full multi
        self.assertLessEqual(s50, REACH_CAP)                   # capped
        self.assertGreater(s50, s2)                            # but more is still more


if __name__ == '__main__':
    unittest.main(verbosity=2)
```

- [x] **Step 2: Run test to verify it fails**
Run: `python lib/test_reachability.py`
Expected: FAIL (ModuleNotFoundError: no `lib.reachability`)

- [x] **Step 3: Write minimal implementation**
```python
"""
Reachability scoring — industry-agnostic.

Measures how easily a decision-maker at a Lead can be reached, on a 0–50
scale, through PEOPLE (POCs) only — never through the business front door.
Business emails (info@…) and business socials (the company's own page) are
deliberately excluded.

Two parts (see DDD-0001):
  1. Representative-POC channel boost — the single best-reachable usable
     contact; channels stack (personal LinkedIn > directly-reachable email >
     personal social), priority via the weights below.
  2. Multi-POC boost — diminishing, capped: more usable contacts help, but the
     2nd matters most and a 50-name crawl artifact cannot dominate.

The per-channel credit comes from ONE representative POC (no-double-count
rule); extra POCs add only through the multi-POC boost.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

REACH_CAP = 50.0
W_LINKEDIN = 30.0
W_EMAIL = 18.0
W_SOCIAL = 8.0
W_MULTI = 10.0
POC_MIN_CONFIDENCE = 0.30   # mirror the bar sales sees in the handoff CSV

# Role / front-door mailbox local-parts that do NOT reach a specific person.
GENERIC_MAILBOXES = frozenset({
    'info', 'contact', 'sales', 'admin', 'hello', 'office', 'team', 'support',
    'service', 'help', 'mail', 'inquiries', 'enquiries', 'reception',
    'frontdesk', 'booking', 'appointments', 'general', 'marketing', 'careers',
    'jobs', 'hr', 'billing', 'accounts', 'noreply', 'no-reply',
})
_SOCIAL_DOMAINS = ('facebook.com', 'instagram.com', 'twitter.com', 'x.com',
                   'tiktok.com', 'youtube.com')


def is_personal_linkedin(url: str | None) -> bool:
    return 'linkedin.com/in/' in (url or '').lower()


def is_reachable_email(email: str | None) -> bool:
    e = (email or '').strip().lower()
    if '@' not in e:
        return False
    local = e.split('@', 1)[0]
    base = re.split(r'[._\-+]', local)[0]
    return local not in GENERIC_MAILBOXES and base not in GENERIC_MAILBOXES


def is_personal_social(url: str | None, business_name: str = '') -> bool:
    """Strict: a personal social profile, not the business's own page.
    LinkedIn is scored separately, so it never counts here."""
    u = (url or '').lower()
    if not u or 'linkedin.com' in u:
        return False
    if not any(d in u for d in _SOCIAL_DOMAINS):
        return False
    if '/pages/' in u or '/company/' in u:
        return False
    biz = re.sub(r'[^a-z0-9]', '', (business_name or '').lower())
    handle = re.sub(r'^https?://', '', u).split('?')[0].rstrip('/').split('/')[-1]
    h = re.sub(r'[^a-z0-9]', '', handle)
    if biz and len(biz) >= 4 and (biz in h or h in biz):
        return False
    return True


@dataclass
class Contact:
    name: str
    has_linkedin: bool
    has_email: bool
    has_social: bool

    def boost(self) -> float:
        return (W_LINKEDIN * self.has_linkedin
                + W_EMAIL * self.has_email
                + W_SOCIAL * self.has_social)


def usable_contacts(lead: dict) -> list[Contact]:
    """Unify pocs[] with the lead-level owner/OSINT contact fields into one
    list of usable contacts (not invalid, confidence ≥ POC_MIN_CONFIDENCE or
    unscored). Lead-level channels fold into a matching pocs[] entry by name,
    else become their own contact — so an owner_linkedin written by the
    owner-research stage counts even with no pocs[] row."""
    biz = lead.get('title') or ''
    contacts: list[Contact] = []
    for p in (lead.get('pocs') or []):
        if not isinstance(p, dict) or p.get('invalid') or not (p.get('name') or '').strip():
            continue
        c = p.get('confidence')
        if c is not None and c < POC_MIN_CONFIDENCE:
            continue
        socials = p.get('socials') or []
        contacts.append(Contact(
            name=p['name'].strip(),
            has_linkedin=any(is_personal_linkedin(s) for s in socials),
            has_email=is_reachable_email(p.get('email')),
            has_social=any(is_personal_social(s, biz) for s in socials),
        ))

    def fold(name: str | None, linkedin_url: str | None, email: str | None) -> None:
        li = is_personal_linkedin(linkedin_url)
        em = is_reachable_email(email)
        name = (name or '').strip()
        if not (name or li or em):
            return
        if name:
            for c in contacts:
                if c.name.lower() == name.lower():
                    c.has_linkedin = c.has_linkedin or li
                    c.has_email = c.has_email or em
                    return
        contacts.append(Contact(name=name or '(owner)', has_linkedin=li,
                                has_email=em, has_social=False))

    fold(lead.get('owner_name'), lead.get('owner_linkedin'), lead.get('owner_email'))
    fold(lead.get('poc_name'), lead.get('linkedin_url_poc'), lead.get('poc_email'))
    return contacts


def reachability_score(lead: dict) -> tuple[float, dict]:
    """Return (score 0–50, breakdown). Breakdown carries the representative
    contact's name, the channels credited, and the usable-POC count."""
    contacts = usable_contacts(lead)
    if not contacts:
        return 0.0, {'usable_poc_count': 0, 'representative': None, 'channels': []}
    rep = max(contacts, key=lambda c: c.boost())
    n = len(contacts)
    multi = W_MULTI * (1 - 1.0 / n)
    score = min(REACH_CAP, rep.boost() + multi)
    channels = [k for k, v in (('linkedin', rep.has_linkedin),
                               ('email', rep.has_email),
                               ('social', rep.has_social)) if v]
    return round(score, 2), {'usable_poc_count': n, 'representative': rep.name,
                             'channels': channels}
```

- [x] **Step 4: Run test to verify it passes**
Run: `python lib/test_reachability.py`
Expected: PASS

---

### Task 2: Ranking integration — normalize fit, blend, tier

**Files:**
- Modify: `lib/ranking.py` (add to the existing module; do NOT change `tier` or `quality_score`)
- Test: `lib/test_ranking.py`

- [x] **Step 1: Write the failing test**
```python
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
```

- [x] **Step 2: Run test to verify it fails**
Run: `python lib/test_ranking.py`
Expected: FAIL (ImportError: cannot import `service_fit_norm`)

- [x] **Step 3: Write minimal implementation**
Append to `lib/ranking.py` (keep the existing `tier` and `quality_score` exactly as-is):
```python
from lib.reachability import reachability_score

FIT_FULL = 60.0  # raw service-fit at/above which the fit half saturates at 50


def service_fit_norm(raw_fit: float | None, *, fit_full: float = FIT_FULL) -> float:
    """Map the open-ended raw service-fit score onto 0–50: linear below
    `fit_full`, capped at 50 above. See DDD-0001."""
    if raw_fit is None:
        return 0.0
    return round(min(1.0, max(0.0, raw_fit) / fit_full) * 50.0, 2)


def blended_tier(quality_score: float | None) -> Tier:
    """Tier on the blended 0–100 scale (DDD-0001). Distinct from `tier`,
    which still bins the legacy open-ended scale until stages migrate."""
    if quality_score is None:
        return 'unranked'
    if quality_score >= 75:
        return 'A'
    if quality_score >= 50:
        return 'B'
    if quality_score >= 25:
        return 'C'
    return 'D'


def score_lead(lead: dict, *, pain_weights: dict[str, int]) -> dict:
    """Single entry point for the blended rating. Reads the lead's pain,
    reviews, and contact data; returns the fields to merge onto the lead:
    raw + normalized service-fit, reachability + breakdown, blended
    quality_score (0–100), and blended tier."""
    pain = lead.get('agent_pain_hits') or lead.get('pain_hits') or {}
    rating = lead.get('rating', lead.get('review_rating')) or 0.0
    raw_fit, weighted, breadth = quality_score(
        pain, lead.get('review_count') or 0, rating, pain_weights=pain_weights,
    )
    fit = service_fit_norm(raw_fit)
    reach, breakdown = reachability_score(lead)
    blended = round(fit + reach, 2)
    return {
        'service_fit_raw': raw_fit,
        'service_fit_score': fit,
        'reachability_score': reach,
        'reachability_breakdown': breakdown,
        'weighted_pain': weighted,
        'pain_breadth': breadth,
        'quality_score': blended,
        'tier': blended_tier(blended),
    }
```

- [x] **Step 4: Run test to verify it passes**
Run: `python lib/test_ranking.py`
Expected: PASS

---

### Task 3: Surface the blended grade in the handoff CSV

**Files:**
- Modify: `lib/handoff/csv_builder.py` (`tier` → delegate, `FIELDNAMES`, `_backfill_quality_score` → authoritative recompute, `_build_row`, `build_handoff` sort)
- Test: `lib/handoff/tests/test_csv_builder.py` (add a new test class; existing tests untouched)

- [x] **Step 1: Write the failing test**
Append this class to `lib/handoff/tests/test_csv_builder.py`:
```python
import csv as _csv
import json as _json
import tempfile
from pathlib import Path as _Path
from lib.handoff.csv_builder import build_handoff


class TestBlendedReachabilityInHandoff(unittest.TestCase):
    PW = {'p': 58}   # weighted+breadth*2 = 60 raw -> fit_norm 50

    def _run(self, leads):
        d = _Path(tempfile.mkdtemp())
        (d / 'master.json').write_text(_json.dumps(leads))
        build_handoff(input_path=d / 'master.json', output_path=d / 'h.csv',
                      service_map={}, pain_weights=self.PW)
        with open(d / 'h.csv') as f:
            return list(_csv.DictReader(f))

    def _maxfit(self, **extra):
        l = {'title': 'Acme', 'agent_pain_hits': {'p': [{}]},
             'review_count': 1, 'rating': 5.0}
        l.update(extra)
        return l

    def test_new_columns_present(self):
        for col in ('service_fit_score', 'reachability_score',
                    'reachability_representative', 'reachability_channels',
                    'usable_poc_count'):
            self.assertIn(col, FIELDNAMES)

    def test_reachable_lead_outranks_equal_fit_unreachable_lead(self):
        rows = self._run([
            self._maxfit(title='Unreachable'),
            self._maxfit(title='Reachable', pocs=[
                {'name': 'O', 'confidence': 0.9,
                 'socials': ['https://linkedin.com/in/o'], 'email': None}]),
        ])
        self.assertEqual(rows[0]['title'], 'Reachable')      # sorted first
        self.assertEqual(rows[0]['tier'], 'A')
        self.assertEqual(rows[0]['quality_score'], '80.0')
        self.assertEqual(rows[0]['reachability_channels'], 'linkedin')
        # unreachable max-fit caps at tier B
        unreachable = next(r for r in rows if r['title'] == 'Unreachable')
        self.assertEqual(unreachable['tier'], 'B')
        self.assertEqual(unreachable['reachability_score'], '0.0')
```

- [x] **Step 2: Run test to verify it fails**
Run: `python lib/handoff/tests/test_csv_builder.py`
Expected: FAIL (`reachability_score` not in `FIELDNAMES`; columns/sort not implemented)

- [x] **Step 3: Write minimal implementation**
In `lib/handoff/csv_builder.py`:

(a) Replace the local `tier` function (lines ~78–84) with a delegation and import `score_lead`:
```python
from lib.url_normalize import normalize_url
from lib.ranking import score_lead, blended_tier as tier
```
…and delete the local `def tier(q): …` block (now imported).

(b) Add the new columns to `FIELDNAMES`, right after `'tier', 'quality_score',`:
```python
    'tier', 'quality_score', 'service_fit_score', 'reachability_score',
    'reachability_representative', 'reachability_channels', 'usable_poc_count',
    'metro', 'title',
```
(remove the old `'tier', 'quality_score', 'metro', 'title',` line it replaces).

(c) Replace `_backfill_quality_score` (lines ~313–326) with an authoritative recompute — it now always blends, so the CSV reflects all enrichment present on the final master:
```python
def _score_lead_for_handoff(l: dict, pain_weights: dict) -> None:
    """Compute the blended grade authoritatively at output time (DDD-0001).
    Master.json may still carry the legacy raw quality_score until the
    eager-recompute node lands; the handoff is the source of truth for the
    delivered grade."""
    l.update(score_lead(l, pain_weights=pain_weights))
```

(d) In `_build_row`, add the breakdown columns to the `row` dict (next to `'quality_score'`):
```python
        'quality_score': l.get('quality_score'),
        'service_fit_score': l.get('service_fit_score'),
        'reachability_score': l.get('reachability_score'),
        'reachability_representative': (l.get('reachability_breakdown') or {}).get('representative') or '',
        'reachability_channels': ';'.join((l.get('reachability_breakdown') or {}).get('channels') or []),
        'usable_poc_count': (l.get('reachability_breakdown') or {}).get('usable_poc_count', 0),
```

(e) In `build_handoff`, swap the backfill loop and add `service_fit_raw` as the sort tiebreaker:
```python
    for l in rows:
        _score_lead_for_handoff(l, pain_weights)

    rows.sort(key=lambda x: (x.get('is_chain_or_dso', False),
                             -(x.get('quality_score') or 0),
                             -(x.get('service_fit_raw') or 0)))
```

- [x] **Step 4: Run the full handoff test file to verify pass + no regression**
Run: `python lib/handoff/tests/test_csv_builder.py`
Expected: PASS (new class passes; all pre-existing pain/email/POC/URL tests still pass)

---

### Task 4: Confirm the whole node is green

- [x] **Step 1: Run the three touched test files**
Run:
```bash
python lib/test_reachability.py
python lib/test_ranking.py
python lib/handoff/tests/test_csv_builder.py
```
Expected: all PASS.

- [x] **Step 2: Confirm no other test regressed from the new imports**
Run the repo suite (per `CLAUDE.md` Workflow):
```bash
for t in $(find lib tests -name 'test_*.py' -o -name '*_tests.py' 2>/dev/null); do echo "== $t"; python "$t" 2>&1 | tail -2; done
```
Expected: no new failures. (Existing stage tests still pass because `ranking.tier` / `ranking.quality_score` are unchanged; only new symbols were added.)

---

## Commit Strategy

Reviewed as one diff, then committed in the final git phase via `conventional-commits`. Group by logical change:

1. `feat(ranking): add reachability scorer and blended 0–100 rating` — `lib/reachability.py`, the `lib/ranking.py` additions (`service_fit_norm`, `blended_tier`, `score_lead`), and their tests (`lib/test_reachability.py`, `lib/test_ranking.py`).
2. `feat(handoff): surface blended grade + reachability sub-scores in the CSV` — `lib/handoff/csv_builder.py` changes and the new `test_csv_builder.py` class.
3. `docs: spec, ADR, glossary, and plan for blended reachability rating` — `CONTEXT.md`, `docs/adr/0000-template.md`, `docs/adr/0001-*.md`, `docs/specs/2026-06-15-reachability-rating.md`, `docs/plans/2026-06-15-reachability-rating/**`, `docs/plans/DEFERRED.md`.

No commits happen during implementation; the whole node stays uncommitted until the final git phase.
