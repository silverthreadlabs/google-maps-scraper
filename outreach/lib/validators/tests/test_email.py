"""Tests for outreach.lib.validators.email (stdlib unittest, no deps)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.validators.email import validate_email


VALID = [
    'info@emergencydentistofaustin.com',
    'sierrafo@skydentalaz.com',
    'info@ficdentistry.com',
    'dentalspecialtyphoenix@gmail.com',  # gmail with a real practice prefix
    'admin@stpetemoderndentistry.com',
    'amanda@westlakesmiles.com',
    'info@toothbar.com',
    'fadi.raffoul@ficdentistry.com',
]

INVALID_PLACEHOLDER = [
    'user@domain.com',
    'example@gmail.com',
    'sample@gmail.com',
    'test@example.com',
    'demo@yourdomain.com',
    'name@email.com',
    'someone@example.com',
    'placeholder@gmail.com',
]

INVALID_IMAGE = [
    'fancybox_sprite@2x.png',
    'logo@3x.svg',
    'icon@2x.jpeg',
]

INVALID_VENDOR = [
    'webreporting@gargle.com',
    'contact@officite.com',
    'support@rola.com',
    'preston@metapv.co',
    'dcpflugerville@mydentalmail.com',
    'noreply@wixpress.com',  # wix subdomain via vendor parent — not in our list, expect fall-through
]

INVALID_NOREPLY = [
    'no-reply@example-dental.com',
    'noreply@toothbar.com',
    'do-not-reply@dental.com',
    'donotreply@practice.com',
    'postmaster@dental.com',
]

INVALID_MALFORMED = [
    '',
    None,
    'not-an-email',
    'foo@',
    '@bar.com',
    'foo@bar',
]


class TestEmailValidity(unittest.TestCase):
    def test_valid(self):
        for e in VALID:
            with self.subTest(email=e):
                ok, reason = validate_email(e)
                self.assertTrue(ok, f"expected valid, got reason={reason}")
                self.assertIsNone(reason)

    def test_placeholder(self):
        for e in INVALID_PLACEHOLDER:
            with self.subTest(email=e):
                ok, reason = validate_email(e)
                self.assertFalse(ok)
                self.assertEqual(reason, 'placeholder')

    def test_image_artifact(self):
        for e in INVALID_IMAGE:
            with self.subTest(email=e):
                ok, reason = validate_email(e)
                self.assertFalse(ok)
                self.assertEqual(reason, 'image_artifact')

    def test_vendor_domains(self):
        # Test only entries with vendor domains we explicitly listed.
        for e in ['webreporting@gargle.com', 'contact@officite.com', 'support@rola.com',
                  'preston@metapv.co', 'dcpflugerville@mydentalmail.com']:
            with self.subTest(email=e):
                ok, reason = validate_email(e)
                self.assertFalse(ok, f"expected vendor reject for {e}")
                self.assertEqual(reason, 'vendor_marketing')

    def test_no_reply(self):
        for e in INVALID_NOREPLY:
            with self.subTest(email=e):
                ok, reason = validate_email(e)
                self.assertFalse(ok)
                self.assertEqual(reason, 'no_reply')

    def test_malformed(self):
        for e in INVALID_MALFORMED:
            with self.subTest(email=e):
                ok, reason = validate_email(e)
                self.assertFalse(ok)
                self.assertEqual(reason, 'malformed')


if __name__ == '__main__':
    unittest.main(verbosity=2)
