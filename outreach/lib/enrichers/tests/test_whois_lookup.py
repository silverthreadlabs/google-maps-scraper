"""Tests for lib.enrichers.whois_lookup."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.enrichers.whois_lookup import lookup_domain


class _FakeWhoisRecord:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class TestWhoisHappyPath(unittest.TestCase):
    def test_unredacted_record_returns_registrant_name_and_email(self):
        fake = _FakeWhoisRecord(
            name='John Smith',
            org='Smith Family Dental',
            emails='john@smithfamilydental.com',
            registrar='GoDaddy',
        )
        with patch('lib.enrichers.whois_lookup.whois.whois', return_value=fake):
            result = lookup_domain('smithfamilydental.com')
        self.assertEqual(result['registrant_name'], 'John Smith')
        self.assertEqual(result['registrant_email'], 'john@smithfamilydental.com')
        self.assertEqual(result['registrant_org'], 'Smith Family Dental')
        self.assertEqual(result['status'], 'ok')


class TestWhoisRedacted(unittest.TestCase):
    def test_redacted_record_returns_status_redacted(self):
        fake = _FakeWhoisRecord(
            name='REDACTED FOR PRIVACY',
            org='Privacy service provided by Withheld for Privacy',
            emails='abuse@withheldforprivacy.com',
        )
        with patch('lib.enrichers.whois_lookup.whois.whois', return_value=fake):
            result = lookup_domain('smithfamilydental.com')
        self.assertEqual(result['status'], 'redacted')
        self.assertIsNone(result['registrant_name'])
        self.assertIsNone(result['registrant_email'])

    def test_redacted_when_name_is_none_and_email_is_privacy_service(self):
        fake = _FakeWhoisRecord(name=None, org=None, emails='proxy@registrar.com')
        with patch('lib.enrichers.whois_lookup.whois.whois', return_value=fake):
            result = lookup_domain('foo.example')
        self.assertEqual(result['status'], 'redacted')


if __name__ == '__main__':
    unittest.main()
