"""Tests for outreach.lib.validators.email (stdlib unittest, no deps)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.validators.email import validate_email


# Dental-specific marketing/template vendors. In production these are
# supplied by pipelines/dental_sunbelt/config.py:VENDOR_DOMAINS_EXTRA;
# duplicating the set here keeps the validator test self-contained.
DENTAL_VENDOR_DOMAINS_EXTRA = frozenset({
    'gargle.com',
    'officite.com',
    'mydentalmail.com',
    'dentalqore.com',
    'progressivedental.com',
})


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

    def test_generic_vendor_domains(self):
        # Generic web-builder / SaaS / template — rejected without any
        # extra_vendor_domains argument.
        for e in ['support@rola.com', 'preston@metapv.co',
                  'team@hubspot.com', 'info@wix.com']:
            with self.subTest(email=e):
                ok, reason = validate_email(e)
                self.assertFalse(ok, f"expected vendor reject for {e}")
                self.assertEqual(reason, 'vendor_marketing')

    def test_vertical_specific_vendors_pass_when_no_extra_supplied(self):
        # Dental vendors are NOT in the lib default — without
        # extra_vendor_domains, they validate as real emails.
        for e in ['webreporting@gargle.com', 'contact@officite.com',
                  'dcpflugerville@mydentalmail.com']:
            with self.subTest(email=e):
                ok, reason = validate_email(e)
                self.assertTrue(ok, f"expected valid (no extra given) for {e}, got {reason}")

    def test_vertical_specific_vendors_rejected_when_extra_supplied(self):
        # When the dental pipeline supplies its VENDOR_DOMAINS_EXTRA, those
        # domains get the same vendor_marketing rejection.
        for e in ['webreporting@gargle.com', 'contact@officite.com',
                  'dcpflugerville@mydentalmail.com']:
            with self.subTest(email=e):
                ok, reason = validate_email(e, extra_vendor_domains=DENTAL_VENDOR_DOMAINS_EXTRA)
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
