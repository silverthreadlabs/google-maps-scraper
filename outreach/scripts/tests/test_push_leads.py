"""Tests for scripts/push_leads — lead transformation and bulk import."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.push_leads import (
    _build_emails,
    _build_pocs,
    _build_reviews_payload,
    _build_socials,
    _flatten_pain_hits,
    _pick_best_email,
    transform_lead,
)

PAIN_WEIGHTS = {
    'calls_unanswered': 5,
    'booking_friction': 4,
    'frontline_communication': 2,
}

SERVICE_MAP = {
    'calls_unanswered': ('Voice AI Agents', 'silverthreadlabs.com/voice'),
    'booking_friction': ('Voice AI Booking', 'silverthreadlabs.com/booking'),
}


def _make_lead(**overrides):
    base = {
        'place_id': 'ChIJ_test123',
        'title': 'Test Dental',
        'link': 'https://maps.google.com/test',
        'website': 'https://testdental.com',
        'phone': '+1 512-555-1234',
        'address': '123 Main St, Austin, TX',
        'emails': ['info@testdental.com'],
        'emails_source': ['gosom_scraper'],
        'crawled_emails': ['contact@testdental.com'],
        'crawled_emails_source': ['agent_browser_crawl'],
        'category': 'Dentist',
        'metro': 'austin',
        'is_chain_or_dso': False,
        'chain_reason': None,
        'rating': 4.5,
        'review_count': 200,
        'reviews_analyzed': 150,
        'negative_reviews_1_3_star': 10,
        'quality_score': 65.0,
        'tier': 'A',
        'socials': ['https://facebook.com/testdental'],
        'crawled_socials': ['https://instagram.com/testdental'],
        'pain_hits': {},
        'agent_pain_hits': {
            'calls_unanswered': [
                {
                    'sub': 'phone_not_answered',
                    'confidence': 0.9,
                    'snippet': 'Called three times and nobody answered.',
                    'rating': 1,
                    'reviewer': 'Jane Doe',
                    'matched': 'called',
                },
            ],
            'booking_friction': [
                {
                    'sub': 'online_booking_broken',
                    'confidence': 0.8,
                    'snippet': 'Their online booking was down.',
                    'rating': 2,
                    'reviewer': 'John Smith',
                    'matched': 'booking',
                },
            ],
        },
        'pocs': [
            {'name': 'Dr. Smith', 'role': 'Owner', 'email': 'smith@test.com', 'socials': None, 'url': None},
            {'name': 'About Us', 'role': None, 'email': None, 'invalid': True, 'invalid_reason': 'heading'},
        ],
        'owner_name': 'Dr. Smith',
        'owner_title': 'DDS',
        'owner_linkedin': 'https://linkedin.com/in/drsmith',
        'additional_team': ['Nurse Jane'],
    }
    base.update(overrides)
    return base


class TestPickBestEmail(unittest.TestCase):
    def test_picks_first_trustworthy(self):
        lead = _make_lead()
        best = _pick_best_email(lead)
        self.assertEqual(best, 'info@testdental.com')

    def test_empty_when_no_emails(self):
        lead = _make_lead(emails=[], crawled_emails=[])
        self.assertEqual(_pick_best_email(lead), '')


class TestBuildEmails(unittest.TestCase):
    def test_merges_gosom_and_crawled(self):
        lead = _make_lead()
        result = _build_emails(lead)
        emails_only = [e['email'] for e in result]
        self.assertIn('info@testdental.com', emails_only)
        self.assertIn('contact@testdental.com', emails_only)

    def test_marks_best(self):
        lead = _make_lead()
        result = _build_emails(lead)
        best_entries = [e for e in result if e['is_best']]
        self.assertEqual(len(best_entries), 1)
        self.assertEqual(best_entries[0]['email'], 'info@testdental.com')

    def test_dedupes(self):
        lead = _make_lead(
            emails=['dup@test.com', 'DUP@test.com'],
            crawled_emails=['dup@test.com'],
        )
        result = _build_emails(lead)
        self.assertEqual(len(result), 1)

    def test_caps_at_50(self):
        emails = [f'e{i}@test.com' for i in range(60)]
        lead = _make_lead(emails=emails, crawled_emails=[])
        result = _build_emails(lead)
        self.assertLessEqual(len(result), 50)


class TestFlattenPainHits(unittest.TestCase):
    def test_flattens_agent_pain_hits(self):
        lead = _make_lead()
        result = _flatten_pain_hits(lead)
        self.assertEqual(len(result), 2)
        cats = {h['category'] for h in result}
        self.assertEqual(cats, {'calls_unanswered', 'booking_friction'})

    def test_empty_when_no_pain(self):
        lead = _make_lead(agent_pain_hits={}, pain_hits={})
        self.assertEqual(_flatten_pain_hits(lead), [])

    def test_caps_at_200(self):
        large_pain = {'cat': [{'snippet': f's{i}', 'rating': 1} for i in range(250)]}
        lead = _make_lead(agent_pain_hits=large_pain)
        result = _flatten_pain_hits(lead)
        self.assertLessEqual(len(result), 200)


class TestBuildReviewsPayload(unittest.TestCase):
    def test_transforms_review_fields(self):
        reviews = [
            {'reviewer': 'Alice', 'text': 'Great service!', 'rating': 5},
            {'reviewer': 'Bob', 'text': 'Terrible wait.', 'rating': 1},
        ]
        result = _build_reviews_payload(reviews)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['reviewer_name'], 'Alice')
        self.assertEqual(result[0]['description'], 'Great service!')

    def test_caps_at_500(self):
        reviews = [{'reviewer': f'R{i}', 'text': f'Text {i}', 'rating': 3} for i in range(600)]
        result = _build_reviews_payload(reviews)
        self.assertLessEqual(len(result), 500)


class TestBuildPocs(unittest.TestCase):
    def test_filters_invalid_pocs(self):
        lead = _make_lead()
        result = _build_pocs(lead)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'Dr. Smith')

    def test_empty_pocs(self):
        lead = _make_lead(pocs=[])
        self.assertEqual(_build_pocs(lead), [])


class TestBuildSocials(unittest.TestCase):
    def test_categorizes_socials(self):
        lead = _make_lead()
        result = _build_socials(lead)
        self.assertIn('facebook', result)
        self.assertIn('instagram', result)
        self.assertIn('facebook.com', result['facebook'])


class TestTransformLead(unittest.TestCase):
    def test_full_transform(self):
        lead = _make_lead()
        reviews_index = {
            'ChIJ_test123': [
                {'reviewer': 'Alice', 'text': 'Great!', 'rating': 5},
            ],
        }
        result = transform_lead(
            lead,
            reviews_index=reviews_index,
            pain_weights=PAIN_WEIGHTS,
            service_map=SERVICE_MAP,
        )
        self.assertEqual(result['place_id'], 'ChIJ_test123')
        self.assertEqual(result['title'], 'Test Dental')
        self.assertEqual(result['google_maps_link'], 'https://maps.google.com/test')
        self.assertGreater(len(result['emails']), 0)
        self.assertGreater(len(result['pain_hits']), 0)
        self.assertEqual(len(result['reviews']), 1)
        self.assertFalse(result['is_chain_or_dso'])

    def test_recommended_service_from_top_pain(self):
        lead = _make_lead()
        result = transform_lead(
            lead,
            reviews_index={},
            pain_weights=PAIN_WEIGHTS,
            service_map=SERVICE_MAP,
        )
        self.assertIn(result['recommended_service'], ['Voice AI Agents', 'Voice AI Booking'])

    def test_no_reviews_when_not_in_index(self):
        lead = _make_lead()
        result = transform_lead(
            lead,
            reviews_index={},
            pain_weights=PAIN_WEIGHTS,
            service_map=SERVICE_MAP,
        )
        self.assertEqual(result['reviews'], [])


if __name__ == '__main__':
    unittest.main()
