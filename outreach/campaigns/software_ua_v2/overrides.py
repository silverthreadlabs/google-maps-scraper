"""Software UA — campaign-specific overrides on top of verticals/software/config.py.

Adds regional UA outsourcer brand lists and ensures the
software vertical's defaults still apply elsewhere. Pain weighting
already matches Ezly's pitch in the vertical default; this file
only adds region-specific signal.

Honest fit note: Ezly's ICP is solo freelancers on Upwork/Fiverr.
This list is small/mid UA agencies. F1 will skew lower than
dental gold (~0.78) because B2B software reviews discuss
project-delivery pain, not response-speed pain.
"""
from __future__ import annotations

import re

DSO_TITLE_REGEX_EXTRA = re.compile(
    r'\b('
    r'EPAM|GlobalLogic|SoftServe|Luxoft|Ciklum|N-?iX|Sigma Software|'
    r'Intellias|ELEKS|Miratech|Infopulse|DataArt|Daxx|Beetroot|'
    r'Astound Commerce|Edvantis|Symphony Solutions|Innovecs|Plexteq|'
    r'TEAM International|AltexSoft|Provectus|Devoteam|'
    r'Wipro|Infosys|TCS|Tata Consultancy|'
    r'Wix\.com|Grammarly|MacPaw|GitLab|JetBrains|Reply'
    r')\b', re.I,
)

DSO_EMAIL_DOMAINS_EXTRA = {
    'epam.com',
    'globallogic.com',
    'softserveinc.com',
    'luxoft.com',
    'ciklum.com',
    'n-ix.com',
    'sigma.software',
    'intellias.com',
    'eleks.com',
    'miratech.com',
    'infopulse.com',
    'dataart.com',
    'daxx.com',
    'beetroot.se',
    'astoundcommerce.com',
    'innovecs.com',
    'symphony-solutions.eu',
    'wipro.com',
    'infosys.com',
    'tcs.com',
    'wix.com',
    'grammarly.com',
    'macpaw.com',
    'gitlab.com',
    'jetbrains.com',
}

# ── Ezly ICP targeting (campaign-scoped) ────────────────────────────────
# Ezly's buyer is the person who runs client communications — founder,
# co-founder, business-development / sales / partnerships lead — and lives on
# LinkedIn. The software vertical already biases the POC LinkedIn query toward
# "CEO OR founder"; here we widen it to the client-comms roles and add a
# direct people-search query. Overlaid on the vertical via campaign_config.
OSINT_SERP_QUERIES = {
    "linkedin_url_poc":
        'site:linkedin.com/in "{poc_name}" "{city}" '
        '(founder OR CEO OR "business development" OR sales OR partnerships OR owner)',
    "linkedin_url_company":
        'site:linkedin.com/company "{business_name}" "{city}"',
}

# Ensure the person-level decision-maker fields are explicitly desired so the
# osint gap-detector chases them even if the vertical default changes.
OSINT_FIELDS_DESIRED = [
    "linkedin_url_poc", "poc_name", "poc_email", "poc_role",
]
