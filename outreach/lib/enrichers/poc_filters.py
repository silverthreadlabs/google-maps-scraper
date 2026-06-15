"""Flag review-author / reviews-widget noise in crawled POC lists.

The website crawler harvests JSON-LD `Person` nodes. On sites that embed
Review schema, the `Person` under each `Review.author` is a *reviewer*, not a
decision-maker (e.g. 'Padra M - Los Angeles, CA'). These arrive in bulk with no
role / email / socials — on real data one auto shop carried 48 of them.

This module marks such entries invalid (append-only, per CLAUDE.md rule 1 —
never stripped, names stay on master for audit). The handoff already drops
POCs flagged `invalid`, so they vanish from the deliverable while a genuine
small team survives. Pure, generalized (no vertical/campaign specifics), and
tolerant of missing fields.
"""
from __future__ import annotations

import re

# 'Padra M - Los Angeles, CA' / 'Ex P - Mountain View, CA' — the Google-review
# author label (a name, then ' - <City>, <ST>'). Hyphen or en-dash.
_REVIEWER_LABEL_RE = re.compile(r'.+\s[-–]\s.+,\s*[A-Z]{2}$')

# Above this many 'bare' POCs (a crawled name with no role / email / socials)
# on a single lead, the page almost certainly embedded a reviews widget — a
# real small business has at most a handful of named decision-makers.
DEFAULT_MAX_BARE_POCS = 4


def is_reviewer_label(name: str | None) -> bool:
    """True for a Google-review author label ('<name> - <City>, <ST>')."""
    return bool(_REVIEWER_LABEL_RE.match((name or '').strip()))


def _is_bare(poc: dict) -> bool:
    """A POC with a name but no corroborating signal (no role, email, or
    socials). Review-author Persons harvested from JSON-LD look exactly like
    this; a genuine decision-maker usually carries at least one."""
    if not isinstance(poc, dict) or not (poc.get('name') or '').strip():
        return False
    return not (poc.get('role') or poc.get('email') or poc.get('socials'))


def flag_review_author_pocs(pocs, *, max_bare: int = DEFAULT_MAX_BARE_POCS) -> list:
    """Return a NEW POC list with review-author noise marked invalid.

    Append-only: copies each dict and ADDS `invalid` / `invalid_reason`; never
    drops a POC and never mutates the input. Already-invalid POCs and non-dict
    entries pass through untouched. Two signals:

      1. name matches the Google-review author label -> always invalid.
      2. if the count of 'bare' POCs exceeds `max_bare`, those bare POCs are
         flagged (reviews-widget signal). At or below the threshold they are
         kept (a real small team). A POC carrying a role/email/socials is never
         flagged by this rule.
    """
    pocs = list(pocs or [])
    widget = sum(1 for p in pocs if _is_bare(p)) > max_bare
    out = []
    for p in pocs:
        if not isinstance(p, dict) or p.get('invalid'):
            out.append(p)
            continue
        q = dict(p)
        if is_reviewer_label(q.get('name', '')):
            q['invalid'] = True
            q['invalid_reason'] = 'review_author_label'
        elif widget and _is_bare(q):
            q['invalid'] = True
            q['invalid_reason'] = 'reviews_widget_suspected'
        out.append(q)
    return out
