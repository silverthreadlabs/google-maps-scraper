"""Tests for lib.enrichers.curl_retry (stdlib unittest, no deps)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from lib.enrichers.curl_retry import (
    RECOVERABLE_STATUSES,
    emails_from_html,
    extract_contact_links,
    is_cloudflare_challenge,
    read_bounded,
    select_candidates,
)


class _DripFile:
    """A body that never ends. Models the slow-drip host that hung a worker."""

    def __init__(self, block: bytes = b'x' * 8):
        self.block = block
        self.reads = 0

    def read(self, n: int) -> bytes:
        self.reads += 1
        return self.block[:n]


class _FiniteFile:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def read(self, n: int) -> bytes:
        out = self.data[self.pos:self.pos + n]
        self.pos += len(out)
        return out


class TestReadBounded(unittest.TestCase):
    def test_reads_a_finite_body_in_full(self):
        fp = _FiniteFile(b'hello world')
        self.assertEqual(read_bounded(fp), b'hello world')

    def test_stops_at_max_bytes(self):
        fp = _DripFile()
        got = read_bounded(fp, max_bytes=32, chunk=8)
        self.assertEqual(len(got), 32)

    def test_stops_at_the_deadline(self):
        # The clock advances one second per call, so a 3-second budget must
        # end the loop even though the body never finishes.
        ticks = iter(range(0, 100))
        fp = _DripFile()
        got = read_bounded(fp, max_bytes=10_000_000, chunk=8,
                           deadline=3, clock=lambda: next(ticks))
        self.assertLess(len(got), 10_000_000)
        self.assertGreater(len(got), 0)

    def test_deadline_already_passed_returns_empty(self):
        fp = _DripFile()
        self.assertEqual(read_bounded(fp, deadline=0, clock=lambda: 5), b'')

    def test_empty_body_returns_empty(self):
        self.assertEqual(read_bounded(_FiniteFile(b'')), b'')


class TestSelectCandidates(unittest.TestCase):
    def test_keeps_recoverable_statuses(self):
        # open_error / timeout / extract_failed are the classes a realistic
        # UA can recover. They 403'd or timed out against the headless UA.
        rows = [
            {'lead_title': 'A', 'website': 'https://a.example/', 'status': 'open_error'},
            {'lead_title': 'B', 'website': 'https://b.example/', 'status': 'timeout'},
            {'lead_title': 'C', 'website': 'https://c.example/', 'status': 'extract_failed'},
        ]
        got = select_candidates(rows)
        self.assertEqual([r['lead_title'] for r in got], ['A', 'B', 'C'])

    def test_keeps_cloudflare_but_marks_low_odds(self):
        # A real JS challenge needs a real browser. We still attempt it —
        # some "cloudflare_blocked" rows are plain 403s on the headless UA.
        rows = [{'lead_title': 'A', 'website': 'https://a.example/',
                 'status': 'cloudflare_blocked'}]
        got = select_candidates(rows)
        self.assertEqual(len(got), 1)
        self.assertTrue(got[0]['low_odds'])

    def test_drops_rows_with_no_website(self):
        rows = [{'lead_title': 'A', 'website': '', 'status': 'open_error'},
                {'lead_title': 'B', 'status': 'open_error'}]
        self.assertEqual(select_candidates(rows), [])

    def test_drops_non_retryable_status(self):
        # A site we reached that simply published no email is not a retry
        # candidate — re-fetching it changes nothing.
        rows = [{'lead_title': 'A', 'website': 'https://a.example/',
                 'status': 'no_email_found'},
                {'lead_title': 'B', 'website': 'https://b.example/',
                 'status': 'ok'}]
        self.assertEqual(select_candidates(rows), [])

    def test_dedupes_by_hostname(self):
        # The merge joins on hostname, so two rows on one host are one fetch.
        rows = [
            {'lead_title': 'A', 'website': 'https://acme.example/', 'status': 'open_error'},
            {'lead_title': 'B', 'website': 'https://www.acme.example/x', 'status': 'open_error'},
        ]
        got = select_candidates(rows)
        self.assertEqual(len(got), 1)

    def test_recoverable_statuses_is_a_frozenset(self):
        self.assertIsInstance(RECOVERABLE_STATUSES, frozenset)


class TestCloudflareDetection(unittest.TestCase):
    def test_detects_just_a_moment_challenge(self):
        html = '<title>Just a moment...</title><p>cloudflare</p>'
        self.assertTrue(is_cloudflare_challenge(html))

    def test_detects_checking_your_browser(self):
        html = 'Checking your browser before accessing. Cloudflare Ray ID'
        self.assertTrue(is_cloudflare_challenge(html))

    def test_detects_cf_error_marker(self):
        self.assertTrue(is_cloudflare_challenge('<div class="cf-error-details">'))

    def test_plain_page_is_not_a_challenge(self):
        html = '<h1>Cool Air Tampa</h1><p>Call us. We use Cloudflare CDN.</p>'
        self.assertFalse(is_cloudflare_challenge(html))


class TestExtractContactLinks(unittest.TestCase):
    def test_finds_relative_and_absolute_contact_links(self):
        html = '''
          <a href="/contact-us">Contact</a>
          <a href="https://acme.example/about">About</a>
          <a href="//acme.example/team">Team</a>
          <a href="/services">Services</a>
        '''
        got = extract_contact_links(html, 'https://acme.example/')
        self.assertIn('https://acme.example/contact-us', got)
        self.assertIn('https://acme.example/about', got)
        self.assertIn('https://acme.example/team', got)
        self.assertNotIn('https://acme.example/services', got)

    def test_skips_the_base_url_itself(self):
        html = '<a href="https://acme.example/">Contact</a>'
        self.assertEqual(extract_contact_links(html, 'https://acme.example/'), [])

    def test_caps_the_link_count(self):
        html = ''.join(f'<a href="/contact-{i}">c</a>' for i in range(20))
        self.assertLessEqual(len(extract_contact_links(html, 'https://acme.example/')), 4)

    def test_handles_mailto_without_crashing(self):
        html = '<a href="mailto:info@acme.example">Contact</a>'
        self.assertEqual(extract_contact_links(html, 'https://acme.example/'), [])


class TestEmailsFromHtml(unittest.TestCase):
    def test_uses_the_canonical_validator(self):
        # Rule 5: no private substring blocklist. The artifact classes the
        # shared validator knows must be rejected here too.
        html = '''
          info@coolairtampa.com
          9a65e97ebe8141fca0c4fd686f70996b@sentry.wixpress.com
          header-logo@2x-150x150.png
          u003einfo@ddair.com
          noreply@coolairtampa.com
        '''
        self.assertEqual(emails_from_html(html), ['info@coolairtampa.com'])

    def test_picks_up_mailto_addresses(self):
        html = '<a href="mailto:owner@shop.example">mail</a>'
        self.assertEqual(emails_from_html(html), ['owner@shop.example'])

    def test_applies_extra_vendor_domains(self):
        html = 'sales@angi.com hello@shop.example'
        got = emails_from_html(html, extra_vendor_domains=frozenset({'angi.com'}))
        self.assertEqual(got, ['hello@shop.example'])

    def test_dedupes_case_insensitively(self):
        html = 'Info@Shop.Example info@shop.example'
        self.assertEqual(len(emails_from_html(html)), 1)

    def test_empty_html_returns_empty_list(self):
        self.assertEqual(emails_from_html(''), [])
        self.assertEqual(emails_from_html(None), [])


if __name__ == '__main__':
    unittest.main()
