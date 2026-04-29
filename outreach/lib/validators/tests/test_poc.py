"""Tests for outreach.lib.validators.poc (stdlib unittest, no deps)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.validators.poc import extract_doctor_name, looks_like_practice_name


SHOULD_EXTRACT = [
    # (input, expected_name)
    ("Dr. John Smith",                  "John Smith"),
    ("Dr John Smith",                   "John Smith"),
    ("Meet Dr. Sarah Connor",           "Sarah Connor"),
    ("Dr. Mark R. Holmes",              "Mark R. Holmes"),
    ("Dr. Mark R Holmes",               "Mark R Holmes"),
    ("Welcome — Dr. Tamer El-Gendy",    "Tamer El-Gendy"),
    ("John Smith, DDS",                 "John Smith"),
    ("John Smith DDS",                  "John Smith"),
    ("Sarah Connor, D.D.S.",            "Sarah Connor"),
    ("Mark R. Holmes, DMD",             "Mark R. Holmes"),
    ("Mark R Holmes DMD",               "Mark R Holmes"),
    ("Tamer El-Gendy, DDS",             "Tamer El-Gendy"),
    ("Erica Webb, DDS, MS",             "Erica Webb"),
    ("Vinh Huynh DMD",                  "Vinh Huynh"),
]

SHOULD_REJECT = [
    "Hancock Dr",
    "Hancock Dr.",
    "Located on Maple Dr",
    "123 Hancock Dr, Suite 100",
    "Visit us on Cedar Park Dr",
    "Office on Highway 41",
    "1234 Main St, Suite 100",
    "5678 Sunset Blvd",
    "Dental on Central",
    "Smile Design Downtown",
    "Pediatric Dentistry of Brandon",
    "Cosmetic Smiles Clinic",
    "Welcome to our practice",
    "Schedule an appointment",
    "Contact Us",
    "About",
    "Dr",
    "",
    None,
    "x" * 200,
    "Doctor available today",
    "We are open every day",
]

PRACTICE_NAME_CASES = [
    # (name, lead_title, expected_is_practice)
    ("Dental on Central",       None,                              True),
    ("Smile Design Downtown",   None,                              True),
    ("Pediatric Dentistry",     None,                              True),
    ("Family Dental Care",      None,                              True),
    ("John Smith",              None,                              False),
    ("Tamer El-Gendy",          None,                              False),
    ("Mountain View",           "Mountain View Family Dental",     True),
    ("Mountain",                "Mountain View Family Dental",     True),
    ("John Smith",              "Mountain View Family Dental",     False),
]


class TestExtraction(unittest.TestCase):
    def test_should_extract(self):
        for text, expected in SHOULD_EXTRACT:
            with self.subTest(text=text):
                self.assertEqual(extract_doctor_name(text), expected)

    def test_should_reject(self):
        for text in SHOULD_REJECT:
            with self.subTest(text=text):
                self.assertIsNone(extract_doctor_name(text))

    def test_practice_name_guard(self):
        for name, title, expected in PRACTICE_NAME_CASES:
            with self.subTest(name=name, title=title):
                self.assertIs(looks_like_practice_name(name, title), expected)

    def test_drops_practice_self_when_title_given(self):
        self.assertIsNone(extract_doctor_name("Dental on Central", "Dental on Central"))

    def test_keeps_real_doctor_with_title_context(self):
        self.assertEqual(
            extract_doctor_name("Dr. Tamer El-Gendy", "Dental on Central"),
            "Tamer El-Gendy",
        )

    def test_whitespace_robustness(self):
        cases = [
            ("Dr. John Smith",          "John Smith"),  # nbsp
            ("  Dr. John Smith  ",            "John Smith"),
            ("Dr. John Smith\nGeneral Dentist", "John Smith"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(extract_doctor_name(text), expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
