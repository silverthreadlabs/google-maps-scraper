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
