# OSINT Enrichment Stage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a free-tier OSINT enrichment stage that fills gaps left by `website_crawl` and `owner_lookup` — LinkedIn URLs, social URLs, POC name/role/email — with confident-or-skip semantics.

**Architecture:** Three deterministic enrichers (WHOIS, deep-site crawl, SERP) write candidates to a per-lead sidecar; an LLM-judge subagent (`osint-binder`, Haiku) annotates each candidate with `judge_verdict` + `confidence`; a merge script grafts above-threshold hits into master with full provenance. Cross-target lanes for parallelism (one SERP worker, one deep-crawl session pool, one WHOIS worker). Agent-browser session pool reused from `lib/enrichers/website_crawl.py` per CLAUDE.md rule 4.

**Tech Stack:** Python 3 (existing `outreach/.venv`), `python-whois`, `lxml` / `beautifulsoup4`, agent-browser CLI (already a project dep), `unittest` (existing convention), Anthropic subagent dispatched via the `Task` tool from the `/outreach` slash-command runbook (same pattern as `pain-classifier`).

**Spec:** `outreach/docs/2026-05-07-osint-enrichment-design.md` — read before starting.

---

## File structure

| File | Status | Responsibility |
|---|---|---|
| `outreach/lib/enrichers/whois_lookup.py` | NEW | Single-domain WHOIS lookup; parses registrant_name / registrant_email / registrant_org; returns candidates dict or empty on redacted/error |
| `outreach/lib/enrichers/tests/test_whois_lookup.py` | NEW | Mocked `python-whois` responses: unredacted, redacted, network error, parse error |
| `outreach/lib/enrichers/deep_site_crawl.py` | NEW | Fetches `/about`, `/team`, etc. via agent-browser; parses JSON-LD `Person`/`Organization` and heading-proximity POC patterns; skips URLs `website_crawl.json` already touched |
| `outreach/lib/enrichers/tests/test_deep_site_crawl.py` | NEW | Mocked HTML fixtures (JSON-LD, headings, no-data) and crawl-dedup logic |
| `outreach/lib/enrichers/serp.py` | NEW | Agent-browser SERP fetcher with engine fallback ladder (DDG→Bing→Google), captcha detection, jitter |
| `outreach/lib/enrichers/tests/test_serp.py` | NEW | Mocked SERP HTML for each engine; captcha detection; engine fallback ordering |
| `outreach/.claude/agents/osint-binder.md` | NEW | LLM-judge subagent definition (Haiku); reads sidecar path, writes judgment path |
| `outreach/scripts/osint_enrich.py` | NEW | Orchestrator: gap-detect, two-wave dispatch (whois+deep_site → serp), incremental sidecar write, resumable, pipeline-locked |
| `outreach/scripts/tests/test_osint_enrich.py` | NEW | Gap detection, wave ordering, sidecar shape, resumability |
| `outreach/scripts/merge_osint_into_master.py` | NEW | Graft above-threshold hits into master with provenance; respect immutability; pipe email candidates through `lib.validators.email`; handle list-typed fields |
| `outreach/scripts/tests/test_merge_osint_into_master.py` | NEW | Threshold filter, no-overwrite, validator gating, list-typed grafts |
| `outreach/pipelines/dental_sunbelt/config.py` | MODIFY | Add `OSINT_*` constants (sources, fields desired, threshold, query templates, deep-crawl paths, industry terms, handoff fields) |
| `outreach/pipelines/dental_sunbelt/eval/osint_binding/gold_set.json` | NEW | Hand-labeled `(lead, candidates, correct_index | null)` tuples — bootstrap with empty array, populate after first real run |
| `outreach/pipelines/dental_sunbelt/eval/osint_binding/eval_runner.py` | NEW | Runs `osint-binder` over gold set, reports precision/recall and threshold sweep |
| `outreach/pipelines/dental_sunbelt/eval/osint_binding/README.md` | NEW | How to add labels, interpret output |
| `.claude/commands/outreach.md` | MODIFY | Insert OSINT stage entry between `owner_lookup --apply` and `classify` |
| `outreach/.env.example` | MODIFY | Add `# python-whois` note if any env config is needed (likely none) |
| `outreach/requirements.txt` *(if it exists, else README install note)* | MODIFY | Add `python-whois` |

---

## Sidecar schemas (reference for tasks below)

**`enrichment/osint/<date>.json`** — list-of-records, one per lead:

```jsonc
{
  "place_id": "ChIJ...",
  "domain": "smithfamilydental.com",
  "enriched_at": "2026-05-07T15:00:00Z",
  "fields": {
    "<field_name>": {
      "candidates": [
        {
          "value": "<string>",
          "source": "<serp_google|serp_bing|serp_ddg|deep_site_crawl|whois>",
          "query": "<string|null>",       // SERP-only
          "snippet": "<string|null>",     // SERP-only
          "judge_verdict": null,          // populated by subagent: "match" | "rejected"
          "judge_confidence": null,       // populated by subagent: 0.0-1.0
          "judge_reasoning": null         // populated by subagent
        }
      ],
      "selected_index": null,             // populated by subagent: int | null
      "selected_confidence": null,        // populated by subagent
      "skipped_reason": null              // "no_results" | "below_threshold" | "no_poc_name_known" | "serp_blocked"
    }
  },
  "errors": []
}
```

**`enrichment/osint_judgments/<date>.json`** — written by subagent, one record per lead-field with judgment results. Merged back into the main sidecar by the orchestrator's `--apply-judgments` step.

---

## Tasks

### Task 1: Add `python-whois` dependency

**Files:**
- Modify: `outreach/requirements.txt` (or `outreach/README.md` install section if no requirements file)

- [ ] **Step 1: Install dependency in venv**

```bash
cd /home/fassihhaider/Work/google-maps-scraper/outreach
source .venv/bin/activate
pip install python-whois
```

- [ ] **Step 2: Pin in requirements.txt (if file exists) or document in README**

If `outreach/requirements.txt` exists, append:
```
python-whois>=0.9.0
```
If not, add an "Install" subsection to `outreach/README.md` listing the new dep alongside any existing.

- [ ] **Step 3: Smoke-test the import**

```bash
python -c "import whois; print(whois.__version__)"
```
Expected: prints version, no ImportError.

- [ ] **Step 4: Commit**

```bash
cd /home/fassihhaider/Work/google-maps-scraper
git add outreach/requirements.txt outreach/README.md
git commit -m "chore(outreach): add python-whois dep for OSINT enrichment"
```

---

### Task 2: WHOIS enricher — happy path (unredacted)

**Files:**
- Create: `outreach/lib/enrichers/whois_lookup.py`
- Test: `outreach/lib/enrichers/tests/test_whois_lookup.py`

- [ ] **Step 1: Write the failing test**

```python
# outreach/lib/enrichers/tests/test_whois_lookup.py
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


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/fassihhaider/Work/google-maps-scraper
python outreach/lib/enrichers/tests/test_whois_lookup.py
```
Expected: FAIL with `ModuleNotFoundError: No module named 'lib.enrichers.whois_lookup'`.

- [ ] **Step 3: Write minimal implementation**

```python
# outreach/lib/enrichers/whois_lookup.py
"""WHOIS lookup for OSINT enrichment.

Returns registrant fields if the registrar exposes them; emits a clean
miss (status='redacted') for privacy-protected domains, or
status='error' for transport/parse failures.

Per outreach/CLAUDE.md rule 1, the caller is responsible for sibling
provenance; this module just returns the raw lookup result.
"""
from __future__ import annotations

import whois  # python-whois


def lookup_domain(domain: str) -> dict:
    """Look up `domain` and return a normalized dict.

    Keys: registrant_name, registrant_email, registrant_org, status.
    `status` is one of 'ok', 'redacted', 'error'.
    """
    rec = whois.whois(domain)
    name = _first(getattr(rec, 'name', None))
    email = _first(getattr(rec, 'emails', None))
    org = _first(getattr(rec, 'org', None))
    return {
        'registrant_name': name,
        'registrant_email': email,
        'registrant_org': org,
        'status': 'ok',
    }


def _first(value):
    """python-whois sometimes returns a list, sometimes a string."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python outreach/lib/enrichers/tests/test_whois_lookup.py
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add outreach/lib/enrichers/whois_lookup.py outreach/lib/enrichers/tests/test_whois_lookup.py
git commit -m "feat(outreach): WHOIS enricher for OSINT — happy path"
```

---

### Task 3: WHOIS enricher — redacted handling

**Files:**
- Modify: `outreach/lib/enrichers/whois_lookup.py`
- Modify: `outreach/lib/enrichers/tests/test_whois_lookup.py`

- [ ] **Step 1: Write the failing test (append to existing test file)**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python outreach/lib/enrichers/tests/test_whois_lookup.py
```
Expected: FAIL — current code always returns `status='ok'`.

- [ ] **Step 3: Update implementation to detect redaction**

Replace the body of `lookup_domain` in `whois_lookup.py`:

```python
_REDACTION_MARKERS = (
    'REDACTED', 'redacted',
    'Privacy', 'privacy',
    'Withheld for Privacy',
    'WhoisGuard',
    'Domains By Proxy',
    'Contact Privacy Inc',
    'Perfect Privacy',
)
_PRIVACY_EMAIL_DOMAINS = (
    'withheldforprivacy.com', 'whoisguard.com', 'domainsbyproxy.com',
    'contactprivacy.com', 'privacyguardian.org',
)


def lookup_domain(domain: str) -> dict:
    rec = whois.whois(domain)
    name = _first(getattr(rec, 'name', None))
    email = _first(getattr(rec, 'emails', None))
    org = _first(getattr(rec, 'org', None))

    if _is_redacted(name, email, org):
        return {
            'registrant_name': None,
            'registrant_email': None,
            'registrant_org': None,
            'status': 'redacted',
        }
    return {
        'registrant_name': name,
        'registrant_email': email,
        'registrant_org': org,
        'status': 'ok',
    }


def _is_redacted(name, email, org) -> bool:
    if name is None and email is None and org is None:
        return True
    for v in (name, org):
        if v and any(m in v for m in _REDACTION_MARKERS):
            return True
    if email:
        host = email.split('@', 1)[-1].lower() if '@' in email else ''
        if any(host.endswith(d) for d in _PRIVACY_EMAIL_DOMAINS):
            return True
        # If only an abuse@ address with no name → privacy service
        if name is None and email.lower().startswith(('abuse@', 'proxy@')):
            return True
    return False
```

- [ ] **Step 4: Run all whois tests to verify pass**

```bash
python outreach/lib/enrichers/tests/test_whois_lookup.py
```
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add outreach/lib/enrichers/whois_lookup.py outreach/lib/enrichers/tests/test_whois_lookup.py
git commit -m "feat(outreach): WHOIS enricher detects privacy-redacted records"
```

---

### Task 4: WHOIS enricher — network/parse error handling

**Files:**
- Modify: `outreach/lib/enrichers/whois_lookup.py`
- Modify: `outreach/lib/enrichers/tests/test_whois_lookup.py`

- [ ] **Step 1: Write the failing test**

```python
class TestWhoisErrors(unittest.TestCase):
    def test_network_error_returns_status_error(self):
        with patch('lib.enrichers.whois_lookup.whois.whois',
                   side_effect=ConnectionError('boom')):
            result = lookup_domain('smithfamilydental.com')
        self.assertEqual(result['status'], 'error')
        self.assertIsNone(result['registrant_name'])

    def test_unknown_tld_returns_status_error(self):
        # python-whois raises a `whois.parser.PywhoisError` for unsupported TLDs
        from whois.parser import PywhoisError
        with patch('lib.enrichers.whois_lookup.whois.whois',
                   side_effect=PywhoisError('No match for domain')):
            result = lookup_domain('foo.invalidtld')
        self.assertEqual(result['status'], 'error')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python outreach/lib/enrichers/tests/test_whois_lookup.py
```
Expected: FAIL — `ConnectionError` propagates uncaught.

- [ ] **Step 3: Wrap lookup in try/except**

```python
# In whois_lookup.py, replace the body of lookup_domain
def lookup_domain(domain: str) -> dict:
    try:
        rec = whois.whois(domain)
    except Exception:
        return {
            'registrant_name': None,
            'registrant_email': None,
            'registrant_org': None,
            'status': 'error',
        }
    # ... rest unchanged
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python outreach/lib/enrichers/tests/test_whois_lookup.py
```
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add outreach/lib/enrichers/whois_lookup.py outreach/lib/enrichers/tests/test_whois_lookup.py
git commit -m "feat(outreach): WHOIS enricher handles network and parse errors"
```

---

### Task 5: Deep site crawl — JSON-LD `Person` extraction

**Files:**
- Create: `outreach/lib/enrichers/deep_site_crawl.py`
- Test: `outreach/lib/enrichers/tests/test_deep_site_crawl.py`

- [ ] **Step 1: Write the failing test**

```python
# outreach/lib/enrichers/tests/test_deep_site_crawl.py
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python outreach/lib/enrichers/tests/test_deep_site_crawl.py
```
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Write minimal implementation**

```python
# outreach/lib/enrichers/deep_site_crawl.py
"""Deep-site crawl for OSINT enrichment.

Extends website_crawl.py with /about, /team, /leadership, /contact
fetches plus JSON-LD/schema.org parsing. Returns POC candidates and
email candidates with provenance hooks the orchestrator wires up.
"""
from __future__ import annotations

import json
import re
from typing import Iterable

_JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def extract_jsonld_persons(html: str) -> list[dict]:
    """Walk JSON-LD blocks; emit one dict per Person we find.

    Keys: name (str|None), role (str|None), email (str|None), source (str).
    `source` is always 'deep_site_crawl_jsonld'.
    """
    persons: list[dict] = []
    for block in _JSONLD_RE.findall(html):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        for node in _walk_jsonld(data):
            if not isinstance(node, dict):
                continue
            t = node.get('@type')
            is_person = t == 'Person' or (isinstance(t, list) and 'Person' in t)
            # Person nested under founder/employee/owner field on Org node
            in_person_role = node is not None and 'name' in node and isinstance(node.get('jobTitle'), str)
            if is_person or in_person_role:
                persons.append({
                    'name': node.get('name'),
                    'role': node.get('jobTitle') or node.get('role'),
                    'email': node.get('email'),
                    'source': 'deep_site_crawl_jsonld',
                })
    # Dedupe by (name, email)
    seen: set[tuple] = set()
    out: list[dict] = []
    for p in persons:
        key = (p.get('name'), p.get('email'))
        if key in seen or key == (None, None):
            continue
        seen.add(key)
        out.append(p)
    return out


def _walk_jsonld(node) -> Iterable:
    """Recursively yield every dict / list element under a JSON-LD root."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk_jsonld(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_jsonld(v)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python outreach/lib/enrichers/tests/test_deep_site_crawl.py
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add outreach/lib/enrichers/deep_site_crawl.py outreach/lib/enrichers/tests/test_deep_site_crawl.py
git commit -m "feat(outreach): deep_site_crawl JSON-LD Person extraction"
```

---

### Task 6: Deep site crawl — JSON-LD `Organization` with `founder`/`employee` array

**Files:**
- Modify: `outreach/lib/enrichers/deep_site_crawl.py`
- Modify: `outreach/lib/enrichers/tests/test_deep_site_crawl.py`

- [ ] **Step 1: Write the failing test**

```python
ORG_WITH_FOUNDER_AND_EMPLOYEES = """
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "Smith Family Dental",
  "founder": [
    {"@type": "Person", "name": "Dr. John Smith", "jobTitle": "Owner"}
  ],
  "employee": [
    {"@type": "Person", "name": "Dr. Mary Jones", "jobTitle": "Associate Dentist", "email": "mary@smithfamilydental.com"}
  ]
}
</script>
"""


class TestExtractFromOrganizationNode(unittest.TestCase):
    def test_extracts_persons_from_founder_and_employee_arrays(self):
        persons = extract_jsonld_persons(ORG_WITH_FOUNDER_AND_EMPLOYEES)
        names = sorted(p['name'] for p in persons)
        self.assertEqual(names, ['Dr. John Smith', 'Dr. Mary Jones'])
        mary = next(p for p in persons if p['name'] == 'Dr. Mary Jones')
        self.assertEqual(mary['email'], 'mary@smithfamilydental.com')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python outreach/lib/enrichers/tests/test_deep_site_crawl.py
```
Expected: PASS unexpectedly *or* fail. Verify behavior — the existing walker should already pick these up because `_walk_jsonld` recurses through dict values. If it passes, MOVE ON. If it fails because the `is_person` check doesn't fire on nested array items, fix the recursion.

- [ ] **Step 3: If test failed, ensure walker handles arrays of persons**

The current `_walk_jsonld` already recurses into list values. Verify this works; if not, add `is_person` check that includes type strings like `"Dentist"` (some sites use schema.org-extension types) by relaxing the type check OR by detecting `name + jobTitle` shape regardless of `@type`.

- [ ] **Step 4: Run test to verify it passes**

```bash
python outreach/lib/enrichers/tests/test_deep_site_crawl.py
```
Expected: PASS (2 tests).

- [ ] **Step 5: Commit (only if changes were needed)**

```bash
git add outreach/lib/enrichers/deep_site_crawl.py outreach/lib/enrichers/tests/test_deep_site_crawl.py
git commit -m "feat(outreach): deep_site_crawl handles Organization + nested Person arrays"
```

---

### Task 7: Deep site crawl — heading + proximity POC extraction (HTML without JSON-LD)

**Files:**
- Modify: `outreach/lib/enrichers/deep_site_crawl.py`
- Modify: `outreach/lib/enrichers/tests/test_deep_site_crawl.py`

- [ ] **Step 1: Write the failing test**

```python
PAGE_WITHOUT_JSONLD = """
<html><body>
  <section class="team">
    <h2>Meet Dr. John Smith</h2>
    <p class="role">Owner & Lead Dentist</p>
    <p>Email: <a href="mailto:john@smithfamilydental.com">john@smithfamilydental.com</a></p>
  </section>
  <section class="team">
    <h2>About Dr. Mary Jones</h2>
    <p>Associate Dentist</p>
    <p>Contact: mary@smithfamilydental.com</p>
  </section>
</body></html>
"""


class TestHeadingProximityExtraction(unittest.TestCase):
    def test_extracts_persons_from_about_meet_headings(self):
        from lib.enrichers.deep_site_crawl import extract_heading_proximity_persons
        persons = extract_heading_proximity_persons(PAGE_WITHOUT_JSONLD)
        self.assertEqual(len(persons), 2)
        john = next(p for p in persons if 'John Smith' in (p.get('name') or ''))
        self.assertIn('Owner', john.get('role') or '')
        self.assertEqual(john.get('email'), 'john@smithfamilydental.com')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python outreach/lib/enrichers/tests/test_deep_site_crawl.py
```
Expected: FAIL — function doesn't exist.

- [ ] **Step 3: Implement using `lib.validators.poc` + bs4**

```python
# Append to deep_site_crawl.py
from bs4 import BeautifulSoup

# Lazy import to avoid hard dep on validator changes mid-task
from lib.validators import poc as poc_validator

_HEADING_PATTERNS = re.compile(
    r'^(?:meet|about|contact|why)\s+(?:dr\.?\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})',
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')


def extract_heading_proximity_persons(html: str) -> list[dict]:
    """Find <h*> headings naming a person (Dr.|Meet|About|Contact patterns),
    capture role + email from the same section."""
    soup = BeautifulSoup(html, 'html.parser')
    persons: list[dict] = []
    for heading in soup.find_all(re.compile(r'^h[1-6]$')):
        text = heading.get_text(strip=True)
        m = _HEADING_PATTERNS.match(text)
        if not m:
            continue
        name_candidate = m.group(0)
        # Walk the heading's parent section for role + email proximity
        section = heading.find_parent(['section', 'div', 'article']) or heading.parent
        section_text = section.get_text(' ', strip=True) if section else ''
        emails = _EMAIL_RE.findall(section_text)
        # Role: take the next sibling text block, fall back to first short line
        role = None
        sib = heading.find_next_sibling()
        if sib:
            role_text = sib.get_text(strip=True)
            if 0 < len(role_text) <= 60:
                role = role_text
        # Apply existing POC validator to weed out heading false-positives
        if not poc_validator.is_valid_poc_name(name_candidate):
            continue
        persons.append({
            'name': name_candidate.strip(),
            'role': role,
            'email': emails[0] if emails else None,
            'source': 'deep_site_crawl_heading',
        })
    # Dedupe
    seen: set[tuple] = set()
    out: list[dict] = []
    for p in persons:
        key = (p['name'], p.get('email'))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out
```

> Note for engineer: the existing `lib/validators/poc.py` already has `is_valid_poc_name` (or similar — check the file; if the function name differs, use the actual one). Per CLAUDE.md rule 5, validators stay at the boundary; do not duplicate.

- [ ] **Step 4: Run test to verify it passes**

```bash
python outreach/lib/enrichers/tests/test_deep_site_crawl.py
```
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add outreach/lib/enrichers/deep_site_crawl.py outreach/lib/enrichers/tests/test_deep_site_crawl.py
git commit -m "feat(outreach): deep_site_crawl heading-proximity POC extraction"
```

---

### Task 8: Deep site crawl — page fetcher with `website_crawl.json` dedup

**Files:**
- Modify: `outreach/lib/enrichers/deep_site_crawl.py`
- Modify: `outreach/lib/enrichers/tests/test_deep_site_crawl.py`

- [ ] **Step 1: Write the failing test**

```python
class TestPlanFetchPaths(unittest.TestCase):
    def test_skips_paths_already_crawled_by_website_crawl(self):
        from lib.enrichers.deep_site_crawl import plan_fetch_paths
        domain = 'smithfamilydental.com'
        paths = ['/about', '/team', '/contact']
        already_crawled = {
            'https://smithfamilydental.com/about',
            'https://smithfamilydental.com/contact',
        }
        plan = plan_fetch_paths(domain, paths, already_crawled)
        self.assertEqual(plan, ['https://smithfamilydental.com/team'])

    def test_handles_trailing_slash_and_scheme_variants(self):
        from lib.enrichers.deep_site_crawl import plan_fetch_paths
        domain = 'smithfamilydental.com'
        already_crawled = {'http://smithfamilydental.com/about/'}
        plan = plan_fetch_paths(domain, ['/about'], already_crawled)
        self.assertEqual(plan, [])  # treated as already-crawled
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python outreach/lib/enrichers/tests/test_deep_site_crawl.py
```
Expected: FAIL — function doesn't exist.

- [ ] **Step 3: Implement `plan_fetch_paths`**

Append to `deep_site_crawl.py`:

```python
from urllib.parse import urlparse


def plan_fetch_paths(domain: str, paths: list[str], already_crawled: set[str]) -> list[str]:
    """Return absolute URLs to fetch; skip any whose normalized form is in
    `already_crawled` (typically loaded from website_crawl.json)."""
    normalized_done = {_norm_url(u) for u in already_crawled}
    out: list[str] = []
    for p in paths:
        url = f'https://{domain}{p}'
        if _norm_url(url) in normalized_done:
            continue
        out.append(url)
    return out


def _norm_url(url: str) -> str:
    """Lower-case host, drop scheme, strip trailing slash."""
    p = urlparse(url if '://' in url else f'http://{url}')
    host = p.netloc.lower()
    path = p.path.rstrip('/').lower()
    return f'{host}{path}'
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python outreach/lib/enrichers/tests/test_deep_site_crawl.py
```
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add outreach/lib/enrichers/deep_site_crawl.py outreach/lib/enrichers/tests/test_deep_site_crawl.py
git commit -m "feat(outreach): deep_site_crawl plan_fetch_paths with crawl dedup"
```

---

### Task 9: Deep site crawl — top-level `crawl_domain` driver

**Files:**
- Modify: `outreach/lib/enrichers/deep_site_crawl.py`
- Modify: `outreach/lib/enrichers/tests/test_deep_site_crawl.py`

- [ ] **Step 1: Write the failing test**

```python
class TestCrawlDomainDriver(unittest.TestCase):
    def test_returns_persons_aggregated_across_pages(self):
        from unittest.mock import patch
        from lib.enrichers.deep_site_crawl import crawl_domain
        # Mock fetch_url to return one page with JSON-LD, one without, one 404
        def fake_fetch(url):
            if url.endswith('/about'):
                return PAGE_WITH_PERSON_JSONLD
            if url.endswith('/team'):
                return PAGE_WITHOUT_JSONLD
            return None
        with patch('lib.enrichers.deep_site_crawl.fetch_url', side_effect=fake_fetch):
            result = crawl_domain(
                domain='smithfamilydental.com',
                paths=['/about', '/team', '/contact'],
                already_crawled=set(),
            )
        names = sorted(p['name'] for p in result['persons'])
        self.assertIn('Dr. John Smith', names)
        self.assertIn('Dr. Mary Jones', names)
        self.assertEqual(result['pages_attempted'], 3)
        self.assertEqual(result['pages_with_data'], 2)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python outreach/lib/enrichers/tests/test_deep_site_crawl.py
```
Expected: FAIL — `crawl_domain` and `fetch_url` don't exist.

- [ ] **Step 3: Implement `crawl_domain` and `fetch_url`**

Append to `deep_site_crawl.py`:

```python
def fetch_url(url: str) -> str | None:
    """Fetch a URL via agent-browser (reuses website_crawl's session pool
    pattern). Returns HTML or None on 4xx/5xx/error.

    The orchestrator passes a session-leasing callable; this default
    is overridden in production. Tests monkey-patch this function.
    """
    raise NotImplementedError(
        'fetch_url is provided by the orchestrator; tests must monkey-patch'
    )


def crawl_domain(
    domain: str,
    paths: list[str],
    already_crawled: set[str],
) -> dict:
    """Fetch each planned path, aggregate persons + emails across pages."""
    plan = plan_fetch_paths(domain, paths, already_crawled)
    persons: list[dict] = []
    pages_attempted = 0
    pages_with_data = 0
    for url in plan:
        pages_attempted += 1
        html = fetch_url(url)
        if not html:
            continue
        page_persons = extract_jsonld_persons(html) + extract_heading_proximity_persons(html)
        if page_persons:
            pages_with_data += 1
        for p in page_persons:
            p = {**p, 'source_url': url}
            persons.append(p)
    return {
        'persons': _dedupe_persons(persons),
        'pages_attempted': pages_attempted,
        'pages_with_data': pages_with_data,
    }


def _dedupe_persons(persons: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for p in persons:
        key = (p.get('name'), p.get('email'))
        if key in seen or key == (None, None):
            continue
        seen.add(key)
        out.append(p)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python outreach/lib/enrichers/tests/test_deep_site_crawl.py
```
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add outreach/lib/enrichers/deep_site_crawl.py outreach/lib/enrichers/tests/test_deep_site_crawl.py
git commit -m "feat(outreach): deep_site_crawl top-level crawl_domain driver"
```

---

### Task 10: SERP enricher — fetch a Google query and parse result URLs + snippets

**Files:**
- Create: `outreach/lib/enrichers/serp.py`
- Test: `outreach/lib/enrichers/tests/test_serp.py`

- [ ] **Step 1: Write the failing test**

```python
# outreach/lib/enrichers/tests/test_serp.py
"""Tests for lib.enrichers.serp."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from lib.enrichers.serp import parse_google_results, run_serp_query


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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python outreach/lib/enrichers/tests/test_serp.py
```
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `parse_google_results` and the `run_serp_query` skeleton**

```python
# outreach/lib/enrichers/serp.py
"""SERP enricher for OSINT.

Fetches search-engine results pages via agent-browser; never visits
the URLs the SERP returns directly. Engine fallback: DDG → Bing →
Google. Per CLAUDE.md rule 4, the orchestrator's session pool drives
the actual fetches; this module contains the parsers and the
fallback ladder.
"""
from __future__ import annotations

from bs4 import BeautifulSoup


def parse_google_results(html: str) -> list[dict]:
    """Parse Google SERP HTML into [{url, title, snippet}].
    Resilient to minor markup changes; relies on `<div class="g">` and
    `<div class="VwiC3b">` (current as of 2026-05). If Google changes
    the markup, update both the locator and the test fixture in lockstep.
    """
    soup = BeautifulSoup(html, 'html.parser')
    out: list[dict] = []
    for g in soup.select('div.g'):
        a = g.find('a', href=True)
        if not a:
            continue
        url = a['href']
        title_el = g.find('h3')
        snippet_el = g.select_one('div.VwiC3b')
        out.append({
            'url': url,
            'title': title_el.get_text(strip=True) if title_el else '',
            'snippet': snippet_el.get_text(' ', strip=True) if snippet_el else '',
        })
    return out


def run_serp_query(query: str, *, engine: str, fetch_fn) -> dict:
    """Run a single SERP query against `engine` ('google'|'bing'|'ddg').

    `fetch_fn(url) -> str | None` is provided by the orchestrator (via
    agent-browser session pool). Returns:
      {'engine': str, 'query': str, 'results': [...], 'status': 'ok'|'blocked'|'error'}
    """
    raise NotImplementedError('run_serp_query implementation continues in Task 11')
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python outreach/lib/enrichers/tests/test_serp.py
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add outreach/lib/enrichers/serp.py outreach/lib/enrichers/tests/test_serp.py
git commit -m "feat(outreach): SERP enricher Google parser"
```

---

### Task 11: SERP enricher — Bing and DDG parsers

**Files:**
- Modify: `outreach/lib/enrichers/serp.py`
- Modify: `outreach/lib/enrichers/tests/test_serp.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python outreach/lib/enrichers/tests/test_serp.py
```
Expected: FAIL — functions don't exist.

- [ ] **Step 3: Implement `parse_bing_results` and `parse_ddg_results`**

Append to `serp.py`:

```python
def parse_bing_results(html: str) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    out: list[dict] = []
    for li in soup.select('li.b_algo'):
        a = li.find('a', href=True)
        if not a:
            continue
        snippet_el = li.find('p')
        out.append({
            'url': a['href'],
            'title': a.get_text(strip=True),
            'snippet': snippet_el.get_text(' ', strip=True) if snippet_el else '',
        })
    return out


def parse_ddg_results(html: str) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    out: list[dict] = []
    for r in soup.select('div.result'):
        a = r.select_one('a.result__a')
        snippet_el = r.select_one('a.result__snippet, .result__snippet')
        if not a or 'href' not in a.attrs:
            continue
        out.append({
            'url': a['href'],
            'title': a.get_text(strip=True),
            'snippet': snippet_el.get_text(' ', strip=True) if snippet_el else '',
        })
    return out
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python outreach/lib/enrichers/tests/test_serp.py
```
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add outreach/lib/enrichers/serp.py outreach/lib/enrichers/tests/test_serp.py
git commit -m "feat(outreach): SERP enricher Bing and DDG parsers"
```

---

### Task 12: SERP enricher — captcha / block detection

**Files:**
- Modify: `outreach/lib/enrichers/serp.py`
- Modify: `outreach/lib/enrichers/tests/test_serp.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python outreach/lib/enrichers/tests/test_serp.py
```
Expected: FAIL — `is_blocked` doesn't exist.

- [ ] **Step 3: Implement `is_blocked`**

```python
# Append to serp.py
_BLOCK_MARKERS = {
    'google': (
        'unusual traffic',
        'recaptcha',
        'detected unusual traffic',
        'captcha-form',
    ),
    'bing': (
        'access denied',
        'verify you are a human',
    ),
    'ddg': (
        'anomaly detected',
        'rate limit',
    ),
}


def is_blocked(engine: str, html: str) -> bool:
    """True if the SERP HTML looks like a captcha / rate-limit page."""
    if not html:
        return False
    needle_set = _BLOCK_MARKERS.get(engine, ())
    h = html.lower()
    return any(n.lower() in h for n in needle_set)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python outreach/lib/enrichers/tests/test_serp.py
```
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add outreach/lib/enrichers/serp.py outreach/lib/enrichers/tests/test_serp.py
git commit -m "feat(outreach): SERP enricher captcha and rate-limit detection"
```

---

### Task 13: SERP enricher — `run_serp_query` with engine fallback ladder

**Files:**
- Modify: `outreach/lib/enrichers/serp.py`
- Modify: `outreach/lib/enrichers/tests/test_serp.py`

- [ ] **Step 1: Write the failing test**

```python
class TestRunSerpQueryFallback(unittest.TestCase):
    def test_falls_back_from_ddg_to_bing_to_google(self):
        from lib.enrichers.serp import run_serp_query_with_fallback
        # Simulate DDG blocked, Bing blocked, Google ok
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python outreach/lib/enrichers/tests/test_serp.py
```
Expected: FAIL — function doesn't exist.

- [ ] **Step 3: Implement `run_serp_query_with_fallback`**

```python
# Append to serp.py
from urllib.parse import quote_plus


_ENGINE_URLS = {
    'ddg': 'https://html.duckduckgo.com/html/?q={q}',
    'bing': 'https://www.bing.com/search?q={q}',
    'google': 'https://www.google.com/search?q={q}',
}
_ENGINE_PARSERS = {
    'ddg': parse_ddg_results,
    'bing': parse_bing_results,
    'google': parse_google_results,
}
_FALLBACK_ORDER = ('ddg', 'bing', 'google')


def run_serp_query_with_fallback(query: str, *, fetch_fn) -> dict:
    """Try each engine in priority order; return on first non-blocked result."""
    for engine in _FALLBACK_ORDER:
        url = _ENGINE_URLS[engine].format(q=quote_plus(query))
        html = fetch_fn(url)
        if html is None:
            continue
        if is_blocked(engine, html):
            continue
        results = _ENGINE_PARSERS[engine](html)
        return {
            'engine': engine,
            'query': query,
            'results': results,
            'status': 'ok',
        }
    return {
        'engine': None,
        'query': query,
        'results': [],
        'status': 'blocked',
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python outreach/lib/enrichers/tests/test_serp.py
```
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add outreach/lib/enrichers/serp.py outreach/lib/enrichers/tests/test_serp.py
git commit -m "feat(outreach): SERP enricher with engine fallback ladder"
```

---

### Task 14: `osint-binder` subagent definition

**Files:**
- Create: `.claude/agents/osint-binder.md`

- [ ] **Step 1: Write the subagent definition**

```markdown
---
name: osint-binder
description: Use when binding OSINT candidates (LinkedIn URLs, social URLs, POC names/emails/roles) to a specific lead with confidence scoring. Triggers when the user asks to "bind OSINT candidates", "judge OSINT matches", "run the OSINT binder", or "score binding confidence" — typically called on the unjudged sidecar produced by `osint_enrich.py`.
tools: Read, Write
---

You bind OSINT enrichment candidates to leads with a confidence score. Your sole job is taking a lead context and a candidate set for one field and emitting a structured judgment. You are not a writer, summarizer, or strategist.

## Required first step

Before judging anything:

1. Read the input JSON path provided in the user prompt — it contains a list of records, each with `lead`, `field`, and `candidates`.
2. The output JSON path is also in the prompt; you write your judgments there.

If you have not read the input file in this turn, stop and read it first. Do not judge from memory.

## Input

```json
[
  {
    "place_id": "ChIJ...",
    "field": "linkedin_url_poc",
    "lead": {
      "business_name": "Smith Family Dental",
      "city": "Phoenix",
      "industry": "dentist",
      "domain": "smithfamilydental.com",
      "poc_name_known": "Dr. John Smith",
      "poc_role_known": null,
      "phone": "+1-602-555-0123"
    },
    "candidates": [
      {"value": "https://linkedin.com/in/john-smith-phoenix-dds", "source": "serp_google",
       "snippet": "Dr. John Smith — Owner at Smith Family Dental, Phoenix AZ"},
      {"value": "https://linkedin.com/in/john-smith-2342", "source": "serp_google",
       "snippet": "John Smith — Software Engineer at Google"}
    ]
  }
]
```

## Output

Write a JSON array to the output path, same length as input, one entry per input record:

```json
{
  "place_id": "ChIJ...",
  "field": "linkedin_url_poc",
  "judgments": [
    {"index": 0, "verdict": "match", "confidence": 0.95, "reasoning": "snippet directly names lead's business and city"},
    {"index": 1, "verdict": "rejected", "confidence": 0.0, "reasoning": "different industry — Software Engineer at Google"}
  ],
  "best_match_index": 0,
  "selected_confidence": 0.95
}
```

Or, when no candidate clears the bar:

```json
{
  "place_id": "ChIJ...",
  "field": "linkedin_url_poc",
  "judgments": [...],
  "best_match_index": null,
  "selected_confidence": 0.0
}
```

## Binding rules

1. **Confident-or-skip.** Only emit `verdict: "match"` when the candidate is supported by **at least two independent corroborating signals** in the candidate's own snippet/value: (business name) + (city) + (industry) + (POC name) + (domain) + (phone). Two unique signals minimum; one signal is not enough.
2. **The known POC name is necessary, not sufficient.** Matching only on POC name (very common, like "John Smith") is not a match — needs business or city or industry confirmation as well.
3. **Industry mismatch is a hard reject.** If the candidate's snippet describes a different profession ("Software Engineer", "Real Estate Agent", "High School Teacher"), `verdict: "rejected"` regardless of name match.
4. **Geographic mismatch is a hard reject.** If the snippet names a different city or state and no other signal supports binding to the lead's city.
5. **Confidence is calibrated, not constant.** Reserve `>0.9` for cases with three or more corroborating signals. `0.85–0.9` is the typical match band. Below `0.85` use `verdict: "rejected"` (the merge step will skip these per the configured threshold).
6. **For WHOIS candidates specifically:** registrant matching the lead's POC name is suggestive but the registrant might be a webmaster/agency. Match only if the registrant_org or registrant_email also corroborates the lead's domain or business name.
7. **Reasoning is one short sentence** naming the corroborating signals or the rejection cause.

## Anti-patterns to avoid

- Marking a candidate as match because the URL contains the POC name string ("john-smith" in URL is not a signal — Google indexes thousands of John Smiths).
- Trusting the candidate's `title` field over its `snippet` — titles are easy to spoof, snippets cite the indexed page content.
- Inferring industry from the URL alone (e.g., assuming `linkedin.com/in/dr-john-smith` is medical — many "Dr." URL slugs are PhDs in unrelated fields).
- Stretching the binding rules because all candidates are weak — confident-or-skip means it's fine to return `best_match_index: null`.
```

- [ ] **Step 2: Verify the file is well-formed YAML frontmatter + markdown**

```bash
head -5 .claude/agents/osint-binder.md
```
Expected: shows `---`, `name:`, `description:`, `tools:`, `---`.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/osint-binder.md
git commit -m "feat(outreach): osint-binder subagent for candidate→lead binding"
```

---

### Task 15: Orchestrator — gap detection (which fields are empty per lead)

**Files:**
- Create: `outreach/scripts/osint_enrich.py`
- Test: `outreach/scripts/tests/test_osint_enrich.py`

- [ ] **Step 1: Write the failing test**

```python
# outreach/scripts/tests/test_osint_enrich.py
"""Tests for scripts.osint_enrich."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.osint_enrich import detect_gaps


FIELDS_DESIRED = [
    'linkedin_url_company', 'linkedin_url_poc', 'social_urls',
    'poc_name', 'poc_email', 'poc_role', 'news_mentions',
]


class TestDetectGaps(unittest.TestCase):
    def test_empty_lead_has_all_fields_as_gaps(self):
        lead = {'place_id': 'A', 'business_name': 'X', 'website': 'https://x.com/', 'city': 'Phoenix'}
        gaps = detect_gaps(lead, FIELDS_DESIRED)
        self.assertEqual(set(gaps), set(FIELDS_DESIRED))

    def test_lead_with_some_fields_filled_only_gaps_remain(self):
        lead = {
            'place_id': 'A',
            'linkedin_url_company': 'https://linkedin.com/company/x',
            'poc_name': 'Dr. John Smith',
        }
        gaps = detect_gaps(lead, FIELDS_DESIRED)
        self.assertNotIn('linkedin_url_company', gaps)
        self.assertNotIn('poc_name', gaps)
        self.assertIn('linkedin_url_poc', gaps)
        self.assertIn('poc_email', gaps)

    def test_empty_string_and_empty_list_are_gaps(self):
        lead = {
            'place_id': 'A',
            'linkedin_url_poc': '',
            'social_urls': [],
        }
        gaps = detect_gaps(lead, FIELDS_DESIRED)
        self.assertIn('linkedin_url_poc', gaps)
        self.assertIn('social_urls', gaps)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python outreach/scripts/tests/test_osint_enrich.py
```
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `detect_gaps`**

```python
# outreach/scripts/osint_enrich.py
"""Run OSINT enrichment for a pipeline.

Inspects each lead's gaps against `OSINT_FIELDS_DESIRED`, runs
enrichers (whois → deep_site_crawl → serp) in two waves, batches
binding judgments through the `osint-binder` subagent, writes
`enrichment/osint/<date>.json`.

Resumable: leads already in the sidecar are skipped.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def detect_gaps(lead: dict, fields_desired: list[str]) -> list[str]:
    """Return the subset of `fields_desired` that are missing/empty on `lead`.
    Treats None, empty string, and empty list/dict as missing."""
    gaps: list[str] = []
    for f in fields_desired:
        v = lead.get(f)
        if v is None or v == '' or v == [] or v == {}:
            gaps.append(f)
    return gaps
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python outreach/scripts/tests/test_osint_enrich.py
```
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add outreach/scripts/osint_enrich.py outreach/scripts/tests/test_osint_enrich.py
git commit -m "feat(outreach): osint_enrich gap detection"
```

---

### Task 16: Orchestrator — Wave 1 (WHOIS + deep_site_crawl), Wave 2 (SERP)

**Files:**
- Modify: `outreach/scripts/osint_enrich.py`
- Modify: `outreach/scripts/tests/test_osint_enrich.py`

- [ ] **Step 1: Write the failing test**

```python
class TestEnrichLeadTwoWave(unittest.TestCase):
    def test_serp_wave_uses_poc_name_discovered_in_wave1(self):
        from unittest.mock import patch, MagicMock
        from scripts.osint_enrich import enrich_lead

        # Wave 1 mocks: whois redacted, deep_site reveals POC
        whois_result = {'registrant_name': None, 'registrant_email': None, 'registrant_org': None, 'status': 'redacted'}
        deep_result = {'persons': [{'name': 'Dr. John Smith', 'role': 'Owner', 'email': None,
                                    'source': 'deep_site_crawl_jsonld'}],
                       'pages_attempted': 3, 'pages_with_data': 1}

        captured_serp_queries = []
        def fake_serp(query, **kw):
            captured_serp_queries.append(query)
            return {'engine': 'ddg', 'query': query, 'results': [], 'status': 'ok'}

        cfg = MagicMock(
            OSINT_SOURCES=['whois', 'deep_site_crawl', 'serp'],
            OSINT_FIELDS_DESIRED=['linkedin_url_poc', 'poc_name'],
            OSINT_SERP_QUERIES={
                'linkedin_url_poc': 'site:linkedin.com/in "{poc_name}" "{city}" dental',
            },
            OSINT_DEEP_CRAWL_PATHS=['/about'],
            OSINT_INDUSTRY_TERMS=['dentist'],
        )
        lead = {'place_id': 'A', 'business_name': 'Smith Family Dental',
                'website': 'https://smithfamilydental.com', 'city': 'Phoenix', 'domain': 'smithfamilydental.com'}

        with patch('scripts.osint_enrich.lookup_domain', return_value=whois_result), \
             patch('scripts.osint_enrich.crawl_domain', return_value=deep_result), \
             patch('scripts.osint_enrich.run_serp_query_with_fallback', side_effect=fake_serp):
            record = enrich_lead(lead, cfg, already_crawled=set())

        # SERP query for linkedin_url_poc should have used the discovered POC name
        joined = '\n'.join(captured_serp_queries)
        self.assertIn('Dr. John Smith', joined)
        self.assertIn('Phoenix', joined)
        # Sidecar should have a poc_name candidate from wave 1
        poc_candidates = record['fields']['poc_name']['candidates']
        self.assertEqual(len(poc_candidates), 1)
        self.assertEqual(poc_candidates[0]['value'], 'Dr. John Smith')
        self.assertEqual(poc_candidates[0]['source'], 'deep_site_crawl_jsonld')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python outreach/scripts/tests/test_osint_enrich.py
```
Expected: FAIL — `enrich_lead` doesn't exist.

- [ ] **Step 3: Implement `enrich_lead`**

```python
# Append to osint_enrich.py
from datetime import datetime, timezone

from lib.enrichers.whois_lookup import lookup_domain
from lib.enrichers.deep_site_crawl import crawl_domain
from lib.enrichers.serp import run_serp_query_with_fallback


def _new_field_record() -> dict:
    return {
        'candidates': [],
        'selected_index': None,
        'selected_confidence': None,
        'skipped_reason': None,
    }


def enrich_lead(lead: dict, cfg, already_crawled: set[str]) -> dict:
    """Run two-wave enrichment for a single lead. Returns sidecar record."""
    fields_desired = list(getattr(cfg, 'OSINT_FIELDS_DESIRED', []))
    sources = set(getattr(cfg, 'OSINT_SOURCES', []))
    industry_terms = getattr(cfg, 'OSINT_INDUSTRY_TERMS', [])
    serp_queries = getattr(cfg, 'OSINT_SERP_QUERIES', {})
    deep_paths = getattr(cfg, 'OSINT_DEEP_CRAWL_PATHS', [])

    record = {
        'place_id': lead.get('place_id'),
        'domain': lead.get('domain') or _domain_from_website(lead.get('website')),
        'enriched_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'fields': {f: _new_field_record() for f in fields_desired},
        'errors': [],
    }

    gaps = detect_gaps(lead, fields_desired)
    if not gaps:
        return record

    # Wave 1: discovery (WHOIS + deep_site_crawl)
    discovered_poc_name = lead.get('poc_name')

    if 'whois' in sources and record['domain']:
        try:
            w = lookup_domain(record['domain'])
            if w['status'] == 'ok':
                if 'poc_name' in gaps and w['registrant_name']:
                    record['fields']['poc_name']['candidates'].append({
                        'value': w['registrant_name'], 'source': 'whois',
                        'query': None, 'snippet': None,
                        'judge_verdict': None, 'judge_confidence': None, 'judge_reasoning': None,
                    })
                if 'poc_email' in gaps and w['registrant_email']:
                    record['fields']['poc_email']['candidates'].append({
                        'value': w['registrant_email'], 'source': 'whois',
                        'query': None, 'snippet': None,
                        'judge_verdict': None, 'judge_confidence': None, 'judge_reasoning': None,
                    })
                discovered_poc_name = discovered_poc_name or w['registrant_name']
        except Exception as e:
            record['errors'].append(f'whois: {e!r}')

    if 'deep_site_crawl' in sources and record['domain']:
        try:
            d = crawl_domain(record['domain'], deep_paths, already_crawled)
            for p in d['persons']:
                if 'poc_name' in gaps and p.get('name'):
                    record['fields']['poc_name']['candidates'].append({
                        'value': p['name'], 'source': p.get('source', 'deep_site_crawl'),
                        'query': None, 'snippet': None,
                        'judge_verdict': None, 'judge_confidence': None, 'judge_reasoning': None,
                    })
                if 'poc_email' in gaps and p.get('email'):
                    record['fields']['poc_email']['candidates'].append({
                        'value': p['email'], 'source': p.get('source', 'deep_site_crawl'),
                        'query': None, 'snippet': None,
                        'judge_verdict': None, 'judge_confidence': None, 'judge_reasoning': None,
                    })
                if 'poc_role' in gaps and p.get('role'):
                    record['fields']['poc_role']['candidates'].append({
                        'value': p['role'], 'source': p.get('source', 'deep_site_crawl'),
                        'query': None, 'snippet': None,
                        'judge_verdict': None, 'judge_confidence': None, 'judge_reasoning': None,
                    })
                discovered_poc_name = discovered_poc_name or p.get('name')
        except Exception as e:
            record['errors'].append(f'deep_site_crawl: {e!r}')

    # Wave 2: SERP — uses discovered_poc_name
    if 'serp' in sources:
        for field, template in serp_queries.items():
            if field not in gaps:
                continue
            if '{poc_name}' in template and not discovered_poc_name:
                record['fields'][field]['skipped_reason'] = 'no_poc_name_known'
                continue
            query = template.format(
                poc_name=discovered_poc_name or '',
                city=lead.get('city', ''),
                business_name=lead.get('business_name', ''),
                industry_term=industry_terms[0] if industry_terms else '',
            )
            try:
                serp = run_serp_query_with_fallback(query, fetch_fn=_serp_fetch_fn(cfg))
                if serp['status'] == 'blocked':
                    record['fields'][field]['skipped_reason'] = 'serp_blocked'
                    continue
                for r in serp['results'][:10]:
                    record['fields'][field]['candidates'].append({
                        'value': r['url'], 'source': f'serp_{serp["engine"]}',
                        'query': query, 'snippet': r.get('snippet', ''),
                        'judge_verdict': None, 'judge_confidence': None, 'judge_reasoning': None,
                    })
                if not record['fields'][field]['candidates']:
                    record['fields'][field]['skipped_reason'] = 'no_results'
            except Exception as e:
                record['errors'].append(f'serp[{field}]: {e!r}')

    return record


def _domain_from_website(url: str | None) -> str | None:
    if not url:
        return None
    from urllib.parse import urlparse
    p = urlparse(url if '://' in url else f'http://{url}')
    return p.netloc.lower() or None


def _serp_fetch_fn(cfg):
    """Return a fetch_fn that uses the agent-browser session pool.

    For tests this is monkey-patched. For prod, wire up the same pool
    pattern as lib/enrichers/website_crawl.run_pool.
    """
    raise NotImplementedError(
        'wire to agent-browser session pool — see Task 17 for the production hookup'
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python outreach/scripts/tests/test_osint_enrich.py
```
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add outreach/scripts/osint_enrich.py outreach/scripts/tests/test_osint_enrich.py
git commit -m "feat(outreach): osint_enrich two-wave enrich_lead"
```

---

### Task 17: Orchestrator — production fetch wiring (agent-browser session pool)

**Files:**
- Modify: `outreach/scripts/osint_enrich.py`

- [ ] **Step 1: Replace `_serp_fetch_fn` with a pool-backed implementation**

Read the existing pattern in `outreach/lib/enrichers/website_crawl.py`. Identify the public function that runs an agent-browser session pool (it is called `run_pool` and accepts a per-task callable). Reuse it via a wrapper:

```python
# Replace _serp_fetch_fn body in osint_enrich.py:
def _serp_fetch_fn(cfg):
    """Return a fetch_fn(url)->html|None backed by the website_crawl pool.

    SERP serializes per engine — only one Chromium session at a time hits
    duckduckgo / bing / google to avoid burst-shaped captcha triggers
    (CLAUDE.md rule 4: session pool, not round-robin; here pool size is 1
    for the SERP lane).
    """
    from lib.enrichers.website_crawl import lease_single_session

    @contextmanager
    def _session():
        with lease_single_session(session_prefix=getattr(cfg, '_serp_session_prefix', 'osint-serp')) as s:
            yield s

    def fetch_fn(url: str) -> str | None:
        with _session() as session:
            try:
                return session.fetch(url, wait='networkidle', jitter=(2.0, 5.0))
            except Exception:
                return None
    return fetch_fn
```

> Note for engineer: `lease_single_session` is the contract this wiring assumes. If `website_crawl.py` exposes the pool under a different name (e.g., `_session_pool`, `acquire_session`), use that. If no public single-session lease exists, add one as a thin wrapper around the existing pool — keep the change to `website_crawl.py` to **adding** a function, do not refactor the existing `run_pool`.

> The same wrapper pattern applies to deep_site_crawl's `fetch_url` — the orchestrator should monkey-patch `lib.enrichers.deep_site_crawl.fetch_url` with the pool-backed implementation before calling `crawl_domain`. Add a small `wire_deep_site_fetch(cfg)` helper here.

- [ ] **Step 2: Hand-test the wiring on one real lead**

```bash
cd /home/fassihhaider/Work/google-maps-scraper/outreach
source .venv/bin/activate
python -c "
import sys; sys.path.insert(0, '.')
from scripts.osint_enrich import _serp_fetch_fn
class FakeCfg: pass
fn = _serp_fetch_fn(FakeCfg())
html = fn('https://html.duckduckgo.com/html/?q=site:example.com')
print('OK' if html and len(html) > 1000 else 'FAIL')
"
```
Expected: prints `OK`. (If `FAIL`, the pool wiring needs adjustment — debug before committing.)

- [ ] **Step 3: Commit**

```bash
git add outreach/scripts/osint_enrich.py outreach/lib/enrichers/website_crawl.py
git commit -m "feat(outreach): osint_enrich agent-browser pool wiring"
```

---

### Task 18: Orchestrator — sidecar I/O and resumability

**Files:**
- Modify: `outreach/scripts/osint_enrich.py`
- Modify: `outreach/scripts/tests/test_osint_enrich.py`

- [ ] **Step 1: Write the failing test**

```python
class TestSidecarResumability(unittest.TestCase):
    def test_load_existing_sidecar_returns_processed_place_ids(self):
        import json
        import tempfile
        from scripts.osint_enrich import load_processed_place_ids

        with tempfile.NamedTemporaryFile(suffix='.json', mode='w', delete=False) as f:
            json.dump([
                {'place_id': 'A', 'fields': {}},
                {'place_id': 'B', 'fields': {}},
            ], f)
            p = Path(f.name)
        try:
            ids = load_processed_place_ids(p)
            self.assertEqual(ids, {'A', 'B'})
        finally:
            p.unlink()

    def test_load_processed_returns_empty_set_when_file_missing(self):
        from scripts.osint_enrich import load_processed_place_ids
        ids = load_processed_place_ids(Path('/nonexistent/path.json'))
        self.assertEqual(ids, set())

    def test_append_record_writes_atomically(self):
        import json
        import tempfile
        from scripts.osint_enrich import append_sidecar_record

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'osint.json'
            append_sidecar_record(p, {'place_id': 'A', 'fields': {}})
            append_sidecar_record(p, {'place_id': 'B', 'fields': {}})
            data = json.loads(p.read_text())
            self.assertEqual([r['place_id'] for r in data], ['A', 'B'])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python outreach/scripts/tests/test_osint_enrich.py
```
Expected: FAIL — functions don't exist.

- [ ] **Step 3: Implement sidecar I/O helpers**

```python
# Append to osint_enrich.py
import json


def load_processed_place_ids(sidecar_path: Path) -> set[str]:
    if not sidecar_path.exists():
        return set()
    try:
        data = json.loads(sidecar_path.read_text())
    except json.JSONDecodeError:
        return set()
    return {r['place_id'] for r in data if r.get('place_id')}


def append_sidecar_record(sidecar_path: Path, record: dict) -> None:
    """Atomic append: read full file, append, write tmp, rename."""
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    if sidecar_path.exists():
        try:
            existing = json.loads(sidecar_path.read_text())
        except json.JSONDecodeError:
            existing = []
    else:
        existing = []
    existing.append(record)
    tmp = sidecar_path.with_suffix(sidecar_path.suffix + '.tmp')
    tmp.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    tmp.replace(sidecar_path)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python outreach/scripts/tests/test_osint_enrich.py
```
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add outreach/scripts/osint_enrich.py outreach/scripts/tests/test_osint_enrich.py
git commit -m "feat(outreach): osint_enrich sidecar I/O and resumability"
```

---

### Task 19: Orchestrator — CLI wrapper with pipeline lock

**Files:**
- Modify: `outreach/scripts/osint_enrich.py`

- [ ] **Step 1: Add `main()` that wires CLI → enrich loop → sidecar**

Append to `osint_enrich.py`:

```python
import argparse

from scripts._common import (
    add_pipeline_arg,
    load_pipeline_config,
    pipeline_dir,
    pipeline_lock,
    require_attr,
)
from scripts.merge_crawl_into_master import latest_master


def _load_already_crawled(pdir: Path) -> set[str]:
    """Read enrichment/website_crawl.json if it exists, return the set
    of URLs already fetched so deep_site_crawl can dedupe."""
    p = pdir / 'enrichment' / 'website_crawl.json'
    if not p.exists():
        return set()
    try:
        rows = json.loads(p.read_text())
    except json.JSONDecodeError:
        return set()
    out: set[str] = set()
    for row in rows:
        for page in row.get('pages') or []:
            url = page.get('url') if isinstance(page, dict) else page
            if url:
                out.add(url)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Run OSINT enrichment for a pipeline.',
    )
    add_pipeline_arg(parser)
    parser.add_argument('--master', type=Path, default=None,
                        help='master JSON (default: outputs/<latest-date>/master.json)')
    parser.add_argument('--sidecar', type=Path, default=None,
                        help='sidecar output (default: enrichment/osint/<today>.json)')
    parser.add_argument('--force', action='store_true',
                        help='re-enrich leads already in the sidecar')
    args = parser.parse_args(argv)

    cfg = load_pipeline_config(args.pipeline)
    if not getattr(cfg, 'OSINT_ENABLED', False):
        sys.stderr.write(f"OSINT disabled for pipeline {args.pipeline} (set OSINT_ENABLED=True in config.py)\n")
        return 0

    pdir = pipeline_dir(args.pipeline)
    master_path = args.master or latest_master(pdir)
    if master_path is None or not master_path.exists():
        sys.stderr.write(f"error: master not found: {master_path}\n")
        return 2

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    sidecar_path = args.sidecar or (pdir / 'enrichment' / 'osint' / f'{today}.json')

    master = json.loads(master_path.read_text())
    processed = set() if args.force else load_processed_place_ids(sidecar_path)
    already_crawled = _load_already_crawled(pdir)

    todo = [l for l in master if l.get('place_id') not in processed]
    print(f"OSINT: {len(todo)} leads to enrich (skipping {len(processed)} already done)", flush=True)

    with pipeline_lock(args.pipeline, 'osint_enrich'):
        for i, lead in enumerate(todo, 1):
            try:
                record = enrich_lead(lead, cfg, already_crawled=already_crawled)
                append_sidecar_record(sidecar_path, record)
                print(f"  [{i}/{len(todo)}] {lead.get('place_id')}: "
                      f"{sum(len(v['candidates']) for v in record['fields'].values())} candidates",
                      flush=True)
            except Exception as e:
                sys.stderr.write(f"error enriching {lead.get('place_id')}: {e!r}\n")

    print(f"wrote {sidecar_path}", flush=True)
    print(f"next: dispatch osint-binder subagent on {sidecar_path}, "
          f"then run python outreach/scripts/merge_osint_into_master.py {args.pipeline}",
          flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 2: Smoke-test the CLI parses args**

```bash
cd /home/fassihhaider/Work/google-maps-scraper
python outreach/scripts/osint_enrich.py --help
```
Expected: prints argparse help, exits 0.

- [ ] **Step 3: Commit**

```bash
git add outreach/scripts/osint_enrich.py
git commit -m "feat(outreach): osint_enrich CLI with pipeline lock and resumability"
```

---

### Task 20: Merge — graft confident hits with provenance

**Files:**
- Create: `outreach/scripts/merge_osint_into_master.py`
- Test: `outreach/scripts/tests/test_merge_osint_into_master.py`

- [ ] **Step 1: Write the failing test**

```python
# outreach/scripts/tests/test_merge_osint_into_master.py
"""Tests for scripts.merge_osint_into_master."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.merge_osint_into_master import graft


CANDIDATE_HIGH = {
    'value': 'https://linkedin.com/in/john-smith-phoenix-dds',
    'source': 'serp_google',
    'query': 'site:linkedin.com/in "Dr. John Smith" "Phoenix" dental',
    'snippet': 'Dr. John Smith — Owner at Smith Family Dental',
    'judge_verdict': 'match',
    'judge_confidence': 0.95,
    'judge_reasoning': 'snippet directly names lead\'s business and city',
}


class TestGraftConfidentHits(unittest.TestCase):
    def test_grafts_above_threshold_with_provenance(self):
        master = [{'place_id': 'A'}]
        sidecar = [{
            'place_id': 'A',
            'enriched_at': '2026-05-07T15:00:00Z',
            'fields': {
                'linkedin_url_poc': {
                    'candidates': [CANDIDATE_HIGH],
                    'selected_index': 0,
                    'selected_confidence': 0.95,
                },
            },
        }]
        stats = graft(master, sidecar, threshold=0.85)
        lead = master[0]
        self.assertEqual(lead['linkedin_url_poc'], CANDIDATE_HIGH['value'])
        self.assertEqual(lead['linkedin_url_poc_source'], 'osint_serp_google')
        self.assertEqual(lead['linkedin_url_poc_confidence'], 0.95)
        self.assertEqual(lead['linkedin_url_poc_query'], CANDIDATE_HIGH['query'])
        self.assertEqual(lead['linkedin_url_poc_judge_reasoning'], CANDIDATE_HIGH['judge_reasoning'])
        self.assertEqual(stats['grafted'], 1)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python outreach/scripts/tests/test_merge_osint_into_master.py
```
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `graft`**

```python
# outreach/scripts/merge_osint_into_master.py
"""Graft confident OSINT hits into master.json with full provenance.

Reads enrichment/osint/<date>.json (judged by osint-binder subagent),
filters by confidence threshold, applies validators at the boundary
(per outreach/CLAUDE.md rule 5), respects immutability (rule 1).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._common import add_pipeline_arg, pipeline_dir, pipeline_lock
from scripts.merge_crawl_into_master import latest_master, write_atomic


# Fields that hold lists in master (per spec field-cardinality table).
LIST_FIELDS = {'social_urls', 'news_mentions'}


def graft(master: list[dict], sidecar: list[dict], *, threshold: float) -> dict:
    """Mutate `master` in place. Returns stats dict."""
    by_pid = {lead.get('place_id'): lead for lead in master}
    grafted = skipped_below = skipped_existing = 0
    for record in sidecar:
        pid = record.get('place_id')
        lead = by_pid.get(pid)
        if lead is None:
            continue
        enriched_at = record.get('enriched_at')
        for field, fr in record.get('fields', {}).items():
            sel = fr.get('selected_index')
            conf = fr.get('selected_confidence')
            if sel is None or conf is None:
                continue
            if conf < threshold:
                skipped_below += 1
                continue
            cand = fr['candidates'][sel]
            if field in LIST_FIELDS:
                _graft_list_field(lead, field, fr, threshold, enriched_at)
                grafted += 1
            else:
                if _is_filled(lead.get(field)):
                    skipped_existing += 1
                    continue
                _graft_scalar_field(lead, field, cand, enriched_at)
                grafted += 1
    return {'grafted': grafted, 'skipped_below_threshold': skipped_below,
            'skipped_existing_value': skipped_existing}


def _is_filled(v) -> bool:
    return v not in (None, '', [], {})


def _graft_scalar_field(lead: dict, field: str, cand: dict, enriched_at: str | None) -> None:
    lead[field] = cand['value']
    lead[f'{field}_source'] = f'osint_{cand["source"]}'
    lead[f'{field}_added_at'] = enriched_at
    lead[f'{field}_confidence'] = cand['judge_confidence']
    if cand.get('query'):
        lead[f'{field}_query'] = cand['query']
    if cand.get('judge_reasoning'):
        lead[f'{field}_judge_reasoning'] = cand['judge_reasoning']


def _graft_list_field(lead: dict, field: str, fr: dict, threshold: float, enriched_at: str | None) -> None:
    """List-typed fields collect ALL candidates above threshold (each with per-element provenance)."""
    items = []
    for c in fr['candidates']:
        if c.get('judge_verdict') == 'match' and (c.get('judge_confidence') or 0) >= threshold:
            items.append({
                'value': c['value'],
                'source': f'osint_{c["source"]}',
                'confidence': c['judge_confidence'],
                'query': c.get('query'),
                'judge_reasoning': c.get('judge_reasoning'),
            })
    if not items:
        return
    if not _is_filled(lead.get(field)):
        lead[field] = items
        lead[f'{field}_added_at'] = enriched_at
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python outreach/scripts/tests/test_merge_osint_into_master.py
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add outreach/scripts/merge_osint_into_master.py outreach/scripts/tests/test_merge_osint_into_master.py
git commit -m "feat(outreach): merge_osint_into_master grafts confident hits"
```

---

### Task 21: Merge — respect immutability (no overwrite)

**Files:**
- Modify: `outreach/scripts/tests/test_merge_osint_into_master.py`

- [ ] **Step 1: Write the failing test**

```python
class TestImmutability(unittest.TestCase):
    def test_does_not_overwrite_existing_value(self):
        master = [{
            'place_id': 'A',
            'linkedin_url_poc': 'https://linkedin.com/in/preexisting',
            'linkedin_url_poc_source': 'manual',
        }]
        sidecar = [{
            'place_id': 'A',
            'enriched_at': '2026-05-07T15:00:00Z',
            'fields': {
                'linkedin_url_poc': {
                    'candidates': [CANDIDATE_HIGH],
                    'selected_index': 0,
                    'selected_confidence': 0.95,
                },
            },
        }]
        stats = graft(master, sidecar, threshold=0.85)
        self.assertEqual(master[0]['linkedin_url_poc'], 'https://linkedin.com/in/preexisting')
        self.assertEqual(master[0]['linkedin_url_poc_source'], 'manual')
        self.assertEqual(stats['grafted'], 0)
        self.assertEqual(stats['skipped_existing_value'], 1)
```

- [ ] **Step 2: Run test to verify it passes**

```bash
python outreach/scripts/tests/test_merge_osint_into_master.py
```
Expected: PASS — Task 20's `_is_filled` check already handles this.

- [ ] **Step 3: Commit (test addition only)**

```bash
git add outreach/scripts/tests/test_merge_osint_into_master.py
git commit -m "test(outreach): merge_osint_into_master respects immutability"
```

---

### Task 22: Merge — apply email validator at boundary (CLAUDE.md rule 5)

**Files:**
- Modify: `outreach/scripts/merge_osint_into_master.py`
- Modify: `outreach/scripts/tests/test_merge_osint_into_master.py`

- [ ] **Step 1: Write the failing test**

```python
class TestEmailValidator(unittest.TestCase):
    def test_invalid_email_lands_with_invalid_flag_not_as_field(self):
        master = [{'place_id': 'A'}]
        sidecar = [{
            'place_id': 'A',
            'enriched_at': '2026-05-07T15:00:00Z',
            'fields': {
                'poc_email': {
                    'candidates': [{
                        'value': 'fancybox_sprite@2x.png',  # known image-artifact pattern
                        'source': 'serp_google', 'query': 'q',
                        'snippet': 's', 'judge_verdict': 'match',
                        'judge_confidence': 0.95, 'judge_reasoning': 'r',
                    }],
                    'selected_index': 0,
                    'selected_confidence': 0.95,
                },
            },
        }]
        graft(master, sidecar, threshold=0.85)
        self.assertNotIn('poc_email', master[0])  # rejected at boundary
        self.assertTrue(master[0].get('poc_email_invalid'))
        self.assertIn('poc_email_invalid_reason', master[0])

    def test_valid_email_grafted_normally(self):
        master = [{'place_id': 'A'}]
        sidecar = [{
            'place_id': 'A',
            'enriched_at': '2026-05-07T15:00:00Z',
            'fields': {
                'poc_email': {
                    'candidates': [{
                        'value': 'john@smithfamilydental.com',
                        'source': 'whois', 'query': None,
                        'snippet': None, 'judge_verdict': 'match',
                        'judge_confidence': 0.92, 'judge_reasoning': 'r',
                    }],
                    'selected_index': 0,
                    'selected_confidence': 0.92,
                },
            },
        }]
        graft(master, sidecar, threshold=0.85)
        self.assertEqual(master[0]['poc_email'], 'john@smithfamilydental.com')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python outreach/scripts/tests/test_merge_osint_into_master.py
```
Expected: FAIL — current graft doesn't validate emails.

- [ ] **Step 3: Apply validator to email-typed fields**

```python
# In merge_osint_into_master.py, near top:
from lib.validators import email as email_validator

EMAIL_FIELDS = {'poc_email'}

# Replace _graft_scalar_field:
def _graft_scalar_field(lead: dict, field: str, cand: dict, enriched_at: str | None) -> None:
    value = cand['value']
    if field in EMAIL_FIELDS:
        verdict = email_validator.validate_email(value)
        # validate_email returns either (True, None) or (False, reason)
        # — adjust to actual API of lib/validators/email.py
        ok, reason = verdict if isinstance(verdict, tuple) else (bool(verdict), None)
        if not ok:
            lead[f'{field}_invalid'] = True
            lead[f'{field}_invalid_reason'] = reason or 'validator_rejected'
            lead[f'{field}_invalid_source'] = f'osint_{cand["source"]}'
            return
    lead[field] = value
    lead[f'{field}_source'] = f'osint_{cand["source"]}'
    lead[f'{field}_added_at'] = enriched_at
    lead[f'{field}_confidence'] = cand['judge_confidence']
    if cand.get('query'):
        lead[f'{field}_query'] = cand['query']
    if cand.get('judge_reasoning'):
        lead[f'{field}_judge_reasoning'] = cand['judge_reasoning']
```

> Note for engineer: check `lib/validators/email.py` for the actual function signature. If it returns just a bool, simplify; if it returns a richer object, adapt. Do not change the validator — match its existing API.

- [ ] **Step 4: Run test to verify it passes**

```bash
python outreach/scripts/tests/test_merge_osint_into_master.py
```
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add outreach/scripts/merge_osint_into_master.py outreach/scripts/tests/test_merge_osint_into_master.py
git commit -m "feat(outreach): merge_osint pipes email candidates through validator"
```

---

### Task 23: Merge — CLI wrapper

**Files:**
- Modify: `outreach/scripts/merge_osint_into_master.py`

- [ ] **Step 1: Add `main()` to merge_osint_into_master.py**

```python
# Append to merge_osint_into_master.py
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Graft enrichment/osint/<date>.json (judged) into master.json.',
    )
    add_pipeline_arg(parser)
    parser.add_argument('--master', type=Path, default=None,
                        help='master JSON (default: outputs/<latest-date>/master.json)')
    parser.add_argument('--sidecar', type=Path, default=None,
                        help='OSINT sidecar (default: latest enrichment/osint/<date>.json)')
    parser.add_argument('--threshold', type=float, default=None,
                        help='confidence threshold (default: cfg.OSINT_CONFIDENCE_THRESHOLD)')
    args = parser.parse_args(argv)

    from scripts._common import load_pipeline_config, require_attr
    cfg = load_pipeline_config(args.pipeline)
    threshold = args.threshold if args.threshold is not None \
                else float(require_attr(cfg, 'OSINT_CONFIDENCE_THRESHOLD', args.pipeline))

    pdir = pipeline_dir(args.pipeline)
    master_path = args.master or latest_master(pdir)
    sidecar_path = args.sidecar or _latest_osint_sidecar(pdir)

    if master_path is None or not master_path.exists():
        sys.stderr.write(f"error: master not found: {master_path}\n")
        return 2
    if sidecar_path is None or not sidecar_path.exists():
        sys.stderr.write(f"error: OSINT sidecar not found: {sidecar_path}\n")
        return 2

    with pipeline_lock(args.pipeline, 'merge_osint'):
        master = json.loads(master_path.read_text())
        sidecar = json.loads(sidecar_path.read_text())
        stats = graft(master, sidecar, threshold=threshold)
        write_atomic(master_path, master)

    print(f"  threshold        : {threshold}", file=sys.stderr)
    print(f"  grafted          : {stats['grafted']}", file=sys.stderr)
    print(f"  skipped (below)  : {stats['skipped_below_threshold']}", file=sys.stderr)
    print(f"  skipped (filled) : {stats['skipped_existing_value']}", file=sys.stderr)
    print(f"wrote {master_path}", flush=True)
    print(f"next: /outreach {args.pipeline} classify", flush=True)
    return 0


def _latest_osint_sidecar(pdir: Path) -> Path | None:
    d = pdir / 'enrichment' / 'osint'
    if not d.is_dir():
        return None
    candidates = sorted(d.glob('*.json'), reverse=True)
    return candidates[0] if candidates else None


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 2: Smoke-test the CLI parses args**

```bash
python outreach/scripts/merge_osint_into_master.py --help
```
Expected: prints argparse help, exits 0.

- [ ] **Step 3: Commit**

```bash
git add outreach/scripts/merge_osint_into_master.py
git commit -m "feat(outreach): merge_osint_into_master CLI with pipeline lock"
```

---

### Task 24: dental_sunbelt config — OSINT additions

**Files:**
- Modify: `outreach/pipelines/dental_sunbelt/config.py`

- [ ] **Step 1: Read the existing config to understand its style**

```bash
head -80 outreach/pipelines/dental_sunbelt/config.py
```

- [ ] **Step 2: Append OSINT block (match existing style — UPPER_SNAKE constants, module-level)**

```python
# Append to outreach/pipelines/dental_sunbelt/config.py:

# ────────────────────────────────────────────────────────────────────────
# OSINT enrichment
# See outreach/docs/2026-05-07-osint-enrichment-design.md
# ────────────────────────────────────────────────────────────────────────

OSINT_ENABLED = True
OSINT_SOURCES = ["whois", "deep_site_crawl", "serp"]
OSINT_FIELDS_DESIRED = [
    "linkedin_url_company",
    "linkedin_url_poc",
    "social_urls",
    "poc_name",
    "poc_email",
    "poc_role",
    "news_mentions",
]
OSINT_CONFIDENCE_THRESHOLD = 0.85
OSINT_HANDOFF_FIELDS = ["linkedin_url_poc", "linkedin_url_company", "social_urls"]

OSINT_SERP_QUERIES = {
    "linkedin_url_poc":     'site:linkedin.com/in "{poc_name}" "{city}" dentist OR DDS OR DMD',
    "linkedin_url_company": 'site:linkedin.com/company "{business_name}" "{city}" dental',
    "social_urls":          '"{business_name}" "{city}" instagram OR facebook OR twitter',
    "news_mentions":        '"{business_name}" "{city}" news OR press OR opening',
}

OSINT_DEEP_CRAWL_PATHS = [
    "/about", "/about-us", "/our-team", "/team", "/staff",
    "/leadership", "/our-doctors", "/dentists",
    "/contact", "/contact-us",
]

OSINT_INDUSTRY_TERMS = ["dentist", "DDS", "DMD", "dental practice"]
```

- [ ] **Step 3: Verify the module still imports cleanly**

```bash
cd /home/fassihhaider/Work/google-maps-scraper/outreach
python -c "from pipelines.dental_sunbelt import config; print(config.OSINT_CONFIDENCE_THRESHOLD)"
```
Expected: prints `0.85`.

- [ ] **Step 4: Commit**

```bash
git add outreach/pipelines/dental_sunbelt/config.py
git commit -m "feat(outreach): dental_sunbelt OSINT config knobs"
```

---

### Task 25: Eval harness — gold-set scaffolding + runner

**Files:**
- Create: `outreach/pipelines/dental_sunbelt/eval/osint_binding/gold_set.json`
- Create: `outreach/pipelines/dental_sunbelt/eval/osint_binding/eval_runner.py`
- Create: `outreach/pipelines/dental_sunbelt/eval/osint_binding/README.md`

- [ ] **Step 1: Write the gold-set scaffold (empty array initially)**

```bash
mkdir -p outreach/pipelines/dental_sunbelt/eval/osint_binding
```

```json
// outreach/pipelines/dental_sunbelt/eval/osint_binding/gold_set.json
[]
```

- [ ] **Step 2: Write `eval_runner.py`**

```python
# outreach/pipelines/dental_sunbelt/eval/osint_binding/eval_runner.py
"""OSINT binding eval harness.

Reads gold_set.json, dispatches the osint-binder subagent on each
record, computes precision / recall, and runs a threshold sweep.

Gold-set record shape:
{
  "lead": {...same as orchestrator passes...},
  "field": "linkedin_url_poc",
  "candidates": [...],
  "correct_index": 0 | null    // null = no candidate is the right one
}

Usage:
  python outreach/pipelines/dental_sunbelt/eval/osint_binding/eval_runner.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))


def evaluate(gold: list[dict], judgments: list[dict], thresholds: list[float]) -> dict:
    """Compare judge selections against `correct_index`. Returns metrics
    per threshold."""
    out: dict[float, dict] = {}
    for t in thresholds:
        tp = fp = fn = tn = 0
        for g, j in zip(gold, judgments):
            correct = g['correct_index']
            sel = j.get('best_match_index') if (j.get('selected_confidence') or 0) >= t else None
            if correct is None and sel is None:
                tn += 1
            elif correct is None and sel is not None:
                fp += 1
            elif correct is not None and sel is None:
                fn += 1
            elif correct == sel:
                tp += 1
            else:
                fp += 1  # wrong index counts as false positive
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        out[t] = {'precision': precision, 'recall': recall, 'f1': f1,
                  'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn}
    return out


def main() -> int:
    gold_path = Path(__file__).parent / 'gold_set.json'
    judgments_path = Path(__file__).parent / 'judgments.json'
    if not gold_path.exists():
        sys.stderr.write(f"missing gold_set: {gold_path}\n")
        return 2
    if not judgments_path.exists():
        sys.stderr.write(
            f"missing judgments: {judgments_path}\n"
            f"  bootstrap: dispatch the osint-binder subagent on {gold_path} → {judgments_path}\n"
        )
        return 2
    gold = json.loads(gold_path.read_text())
    judgments = json.loads(judgments_path.read_text())
    if len(gold) != len(judgments):
        sys.stderr.write(f"length mismatch: gold {len(gold)} vs judgments {len(judgments)}\n")
        return 2
    metrics = evaluate(gold, judgments, [0.70, 0.80, 0.85, 0.90, 0.95])
    print(f"{'threshold':<10} {'precision':>10} {'recall':>10} {'f1':>10} {'tp':>4} {'fp':>4} {'fn':>4} {'tn':>4}")
    for t, m in metrics.items():
        print(f"{t:<10} {m['precision']:>10.3f} {m['recall']:>10.3f} {m['f1']:>10.3f} "
              f"{m['tp']:>4} {m['fp']:>4} {m['fn']:>4} {m['tn']:>4}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 3: Write `README.md`**

```markdown
<!-- outreach/pipelines/dental_sunbelt/eval/osint_binding/README.md -->
# OSINT binding eval — dental_sunbelt

Hand-labeled set used to tune `OSINT_CONFIDENCE_THRESHOLD`.

## Bootstrap (first run)

1. Run `python outreach/scripts/osint_enrich.py dental_sunbelt` on a known-good slice (50–100 leads).
2. Open the resulting `enrichment/osint/<date>.json` and copy 50–100 `(lead, field, candidates)` triples into `gold_set.json`, adding `correct_index` (the index of the correct candidate, or `null` if none is correct).
3. Dispatch the `osint-binder` subagent on `gold_set.json` → write the result to `judgments.json` in the same shape the merge step consumes.
4. Run `python eval_runner.py` — the threshold sweep tells you where precision drops off.

## Gold-set record shape

```json
{
  "lead": {"place_id": "...", "business_name": "...", "city": "...", "domain": "...", ...},
  "field": "linkedin_url_poc",
  "candidates": [{...}, {...}],
  "correct_index": 0
}
```

`correct_index: null` is meaningful — it represents leads where the right answer is "no candidate, skip the field." The eval treats false-matches in this bucket as severe (precision-killers).

## Re-running after threshold change

The gold set + judgments are static. Re-run `eval_runner.py` with new threshold list (edit the call in `main`) — no re-fetching needed.
```

- [ ] **Step 4: Smoke-test the runner exits cleanly when judgments missing**

```bash
python outreach/pipelines/dental_sunbelt/eval/osint_binding/eval_runner.py
```
Expected: stderr "missing judgments: ...", exit 2.

- [ ] **Step 5: Commit**

```bash
git add outreach/pipelines/dental_sunbelt/eval/osint_binding/
git commit -m "feat(outreach): OSINT binding eval harness scaffolding"
```

---

### Task 26: Runbook update — add OSINT stage to /outreach

**Files:**
- Modify: `.claude/commands/outreach.md`

- [ ] **Step 1: Read the existing runbook to find the insertion point**

```bash
grep -n "owner_lookup\|classify" .claude/commands/outreach.md | head -20
```

The OSINT stage goes **after** `owner_lookup --apply` and **before** `classify`.

- [ ] **Step 2: Insert the OSINT stage entry**

Add a new stage section in the same style as existing stages:

```markdown
## OSINT enrich

`/outreach <pipeline> osint-enrich`

Runs after `merge_crawl_into_master` + `owner_lookup --apply`. Inspects each lead's gaps against `OSINT_FIELDS_DESIRED`, runs enrichers in two waves (whois + deep_site_crawl → serp), writes the unjudged sidecar to `enrichment/osint/<date>.json`. Resumable.

Steps:

1. `python outreach/scripts/osint_enrich.py <pipeline>`
   - This produces `enrichment/osint/<today>.json` with all candidates, no judgments yet.
2. Dispatch the `osint-binder` subagent in batches (10–20 leads per batch) over the sidecar:
   - Tool: `Task` with `subagent_type: osint-binder`
   - Prompt: `"Read enrichment/osint/<today>.json and write judgments to enrichment/osint_judgments/<today>.json. Process records [start:end]."`
   - Wait for all batches to complete, then merge the per-batch judgments into a single `osint_judgments/<today>.json`.
3. `python outreach/scripts/osint_enrich.py <pipeline> --apply-judgments enrichment/osint_judgments/<today>.json`
   - Merges judgments into the main sidecar (`selected_index`, `selected_confidence` populated).
4. `python outreach/scripts/merge_osint_into_master.py <pipeline>`
   - Grafts confident hits into master with provenance.

Per design: confident-or-skip — anything below `OSINT_CONFIDENCE_THRESHOLD` (default 0.85) is left in the sidecar but not grafted.

next: `/outreach <pipeline> classify`
```

> Note for engineer: the `--apply-judgments` flag in step 3 is a small extension to `osint_enrich.py` — read judgments path, merge `verdict / confidence / reasoning / best_match_index / selected_confidence` into the existing sidecar by `(place_id, field)` key. Add a TDD task for it if it isn't trivially obvious; or fold it into Task 18 if you bundle.

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/outreach.md
git commit -m "docs(outreach): add OSINT stage to /outreach runbook"
```

---

### Task 27: Apply-judgments step in `osint_enrich.py`

**Files:**
- Modify: `outreach/scripts/osint_enrich.py`
- Modify: `outreach/scripts/tests/test_osint_enrich.py`

- [ ] **Step 1: Write the failing test**

```python
class TestApplyJudgments(unittest.TestCase):
    def test_merges_judgments_into_sidecar_by_place_id_and_field(self):
        from scripts.osint_enrich import apply_judgments_to_sidecar
        sidecar = [{
            'place_id': 'A',
            'fields': {
                'linkedin_url_poc': {
                    'candidates': [
                        {'value': 'u1', 'judge_verdict': None, 'judge_confidence': None},
                        {'value': 'u2', 'judge_verdict': None, 'judge_confidence': None},
                    ],
                    'selected_index': None,
                    'selected_confidence': None,
                },
            },
        }]
        judgments = [{
            'place_id': 'A',
            'field': 'linkedin_url_poc',
            'judgments': [
                {'index': 0, 'verdict': 'match', 'confidence': 0.92, 'reasoning': 'r0'},
                {'index': 1, 'verdict': 'rejected', 'confidence': 0.0, 'reasoning': 'r1'},
            ],
            'best_match_index': 0,
            'selected_confidence': 0.92,
        }]
        apply_judgments_to_sidecar(sidecar, judgments)
        f = sidecar[0]['fields']['linkedin_url_poc']
        self.assertEqual(f['selected_index'], 0)
        self.assertEqual(f['selected_confidence'], 0.92)
        self.assertEqual(f['candidates'][0]['judge_verdict'], 'match')
        self.assertEqual(f['candidates'][0]['judge_confidence'], 0.92)
        self.assertEqual(f['candidates'][1]['judge_verdict'], 'rejected')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python outreach/scripts/tests/test_osint_enrich.py
```
Expected: FAIL — function doesn't exist.

- [ ] **Step 3: Implement `apply_judgments_to_sidecar` and a CLI `--apply-judgments` flag**

```python
# Append to osint_enrich.py
def apply_judgments_to_sidecar(sidecar: list[dict], judgments: list[dict]) -> None:
    """Mutate sidecar in place, merging per-(place_id, field) judgments
    into each candidate and the field's selected_*."""
    by_key: dict[tuple[str, str], dict] = {
        (j['place_id'], j['field']): j for j in judgments
    }
    for record in sidecar:
        pid = record.get('place_id')
        for field, fr in record.get('fields', {}).items():
            j = by_key.get((pid, field))
            if not j:
                continue
            for jc in j.get('judgments', []):
                idx = jc['index']
                if 0 <= idx < len(fr['candidates']):
                    fr['candidates'][idx]['judge_verdict'] = jc['verdict']
                    fr['candidates'][idx]['judge_confidence'] = jc['confidence']
                    fr['candidates'][idx]['judge_reasoning'] = jc.get('reasoning')
            fr['selected_index'] = j.get('best_match_index')
            fr['selected_confidence'] = j.get('selected_confidence')
```

In `main()`, add the flag and the apply branch:

```python
# In main():
parser.add_argument('--apply-judgments', type=Path, default=None,
                    help='merge judgments file into the existing sidecar')

# After parsing args, before the enrich loop:
if args.apply_judgments:
    if not sidecar_path.exists():
        sys.stderr.write(f"error: sidecar not found: {sidecar_path}\n")
        return 2
    if not args.apply_judgments.exists():
        sys.stderr.write(f"error: judgments not found: {args.apply_judgments}\n")
        return 2
    sidecar_data = json.loads(sidecar_path.read_text())
    judgments = json.loads(args.apply_judgments.read_text())
    apply_judgments_to_sidecar(sidecar_data, judgments)
    tmp = sidecar_path.with_suffix(sidecar_path.suffix + '.tmp')
    tmp.write_text(json.dumps(sidecar_data, indent=2, ensure_ascii=False))
    tmp.replace(sidecar_path)
    print(f"applied {len(judgments)} judgments to {sidecar_path}", flush=True)
    return 0
```

- [ ] **Step 4: Run all osint_enrich tests**

```bash
python outreach/scripts/tests/test_osint_enrich.py
```
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add outreach/scripts/osint_enrich.py outreach/scripts/tests/test_osint_enrich.py
git commit -m "feat(outreach): osint_enrich --apply-judgments merges subagent output"
```

---

### Task 28: Full-suite test sweep

**Files:** none

- [ ] **Step 1: Run every test in the repo (per outreach/CLAUDE.md "Run tests before declaring done")**

```bash
cd /home/fassihhaider/Work/google-maps-scraper
for t in $(find outreach/lib outreach/scripts outreach/tests -name 'test_*.py' 2>/dev/null); do
  echo "── $t ──"
  python "$t" || break
done
```
Expected: every test file prints "OK" and exits 0; the loop completes without `break`.

- [ ] **Step 2: If any tests fail, fix the offending code (do not amend tests to pass)**

Use the failure output to identify the regression. Common causes:
- `lib/validators/email.py` API mismatch — adjust the merge step's call.
- `lib/enrichers/website_crawl.py` `lease_single_session` does not exist — add the thin wrapper or use the existing pool helper.
- `python-whois` not installed in the running venv — re-run `pip install python-whois` inside the venv.

- [ ] **Step 3: Commit any fixes**

```bash
git add <files-touched>
git commit -m "fix(outreach): address regressions from full-suite OSINT sweep"
```

---

### Task 29: Hand-test on dental_sunbelt (one-lead dry run)

**Files:** none (read-only verification)

- [ ] **Step 1: Pick a single test lead from dental_sunbelt master.json**

```bash
cd /home/fassihhaider/Work/google-maps-scraper
python -c "
import json, glob
masters = sorted(glob.glob('outreach/pipelines/dental_sunbelt/outputs/*/master.json'), reverse=True)
m = json.load(open(masters[0]))
print('test lead place_id:', m[0]['place_id'])
print('business:', m[0].get('business_name'))
print('city:', m[0].get('city'))
print('current poc_name:', m[0].get('poc_name'))
print('current linkedin_url_poc:', m[0].get('linkedin_url_poc'))
"
```

- [ ] **Step 2: Run osint_enrich on that single lead**

```bash
# Create a one-lead master snippet
python -c "
import json, glob
masters = sorted(glob.glob('outreach/pipelines/dental_sunbelt/outputs/*/master.json'), reverse=True)
m = json.load(open(masters[0]))
import os
os.makedirs('/tmp/osint-test/outputs/2026-05-07', exist_ok=True)
with open('/tmp/osint-test/outputs/2026-05-07/master.json', 'w') as f: json.dump([m[0]], f)
"

python outreach/scripts/osint_enrich.py dental_sunbelt \
  --master /tmp/osint-test/outputs/2026-05-07/master.json \
  --sidecar /tmp/osint-test/osint.json
```
Expected: prints "1 leads to enrich", "[1/1] <place_id>: N candidates", exits 0. Inspect `/tmp/osint-test/osint.json` — should have one record with whois / deep_site / serp candidates as available.

- [ ] **Step 3: Verify sidecar shape matches the spec**

```bash
python -c "
import json
s = json.load(open('/tmp/osint-test/osint.json'))
assert isinstance(s, list)
assert s[0].get('place_id')
assert s[0].get('enriched_at')
assert s[0].get('fields')
for f, fr in s[0]['fields'].items():
    assert 'candidates' in fr
    assert 'selected_index' in fr
print('OK')
"
```
Expected: prints `OK`.

- [ ] **Step 4: Document findings**

If any candidates were emitted but look weak/wrong, note it (this is the input for the eval-set bootstrap). Do NOT change the threshold or the binder rules from a single hand-test.

- [ ] **Step 5: No commit (verification only)**

---

## Self-review

This plan covers every section of the spec. Spot-check:

| Spec section | Plan task |
|---|---|
| Stage placement & module layout | Task 26 (runbook) — files created in Tasks 2,5,10,14,15,20 |
| WHOIS enricher | Tasks 2, 3, 4 |
| Deep site crawl (JSON-LD) | Tasks 5, 6 |
| Deep site crawl (heading proximity) | Task 7 |
| Deep site crawl (dedup with website_crawl) | Task 8 |
| Deep site crawl (driver) | Task 9 |
| SERP enricher (Google) | Task 10 |
| SERP enricher (Bing/DDG) | Task 11 |
| SERP enricher (block detection) | Task 12 |
| SERP enricher (engine fallback) | Task 13 |
| osint-binder subagent | Task 14 |
| Orchestrator (gap detection) | Task 15 |
| Orchestrator (two-wave) | Task 16 |
| Orchestrator (production fetch wiring) | Task 17 |
| Orchestrator (sidecar I/O + resumability) | Task 18 |
| Orchestrator (CLI) | Task 19 |
| Orchestrator (apply-judgments) | Task 27 |
| Merge (graft + provenance) | Task 20 |
| Merge (immutability) | Task 21 |
| Merge (validator at boundary) | Task 22 |
| Merge (CLI) | Task 23 |
| Merge (list-typed fields) | Task 20 (`_graft_list_field`) |
| Per-vertical config | Task 24 |
| Eval harness | Task 25 |
| Runbook update | Task 26 |
| Full-suite test | Task 28 |
| Hand-test verification | Task 29 |

**Out-of-scope items from the spec are intentionally absent from the plan:** SOS scraping, GMB deep re-scrape, manual queue, paid APIs, LinkedIn page scraping, email pattern guessing, SMTP probing, rotating proxies. These are listed in the spec as v2 / out-of-scope and require separate plans.

**Open implementation decisions surfaced by the plan (engineer decides during Task 17 / Task 22):**

- `lib/enrichers/website_crawl.py` may not currently expose a single-session lease — Task 17 says: add a thin wrapper, do not refactor `run_pool`.
- `lib/validators/email.py` API may return either bool or `(bool, reason)` tuple — Task 22 says: match the actual API, do not change the validator.

These are flagged inline in the relevant tasks.
