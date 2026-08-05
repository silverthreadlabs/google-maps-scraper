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
    # Real artifact from a software_ua crawl: '@-NNNxNNN.jpg' (dash before
    # the width). The `@` regex captures the slug as the local part and the
    # filename as the domain, so the validator must catch the image-size
    # suffix even when it isn't immediately preceded by digits.
    'how-to-build-a-saas-platform2@-158x106.jpg',
    'agency-growth-levers@-614x346.jpg',
    # hvac_tampa crawl (DDD-0004): WordPress thumbnail variants. The retina
    # suffix is followed by a *second* dimension suffix or '-scaled', so the
    # `<digits>x<digits>.<ext>$` anchor never reached the end of the string.
    'header-logo@2x-150x150.png',
    'home-banner@2x-scaled.webp',
    'hero@2x-1024x683.jpeg',
    # .avif was simply absent from the extension list.
    'logo@2x.avif',
]

# JSON-escape artifacts: the crawler captured an address embedded in a JSON
# blob, so the escape sequence for the preceding `>` or `"` is glued to the
# local part ('>' → 'u003e'). All 23 in the hvac_tampa corpus have their
# clean twin in the same pool, so rejecting the mangled form loses nothing.
INVALID_JSON_ESCAPE = [
    'u003ecustomerservice@classycaps.com',
    'u0022contact@firm.com',
    'u003Einfo@coolairtampa.com',
]

# URL-encoded leading whitespace (e.g. '%20' = space). Some gosom captures
# include the encoded space and slip past the basic EMAIL_RE because `%`
# is a permitted local-part character. The clean version of the address is
# usually right next to it in the same emails[] array, so rejecting the
# encoded variant is harmless and avoids backend validation 500s.
INVALID_URL_ENCODED = [
    '%20marketing@signupsolution.com',
    '%20info@creativewebvisions.com',
    '%20Info@unitedsol.net',
]

# Sentry DSN public keys captured off template sites. The DSN is embedded in
# page JS as `https://<32-hex>@<host>/<project>`, so the `@` regex yields a
# 32-hex local part on a Sentry ingest host. Observed on Wix-hosted HVAC sites
# (hvac_tampa crawl); the ingest host varies per tenant, so match the DSN shape
# rather than enumerating hosts.
INVALID_SENTRY_DSN = [
    '9a65e97ebe8141fca0c4fd686f70996b@sentry.wixpress.com',
    'c183baa23371454f99f417f6616b724d@sentry.wixpress.com',
    'dd0a55ccb8124b9c9d938e3acf41f8aa@sentry-next.wixpress.com',
    '0123456789abcdef0123456789abcdef@o12345.ingest.sentry.io',
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

    def test_image_artifact_with_dimension_suffix(self):
        # A retina suffix followed by a resize suffix (WordPress thumbnails).
        for e in ('header-logo@2x-150x150.png', 'hero@2x-1024x683.jpeg'):
            with self.subTest(email=e):
                self.assertEqual(validate_email(e), (False, 'image_artifact'))

    def test_image_artifact_scaled_suffix(self):
        self.assertEqual(validate_email('home-banner@2x-scaled.webp'),
                         (False, 'image_artifact'))

    def test_image_artifact_avif(self):
        self.assertEqual(validate_email('logo@2x.avif'), (False, 'image_artifact'))

    def test_json_escape_prefix_rejected(self):
        for e in INVALID_JSON_ESCAPE:
            with self.subTest(email=e):
                self.assertEqual(validate_email(e), (False, 'json_escape_artifact'))

    def test_clean_address_with_u_prefix_still_valid(self):
        # The guard anchors on 'u00' + two hex digits, not on a leading 'u'.
        for e in ('ulrich@acme.com', 'u2@acme.com', 'uma.patel@acme.com'):
            with self.subTest(email=e):
                ok, reason = validate_email(e)
                self.assertTrue(ok, f"expected valid, got reason={reason}")

    def test_existing_valid_addresses_unaffected(self):
        # Regression guard for the widened IMAGE_RE / new escape class.
        # A generic mailbox is NOT invalid — that distinction lives in the
        # scorer, not the validator.
        for e in VALID + ['info@acme.com', 'office@shop.com',
                          'bamairservices@gmail.com', 'a2x@acme.com']:
            with self.subTest(email=e):
                ok, reason = validate_email(e)
                self.assertTrue(ok, f"expected valid, got reason={reason}")

    def test_sentry_dsn(self):
        for e in INVALID_SENTRY_DSN:
            with self.subTest(email=e):
                ok, reason = validate_email(e)
                self.assertFalse(ok)
                self.assertEqual(reason, 'tracking_artifact')

    def test_hex_local_part_on_real_domain_still_valid(self):
        # The DSN guard keys on hex local part AND a tracking host. A hex-ish
        # local part on a practice domain is a real (if odd) mailbox.
        ok, reason = validate_email('0123456789abcdef0123456789abcdef@coolairtampa.com')
        self.assertTrue(ok, f"expected valid, got reason={reason}")

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

    def test_url_encoded_prefix(self):
        for e in INVALID_URL_ENCODED:
            with self.subTest(email=e):
                ok, reason = validate_email(e)
                self.assertFalse(ok, f"expected reject for {e}")
                self.assertEqual(reason, 'malformed')


if __name__ == '__main__':
    unittest.main(verbosity=2)
