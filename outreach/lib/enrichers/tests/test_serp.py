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


if __name__ == '__main__':
    unittest.main()
