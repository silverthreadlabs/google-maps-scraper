"""Tests for lib.enrichers.serp."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.enrichers.serp import parse_google_results


GOOGLE_HTML = """
<html><body>
<div class="g">
  <a href="https://linkedin.com/in/john-smith-phoenix-dds"><h3>Dr. John Smith — Smith Family Dental</h3></a>
  <div class="VwiC3b">Dr. John Smith — Owner at Smith Family Dental, Phoenix AZ.</div>
</div>
<div class="g">
  <a href="https://www.smithfamilydental.com"><h3>Smith Family Dental — Home</h3></a>
  <div class="VwiC3b">Phoenix family dentistry. New patients welcome.</div>
</div>
</body></html>
"""


class TestParseGoogleResults(unittest.TestCase):
    def test_extracts_url_title_and_snippet_for_each_result(self):
        results = parse_google_results(GOOGLE_HTML)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['url'], 'https://linkedin.com/in/john-smith-phoenix-dds')
        self.assertIn('Smith Family Dental', results[0]['title'])
        self.assertIn('Phoenix', results[0]['snippet'])


BING_HTML = """
<html><body>
<li class="b_algo">
  <h2><a href="https://linkedin.com/in/john-smith-phoenix-dds">Dr. John Smith</a></h2>
  <p>Owner at Smith Family Dental, Phoenix AZ.</p>
</li>
</body></html>
"""

DDG_HTML = """
<html><body>
<div class="result">
  <a class="result__a" href="https://linkedin.com/in/john-smith-phoenix-dds">Dr. John Smith</a>
  <a class="result__snippet">Owner at Smith Family Dental, Phoenix AZ.</a>
</div>
</body></html>
"""


class TestParseBingDDGResults(unittest.TestCase):
    def test_parse_bing_results(self):
        from lib.enrichers.serp import parse_bing_results
        results = parse_bing_results(BING_HTML)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['url'], 'https://linkedin.com/in/john-smith-phoenix-dds')

    def test_parse_ddg_results(self):
        from lib.enrichers.serp import parse_ddg_results
        results = parse_ddg_results(DDG_HTML)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['url'], 'https://linkedin.com/in/john-smith-phoenix-dds')


GOOGLE_CAPTCHA_HTML = """
<html><body>
<div id="captcha-form">
  <h2>Our systems have detected unusual traffic from your computer network.</h2>
  <input type="hidden" name="recaptcha-response">
</div>
</body></html>
"""

DDG_RATE_LIMITED_HTML = """
<html><body><h1>Anomaly detected</h1><p>Please retry shortly.</p></body></html>
"""


class TestBlockDetection(unittest.TestCase):
    def test_google_captcha_detected(self):
        from lib.enrichers.serp import is_blocked
        self.assertTrue(is_blocked('google', GOOGLE_CAPTCHA_HTML))

    def test_ddg_anomaly_detected(self):
        from lib.enrichers.serp import is_blocked
        self.assertTrue(is_blocked('ddg', DDG_RATE_LIMITED_HTML))

    def test_normal_page_not_blocked(self):
        from lib.enrichers.serp import is_blocked
        self.assertFalse(is_blocked('google', GOOGLE_HTML))


class TestRunSerpQueryFallback(unittest.TestCase):
    def test_falls_back_from_ddg_to_bing_to_google(self):
        from lib.enrichers.serp import run_serp_query_with_fallback
        calls = []
        def fake_fetch(url):
            if 'duckduckgo.com' in url:
                calls.append('ddg')
                return DDG_RATE_LIMITED_HTML
            if 'bing.com' in url:
                calls.append('bing')
                return '<html><body>access denied</body></html>'
            calls.append('google')
            return GOOGLE_HTML
        result = run_serp_query_with_fallback(
            query='site:linkedin.com/in "Dr. John Smith" "Phoenix" dental',
            fetch_fn=fake_fetch,
        )
        self.assertEqual(calls, ['ddg', 'bing', 'google'])
        self.assertEqual(result['engine'], 'google')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(len(result['results']), 2)

    def test_returns_blocked_when_all_engines_blocked(self):
        from lib.enrichers.serp import run_serp_query_with_fallback
        def all_blocked(url):
            return '<html><body>captcha-form unusual traffic</body></html>'
        result = run_serp_query_with_fallback(query='foo', fetch_fn=all_blocked)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['results'], [])


if __name__ == '__main__':
    unittest.main()
