"""Tests for lib.enrichers.deep_site_crawl."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.enrichers.deep_site_crawl import extract_jsonld_persons


PAGE_WITH_PERSON_JSONLD = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Dentist",
  "name": "Smith Family Dental",
  "url": "https://smithfamilydental.com",
  "founder": {
    "@type": "Person",
    "name": "Dr. John Smith",
    "jobTitle": "Owner",
    "email": "john@smithfamilydental.com"
  }
}
</script>
</head><body></body></html>
"""


class TestExtractJsonLDPersons(unittest.TestCase):
    def test_extracts_person_with_name_role_email(self):
        persons = extract_jsonld_persons(PAGE_WITH_PERSON_JSONLD)
        self.assertEqual(len(persons), 1)
        self.assertEqual(persons[0]['name'], 'Dr. John Smith')
        self.assertEqual(persons[0]['role'], 'Owner')
        self.assertEqual(persons[0]['email'], 'john@smithfamilydental.com')


if __name__ == '__main__':
    unittest.main()
