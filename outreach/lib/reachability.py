"""
Reachability scoring — industry-agnostic.

Measures how easily a decision-maker at a Lead can be reached, on a 0–50
scale, through PEOPLE (POCs) only — never through the business front door.
Business emails (info@…) and business socials (the company's own page) are
deliberately excluded.

Two parts (see DDD-0001):
  1. Representative-POC channel boost — the single best-reachable usable
     contact; channels stack (personal LinkedIn > directly-reachable email >
     personal social), priority via the weights below.
  2. Multi-POC boost — diminishing, capped: more usable contacts help, but the
     2nd matters most and a 50-name crawl artifact cannot dominate.

The per-channel credit comes from ONE representative POC (no-double-count
rule); extra POCs add only through the multi-POC boost.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

REACH_CAP = 50.0
W_LINKEDIN = 30.0
W_EMAIL = 18.0
W_SOCIAL = 8.0
W_MULTI = 10.0
# When NO usable contact has a reachable channel, the multi-POC boost is capped
# at this (instead of climbing toward W_MULTI). Named-but-unreachable contacts
# are only a research starting point — a lead we can't reach by any channel must
# not approach a genuinely-reachable lead's score. See DDD-0001.
NO_CHANNEL_MULTI_CAP = 3.0
POC_MIN_CONFIDENCE = 0.30   # mirror the bar sales sees in the handoff CSV

# Role / front-door mailbox local-parts that do NOT reach a specific person.
GENERIC_MAILBOXES = frozenset({
    'info', 'contact', 'sales', 'admin', 'hello', 'office', 'team', 'support',
    'service', 'help', 'mail', 'inquiries', 'enquiries', 'reception',
    'frontdesk', 'booking', 'appointments', 'general', 'marketing', 'careers',
    'jobs', 'hr', 'billing', 'accounts', 'noreply', 'no-reply',
})
_SOCIAL_DOMAINS = ('facebook.com', 'instagram.com', 'twitter.com', 'x.com',
                   'tiktok.com', 'youtube.com')


def is_personal_linkedin(url: str | None) -> bool:
    return 'linkedin.com/in/' in (url or '').lower()


def is_reachable_email(email: str | None) -> bool:
    e = (email or '').strip().lower()
    if '@' not in e:
        return False
    local = e.split('@', 1)[0]
    base = re.split(r'[._\-+]', local)[0]
    return local not in GENERIC_MAILBOXES and base not in GENERIC_MAILBOXES


def is_personal_social(url: str | None, business_name: str = '') -> bool:
    """Strict: a personal social profile, not the business's own page.
    LinkedIn is scored separately, so it never counts here."""
    u = (url or '').lower()
    if not u or 'linkedin.com' in u:
        return False
    if not any(d in u for d in _SOCIAL_DOMAINS):
        return False
    if '/pages/' in u or '/company/' in u:
        return False
    biz = re.sub(r'[^a-z0-9]', '', (business_name or '').lower())
    handle = re.sub(r'^https?://', '', u).split('?')[0].rstrip('/').split('/')[-1]
    h = re.sub(r'[^a-z0-9]', '', handle)
    if biz and len(biz) >= 4 and (biz in h or h in biz):
        return False
    return True


@dataclass
class Contact:
    name: str
    has_linkedin: bool
    has_email: bool
    has_social: bool

    def boost(self) -> float:
        return (W_LINKEDIN * self.has_linkedin
                + W_EMAIL * self.has_email
                + W_SOCIAL * self.has_social)


def usable_contacts(lead: dict) -> list[Contact]:
    """Unify pocs[] with the lead-level owner/OSINT contact fields into one
    list of usable contacts (not invalid, confidence ≥ POC_MIN_CONFIDENCE or
    unscored). Lead-level channels fold into a matching pocs[] entry by name,
    else become their own contact — so an owner_linkedin written by the
    owner-research stage counts even with no pocs[] row."""
    biz = lead.get('title') or ''
    contacts: list[Contact] = []
    for p in (lead.get('pocs') or []):
        if not isinstance(p, dict) or p.get('invalid') or not (p.get('name') or '').strip():
            continue
        c = p.get('confidence')
        if c is not None and c < POC_MIN_CONFIDENCE:
            continue
        socials = p.get('socials') or []
        contacts.append(Contact(
            name=p['name'].strip(),
            has_linkedin=any(is_personal_linkedin(s) for s in socials),
            has_email=is_reachable_email(p.get('email')),
            has_social=any(is_personal_social(s, biz) for s in socials),
        ))

    def fold(name: str | None, linkedin_url: str | None, email: str | None) -> None:
        li = is_personal_linkedin(linkedin_url)
        em = is_reachable_email(email)
        name = (name or '').strip()
        if not (name or li or em):
            return
        if name:
            for c in contacts:
                if c.name.lower() == name.lower():
                    c.has_linkedin = c.has_linkedin or li
                    c.has_email = c.has_email or em
                    return
        contacts.append(Contact(name=name or '(owner)', has_linkedin=li,
                                has_email=em, has_social=False))

    fold(lead.get('owner_name'), lead.get('owner_linkedin'), lead.get('owner_email'))
    fold(lead.get('poc_name'), lead.get('linkedin_url_poc'), lead.get('poc_email'))
    return contacts


def reachability_score(lead: dict) -> tuple[float, dict]:
    """Return (score 0–50, breakdown). Breakdown carries the representative
    contact's name, the channels credited, and the usable-POC count."""
    contacts = usable_contacts(lead)
    if not contacts:
        return 0.0, {'usable_poc_count': 0, 'representative': None, 'channels': []}
    rep = max(contacts, key=lambda c: c.boost())
    n = len(contacts)
    multi = W_MULTI * (1 - 1.0 / n)
    if rep.boost() == 0:
        # No usable contact carries a reachable channel: cap the multi-POC
        # boost low (see NO_CHANNEL_MULTI_CAP) rather than letting a pile of
        # named-but-unreachable contacts approach a reachable lead's score.
        score = min(NO_CHANNEL_MULTI_CAP, multi)
    else:
        score = min(REACH_CAP, rep.boost() + multi)
    channels = [k for k, v in (('linkedin', rep.has_linkedin),
                               ('email', rep.has_email),
                               ('social', rep.has_social)) if v]
    return round(score, 2), {'usable_poc_count': n, 'representative': rep.name,
                             'channels': channels}
