"""Tests for vertical-agnostic website_crawl primitives."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.enrichers.website_crawl import (
    EnrichProfile,
    _build_extract_js,
    looks_like_practice_name,
    merge_doctors,
    parse_eval_output,
)


DENTAL = EnrichProfile(
    poc_title_markers_js=r"\b(?:Dr\.?|DDS|DMD|D\.D\.S\.?|D\.M\.D\.?)\b",
    jsonld_person_types=("person", "dentist", "physician"),
    practice_name_words=frozenset({"dental", "dentistry", "smiles", "orthodontics",
                                   "clinic", "office", "practice"}),
    internal_link_gate_js=r"(contact|about|team|staff|get-in-touch|our-team|meet|providers|doctors|dentist|dr-)",
    contact_link_pattern=r"/(contact|get-in-touch)",
    team_link_pattern=r"/(team|staff|providers|doctors|our-doctor|meet|about)",
)


# A second profile so loop tests can assert *discriminating* properties per
# variant rather than re-asserting things that hold for every profile.
LEGAL = EnrichProfile(
    poc_title_markers_js=r"\b(?:Esq\.?|Attorney)\b",
    jsonld_person_types=("person", "attorney"),
    practice_name_words=frozenset({"law", "legal", "associates", "llp", "llc"}),
    internal_link_gate_js=r"(contact|about|attorneys|partners|team)",
    contact_link_pattern=r"/(contact|reach-us)",
    team_link_pattern=r"/(attorneys|partners|team|our-people)",
)


class TestBuildExtractJs(unittest.TestCase):
    def test_injects_poc_title_markers_as_regex_literal(self):
        js = _build_extract_js(DENTAL)
        self.assertIn(r"/\b(?:Dr\.?|DDS|DMD|D\.D\.S\.?|D\.M\.D\.?)\b/i", js)

    def test_injects_jsonld_person_types_as_json_array(self):
        js = _build_extract_js(DENTAL)
        self.assertIn('["person", "dentist", "physician"]', js)

    def test_injects_internal_link_gate_as_regex_literal(self):
        js = _build_extract_js(DENTAL)
        self.assertIn(r"/(contact|about|team|staff|get-in-touch|our-team|meet|providers|doctors|dentist|dr-)/i", js)

    def test_no_unresolved_placeholders(self):
        js = _build_extract_js(DENTAL)
        for placeholder in ("__POC_TITLE_MARKERS__", "__JSONLD_PERSON_TYPES__", "__INTERNAL_LINK_GATE__"):
            self.assertNotIn(placeholder, js, f"placeholder {placeholder} not replaced")

    def test_distinct_profiles_render_distinct_title_markers(self):
        # Each variant must produce JS that contains its own marker and not the other's.
        cases = [
            (DENTAL, r"/\b(?:Dr\.?|DDS|DMD|D\.D\.S\.?|D\.M\.D\.?)\b/i", r"/\b(?:Esq\.?|Attorney)\b/i"),
            (LEGAL,  r"/\b(?:Esq\.?|Attorney)\b/i",                    r"/\b(?:Dr\.?|DDS|DMD|D\.D\.S\.?|D\.M\.D\.?)\b/i"),
        ]
        for profile, expected_present, expected_absent in cases:
            with self.subTest(profile=profile.jsonld_person_types):
                js = _build_extract_js(profile)
                self.assertIn(expected_present, js)
                self.assertNotIn(expected_absent, js)


class TestLooksLikePracticeName(unittest.TestCase):
    def test_no_space_in_name_is_practice(self):
        self.assertTrue(looks_like_practice_name("Smiles", "Smiles Dental", profile=DENTAL))

    def test_name_containing_practice_word_is_practice(self):
        self.assertTrue(looks_like_practice_name("Smiles Dental Office", "Smiles Dental", profile=DENTAL))

    def test_name_substring_of_lead_title_is_practice(self):
        self.assertTrue(looks_like_practice_name("Round Rock", "Round Rock Modern Dentistry", profile=DENTAL))

    def test_real_person_name_is_not_practice(self):
        self.assertFalse(looks_like_practice_name("Sarah Patel", "Round Rock Modern Dentistry", profile=DENTAL))

    def test_profile_word_set_drives_filter(self):
        # "Patel Law Group" contains a LEGAL practice word but no DENTAL one.
        self.assertTrue(looks_like_practice_name("Patel Law Group", "Acme Law Firm", profile=LEGAL))
        # Under DENTAL it would *still* be filtered because "Patel Law Group"
        # is a substring of "Acme Law Firm" — so use a non-substring title to
        # isolate the word-filter behaviour.
        self.assertFalse(looks_like_practice_name("Patel Law Group", "Some Other Place", profile=DENTAL))


class TestMergeDoctors(unittest.TestCase):
    def test_jsonld_person_becomes_poc_with_role(self):
        data = {
            "ldPersons": [{"name": "Sarah Patel", "jobTitle": "DDS", "email": None,
                           "sameAs": [], "url": None}],
            "drHeadings": [],
            "drAlts": [],
        }
        out = merge_doctors(data, "Acme Dental", profile=DENTAL)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "Sarah Patel")
        self.assertEqual(out[0]["role"], "DDS")
        self.assertEqual(out[0]["sources"], ["json_ld"])

    def test_dedupes_jsonld_and_heading_for_same_person(self):
        data = {
            "ldPersons": [{"name": "Sarah Patel", "jobTitle": "DDS", "email": None,
                           "sameAs": [], "url": None}],
            "drHeadings": [{"tag": "h2", "text": "Dr. Sarah Patel", "name": "Sarah Patel"}],
            "drAlts": [],
        }
        out = merge_doctors(data, "Acme Dental", profile=DENTAL)
        self.assertEqual(len(out), 1)
        self.assertEqual(set(out[0]["sources"]), {"json_ld", "heading_h2"})

    def test_filters_practice_name_entries(self):
        data = {
            "ldPersons": [
                {"name": "Acme Dental Office", "jobTitle": None, "email": None,
                 "sameAs": [], "url": None},
                {"name": "Sarah Patel", "jobTitle": None, "email": None,
                 "sameAs": [], "url": None},
            ],
            "drHeadings": [],
            "drAlts": [],
        }
        out = merge_doctors(data, "Acme Dental", profile=DENTAL)
        self.assertEqual([p["name"] for p in out], ["Sarah Patel"])

    def test_img_alt_only_person_appears(self):
        data = {
            "ldPersons": [],
            "drHeadings": [],
            "drAlts": [{"alt": "Dr. Sarah Patel, DDS", "name": "Sarah Patel"}],
        }
        out = merge_doctors(data, "Acme Dental", profile=DENTAL)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["sources"], ["img_alt"])


class TestParseEvalOutput(unittest.TestCase):
    def test_parses_double_encoded_json_string(self):
        # agent-browser sometimes returns the JSON as a double-encoded string
        # ("...{\"k\": ...}...") on its last output line.
        raw = '"{\\"emails\\": [\\"x@y.com\\"]}"'
        self.assertEqual(parse_eval_output(raw), {"emails": ["x@y.com"]})

    def test_parses_plain_json_object(self):
        raw = '{"emails": ["x@y.com"]}'
        self.assertEqual(parse_eval_output(raw), {"emails": ["x@y.com"]})

    def test_returns_none_for_empty_or_none_input(self):
        self.assertIsNone(parse_eval_output(""))
        self.assertIsNone(parse_eval_output(None))

    def test_returns_none_for_unparseable(self):
        self.assertIsNone(parse_eval_output("not json at all\nblah blah"))


class TestFilterValidEmails(unittest.TestCase):
    """The JS REJECT regex used to drop these in the browser. Now Python
    does it via `filter_valid_emails` → `validate_email`."""

    def setUp(self):
        from lib.enrichers.website_crawl import filter_valid_emails
        self.f = filter_valid_emails

    def test_drops_image_artifact_emails(self):
        # WordPress/retina image filenames matched the email regex on
        # row 0 of the cosmetic_surgeons_dallas handoff (12 of them).
        out = self.f([
            'real@drburns.com',
            'shutterstock_2675292683_1440x640@2x.jpg',
            'image_x_1440x640@2x.png',
        ])
        self.assertEqual(out, ['real@drburns.com'])

    def test_drops_vendor_domains(self):
        out = self.f([
            'info@drburns.com', 'tracker@wix.com', 'data@cloudflare.com',
        ])
        self.assertEqual(out, ['info@drburns.com'])

    def test_drops_placeholder_locals_and_domains(self):
        out = self.f([
            'real@drburns.com', 'sample@anything.com', 'info@example.com',
            'your@email.com', 'noreply@drburns.com',
        ])
        self.assertEqual(out, ['real@drburns.com'])

    def test_dedupes_case_insensitively_preserves_first(self):
        out = self.f(['Info@Drburns.com', 'info@drburns.com'])
        self.assertEqual(out, ['Info@Drburns.com'])

    def test_skips_blank_and_non_string(self):
        out = self.f(['', '  ', None, 123, 'real@drburns.com'])
        self.assertEqual(out, ['real@drburns.com'])

    def test_extra_vendor_domains_layer(self):
        out = self.f(
            ['hello@vendor.example', 'real@drburns.com'],
            extra_vendor_domains=frozenset({'vendor.example'}),
        )
        self.assertEqual(out, ['real@drburns.com'])


class TestExtractJsTemplateNoRejectRegex(unittest.TestCase):
    """Lock the architectural change: JS no longer carries a hard-coded
    REJECT regex of vendor / image / placeholder patterns. Filtering is
    Python-side via `filter_valid_emails` so we only have one set of rules."""

    def test_template_does_not_declare_reject_constant(self):
        from lib.enrichers.website_crawl import EXTRACT_JS_TEMPLATE
        self.assertNotIn('const REJECT', EXTRACT_JS_TEMPLATE)
        self.assertNotIn('@wix\\.com', EXTRACT_JS_TEMPLATE)
        self.assertNotIn('@2x', EXTRACT_JS_TEMPLATE)


if __name__ == '__main__':
    unittest.main(verbosity=2)
