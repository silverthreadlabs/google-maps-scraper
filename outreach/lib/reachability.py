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

# Free-mail / consumer domains. An address here that names a person
# (non-generic local part) is treated as a PERSONAL email — a direct line to
# the individual — as opposed to a company-domain address (john.doe@firm.com),
# which is a BUSINESS email. See DDD-0003 (lpo_ladder profile).
FREE_MAIL_DOMAINS = frozenset({
    'gmail.com', 'googlemail.com', 'yahoo.com', 'ymail.com', 'rocketmail.com',
    'hotmail.com', 'outlook.com', 'live.com', 'msn.com', 'aol.com',
    'icloud.com', 'me.com', 'mac.com', 'proton.me', 'protonmail.com',
    'gmx.com', 'gmx.us', 'mail.com', 'zoho.com', 'yandex.com',
    'comcast.net', 'verizon.net', 'sbcglobal.net', 'att.net',
    'bellsouth.net', 'cox.net', 'earthlink.net', 'optonline.net',
})


def _email_domain(email: str | None) -> str:
    e = (email or '').strip().lower()
    return e.split('@', 1)[1] if '@' in e else ''


def is_personal_email(email: str | None) -> bool:
    """Reachable (names a person) AND on a free-mail/consumer domain — a direct
    personal line (e.g. jane.doe@gmail.com). See DDD-0003."""
    return is_reachable_email(email) and _email_domain(email) in FREE_MAIL_DOMAINS


def is_named_business_email(email: str | None) -> bool:
    """Reachable (names a person) but on a company domain (e.g.
    john.doe@acme.com) — weaker than a personal address in the lpo_ladder."""
    return is_reachable_email(email) and _email_domain(email) not in FREE_MAIL_DOMAINS


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


# --- phone_first profile (DDD-0002) -----------------------------------------
# For campaigns whose client outreaches by PHONE (reps cold-call), the POC
# channel model is backwards: it scores ~0 for a lead with a perfectly
# callable number and a known owner. The phone_first profile measures "can a
# rep execute a phone call on this lead": callable number is the gate, the
# decision-maker's NAME is the payload ("Hi, is this Rick?"), person-level
# channels are follow-up bonuses. Opt in per campaign via
# REACHABILITY_PROFILE = 'phone_first' in overrides.py.
PF_W_PHONE = 25.0          # validated callable number (phone or phone_alt)
PF_W_OWNER_NAME = 15.0     # decision-maker name known
PF_W_DIRECT_LINE = 5.0     # person-level direct/cell line found
PF_W_SECOND_CONTACT = 3.0  # a second named person as fallback
PF_W_BONUS_CHANNEL = 2.0   # any personal email/LinkedIn/social (follow-up)


def phone_first_reachability_score(lead: dict) -> tuple[float, dict]:
    """phone_first profile: (score 0–50, breakdown) — same breakdown shape as
    the poc_channels scorer so downstream columns don't change."""
    channels: list[str] = []
    score = 0.0

    phone_ok = bool((lead.get('phone') and not lead.get('phone_invalid'))
                    or lead.get('phone_alt'))
    if phone_ok:
        score += PF_W_PHONE
        channels.append('phone_alt' if (lead.get('phone_invalid')
                                        and lead.get('phone_alt')) else 'phone')

    contacts = usable_contacts(lead)
    owner = (lead.get('owner_name') or '').strip()
    representative = owner or (contacts[0].name if contacts else None)
    if representative:
        score += PF_W_OWNER_NAME
        channels.append('named_decision_maker')

    direct = any((p.get('phone') or '').strip()
                 for p in (lead.get('pocs') or [])
                 if isinstance(p, dict) and not p.get('invalid'))
    if direct:
        score += PF_W_DIRECT_LINE
        channels.append('direct_line')

    if len(contacts) >= 2:
        score += PF_W_SECOND_CONTACT
        channels.append('fallback_contact')

    if any(c.boost() > 0 for c in contacts):
        score += PF_W_BONUS_CHANNEL
        channels.append('bonus_channel')

    # Without a callable number the other components are research value,
    # not reachability — cap hard (mirrors NO_CHANNEL_MULTI_CAP's intent).
    if not phone_ok:
        score = min(score, NO_CHANNEL_MULTI_CAP)

    return round(min(REACH_CAP, score), 2), {
        'usable_poc_count': len(contacts),
        'representative': representative,
        'channels': channels,
    }


# --- lpo_ladder profile (DDD-0003) -----------------------------------------
# For the LPO campaign, reachability IS the classification and it is a strict
# LADDER (client-defined, highest → lowest):
#   A  ≥2 personal channels  (POC LinkedIn OR personal email)
#   B   1 personal channel   (POC LinkedIn OR personal email)
#   C   no personal channel, but a personal social OR a named business email
#       (john.doe@acme.com)
#   D   none of the above, but a (generic) business email AND a phone
#   .   phone-only / nothing → unreachable, lowest
# Scores are placed inside the blended-tier bands (A≥75 / B≥50 / C≥25 / D<25)
# so score_lead's tier assignment falls out for free. Range is 0–100 (this
# profile is the whole score; there is no service-fit half — the LPO campaign
# skips pain classification). reachability_channels tags are profile-specific.
LADDER_SOCIAL_DOMAINS = _SOCIAL_DOMAINS


def _ladder_pools(lead: dict) -> dict:
    """Collect the reachability signals the ladder needs, across pocs[],
    lead-level owner/poc fields, and crawled lead-level pools. A personal
    channel is a personal LinkedIn (/in/) or a personal (free-mail) email."""
    biz = lead.get('title') or ''
    emails: set[str] = set()
    linkedins: set[str] = set()
    socials: set[str] = set()

    def add_socials(seq):
        for s in (seq or []):
            if not isinstance(s, str):
                continue
            if is_personal_linkedin(s):
                linkedins.add(s.lower())
            elif is_personal_social(s, biz):
                socials.add(s.lower())

    for p in (lead.get('pocs') or []):
        if not isinstance(p, dict) or p.get('invalid') or not (p.get('name') or '').strip():
            continue
        c = p.get('confidence')
        if c is not None and c < POC_MIN_CONFIDENCE:
            continue
        if p.get('email'):
            emails.add(str(p['email']).strip().lower())
        add_socials(p.get('socials'))

    for e in (lead.get('owner_email'), lead.get('poc_email')):
        if e:
            emails.add(str(e).strip().lower())
    for li in (lead.get('owner_linkedin'), lead.get('linkedin_url_poc')):
        if is_personal_linkedin(li):
            linkedins.add(str(li).strip().lower())
    for pool in ('crawled_emails', 'emails'):
        for e in (lead.get(pool) or []):
            if isinstance(e, str):
                emails.add(e.strip().lower())
    add_socials(lead.get('crawled_socials'))
    add_socials(lead.get('social_urls'))

    personal_emails = {e for e in emails if is_personal_email(e)}
    named_biz_emails = {e for e in emails if is_named_business_email(e)}
    generic_emails = {e for e in emails if e and not is_reachable_email(e)}
    phone_ok = bool((lead.get('phone') and not lead.get('phone_invalid'))
                    or lead.get('phone_alt'))
    return {
        'linkedins': linkedins, 'personal_emails': personal_emails,
        'named_biz_emails': named_biz_emails, 'generic_emails': generic_emails,
        'socials': socials, 'phone_ok': phone_ok,
    }


def lpo_ladder_reachability_score(lead: dict) -> tuple[float, dict]:
    """lpo_ladder profile (DDD-0003): (score 0–100, breakdown). The band is the
    tier; the score orders leads within a band. Same breakdown shape as the
    other scorers so CSV columns don't move."""
    p = _ladder_pools(lead)
    n_personal = len(p['linkedins']) + len(p['personal_emails'])
    channels: list[str] = []
    if p['linkedins']:
        channels.append('poc_linkedin')
    if p['personal_emails']:
        channels.append('personal_email')
    if p['named_biz_emails']:
        channels.append('named_business_email')
    if p['socials']:
        channels.append('social')
    if p['generic_emails']:
        channels.append('business_email')
    if p['phone_ok']:
        channels.append('phone')

    if n_personal >= 2:                       # A band (≥75)
        score = min(100.0, 80.0 + 4.0 * n_personal)
    elif n_personal == 1:                     # B band (50–74)
        score = 60.0
        if p['socials']:
            score += 5.0
        if p['named_biz_emails']:
            score += 5.0
        if p['phone_ok']:
            score += 3.0
        score = min(74.0, score)
    elif p['socials'] or p['named_biz_emails']:   # C band (25–49)
        score = 30.0 + (10.0 if p['named_biz_emails'] else 0.0) + (5.0 if p['socials'] else 0.0)
        score = min(49.0, score)
    elif (p['generic_emails'] and p['phone_ok']):  # D band: business email + phone
        score = 15.0
    elif p['phone_ok'] or p['generic_emails']:     # bottom of D: only one of the two
        score = 8.0
    else:                                          # unreachable
        score = 0.0

    rep = (lead.get('owner_name') or '').strip() or None
    if not rep:
        for c in (lead.get('pocs') or []):
            if isinstance(c, dict) and (c.get('name') or '').strip() and not c.get('invalid'):
                rep = c['name'].strip()
                break
    return round(score, 2), {
        'usable_poc_count': len(usable_contacts(lead)),
        'representative': rep,
        'channels': channels,
    }


# --- phone_email_parallel profile (DDD-0004) --------------------------------
# For campaigns A/B-testing PHONE and EMAIL outreach in parallel, the best lead
# has a validated phone number AND a good-quality, genuinely reachable email.
# phone_first cannot express that: it awards ANY personal email a flat 2 points
# in one undifferentiated bucket, so email quality is invisible to the grade.
#
# Two arms, each scored on its own scale, then blended:
#   phone arm — the existing DDD-0002 scorer, called UNCHANGED for its channel
#               facts (no new phone logic, no risk to phone semantics);
#   email arm — the 5-rung E-ladder below.
#
# Every list here is a LOCAL extension, unioned at use — the shared
# GENERIC_MAILBOXES / FREE_MAIL_DOMAINS frozensets are deliberately NOT
# mutated. They feed is_reachable_email → Contact.boost → phone_first's
# bonus_channel, so widening them in place would move delivered tiers on
# attorney_newyork, hvac_phoenix, hvac_dallas, hvac_atlanta and
# automotive_sanfrancisco. Opt in per campaign via
# REACHABILITY_PROFILE = 'phone_email_parallel'.

# Regional consumer ISPs missing from FREE_MAIL_DOMAINS. Matched on the
# REGISTRABLE domain, so `tampabay.rr.com` counts as `rr.com` — without this,
# Roadrunner owner inboxes fall into the off-site-zero bucket.
FREE_MAIL_DOMAINS_EXTRA = frozenset({
    'rr.com', 'twc.com', 'charter.net', 'windstream.net', 'frontier.com',
    'embarqmail.com', 'juno.com', 'netzero.net', 'roadrunner.com',
    'peoplepc.com', 'aim.com', 'ptd.net',
})
_FREEMAIL_ALL = FREE_MAIL_DOMAINS | FREE_MAIL_DOMAINS_EXTRA

# Role / front-door locals observed on these sites that GENERIC_MAILBOXES
# does not list. Used only by the E-ladder (see the no-mutation note above).
GENERIC_MAILBOXES_EXTRA = frozenset({
    'estimating', 'estimates', 'dispatch', 'bookings', 'schedule',
    'scheduling', 'customercare', 'customerservice', 'clientcare', 'feedback',
    'claims', 'orders', 'order', 'accounting', 'warranty', 'parts', 'permits',
    'quotes', 'quote', 'newcustomers', 'frontoffice', 'shop', 'store', 'web',
    'webmaster', 'privacy', 'legal', 'compliance', 'returns', 'supportteam',
})
_ROLE_LOCALS = GENERIC_MAILBOXES | GENERIC_MAILBOXES_EXTRA

# Website-builder / hosting hosts. A lead whose Maps `website` is a builder
# subdomain must not make `@webador.com` look site-aligned.
BUILDER_HOSTS = frozenset({
    'webador.com', 'wixsite.com', 'wix.com', 'squarespace.com', 'weebly.com',
    'godaddysites.com', 'business.site', 'sites.google.com', 'wordpress.com',
    'blogspot.com', 'myshopify.com', 'square.site', 'webnode.com',
    'jimdosite.com', 'strikingly.com', 'netlify.app', 'github.io',
    'facebook.com', 'linktr.ee',
})

# Only legal forms and geography are stripped from the business title. Trade
# words (air / hvac / cooling / comfort) are DELIBERATELY kept: for a small
# owner-operated shop `bamairservices@gmail.com` IS the shop's inbox and the
# trade word is the evidence. Stripping them emptied the token set for shops
# like "HVAC Comfort Solutions".
#
# The geography half is the measured DDD-0004 list, calibrated on the Tampa
# master: it is what keeps `clearwaterradiator@gmail.com` and
# `ccsoftampa@verizon.net` at E1 ("usable, unproven") instead of crediting a
# place name as the business name. Location terms belong in
# `locations/<loc>.yaml` by CLAUDE.md's repo shape, but the scorer has no
# config channel today — deriving them from the lead's own address/metro
# fields instead was measured and over-strips (B 381 / D 338 vs 383 / 337).
# Move this half behind a config-supplied set when a second location adopts
# the profile; see DDD-0004 §5.
TITLE_STOP = frozenset({
    'llc', 'inc', 'co', 'corp', 'corporation', 'incorporated', 'company',
    'the', 'and', 'of', 'ltd', 'lp', 'pa', 'pllc',
    'tampa', 'florida', 'fl', 'clearwater', 'brandon', 'lutz', 'pinellas',
    'hillsborough', 'pasco', 'petersburg', 'stpete', 'wesley', 'chapel',
})
BIZ_NAME_MIN_COVERAGE = 0.5

# The E-ladder (DDD-0004 §2), highest → lowest.
E_PERSON, E_OWNER_INBOX, E_SHOP_INBOX, E_UNVERIFIED, E_NONE = 'E4', 'E3', 'E2', 'E1', 'E0'
E_ORDER = [E_NONE, E_UNVERIFIED, E_SHOP_INBOX, E_OWNER_INBOX, E_PERSON]
E_MIN_GENUINE = E_SHOP_INBOX          # the "genuinely reachable" bar (E2+)

# Blended-half weights. The callable gate keeps DDD-0002's 25 points EXACTLY,
# so a callable lead still clears the C line (>=25) at any service-fit value.
# Phone RESEARCH depth carries only ordering weight here (1.0 / 0.5 / 0.25
# instead of 15 / 5 / 3): knowing the owner's name does not open a second
# channel. It is not discarded — it earns its keep through the email leg,
# because a known name is what promotes an address to E4.
PEP_PHONE_GATE = 25.0
PEP_PHONE_NAME = 1.0
PEP_PHONE_DIRECT = 0.5
PEP_PHONE_FALLBACK = 0.25
# Points the email leg contributes to the 0–50 reachability half.
PEP_E_BLEND = {E_PERSON: 25.0, E_OWNER_INBOX: 23.0, E_SHOP_INBOX: 18.0,
               E_UNVERIFIED: 5.0, E_NONE: 0.0}
PEP_E_MULTI = 1.0            # a second independent E2+ email, capped
# The same ladder on the email arm's own 0–50 scale (DDD-0004 §2, "Arm pts").
# Reported for readability beside the blend; the grade uses PEP_E_BLEND.
PEP_E_ARM = {E_PERSON: 46.0, E_OWNER_INBOX: 43.0, E_SHOP_INBOX: 25.0,
             E_UNVERIFIED: 8.0, E_NONE: 0.0}
PEP_E_ARM_MULTI = 2.0


def _host(url: str | None) -> str:
    u = re.sub(r'^[a-z]+://', '', (url or '').strip().lower())
    h = u.split('/')[0].split('?')[0].split(':')[0]
    return h[4:] if h.startswith('www.') else h


def _registrable(host: str) -> str:
    """Last two labels of a host — 'mail.tampabay.rr.com' → 'rr.com'. Good
    enough for the domains this pipeline sees; no public-suffix list."""
    parts = [p for p in (host or '').split('.') if p]
    return '.'.join(parts[-2:]) if len(parts) >= 2 else (host or '')


def _is_freemail(domain: str) -> bool:
    """Freemail on the REGISTRABLE domain. `_email_domain` keeps its exact-match
    contract for existing callers; this is the E-ladder's widened test."""
    return domain in _FREEMAIL_ALL or _registrable(domain) in _FREEMAIL_ALL


def _title_tokens(title: str | None) -> set[str]:
    words = re.findall(r'[a-z0-9]+', (title or '').lower())
    toks = {w for w in words if w not in TITLE_STOP and len(w) >= 3}
    return toks or {w for w in words if len(w) >= 3}


def business_name_coverage(local: str, title: str | None) -> float:
    """Fraction of the local part's alphanumerics covered by business-title
    tokens. 1.00 for `bamairservices` vs "Bam Air Conditioning Services LLC";
    0.43 for `airluxe` vs "Dunedin Air Comfort". Plain "shares a token"
    over-fires on trade words, which is why this measures coverage."""
    lz = re.sub(r'[^a-z0-9]', '', (local or '').lower())
    total = len(lz)
    if not total:
        return 0.0
    covered = 0
    for t in sorted(_title_tokens(title), key=len, reverse=True):
        if t in lz:
            covered += len(t)
            lz = lz.replace(t, '', 1)
    return covered / total


def _person_names(lead: dict) -> set[str]:
    """Name tokens known for this lead, from owner research and non-invalid
    POCs — the provenance evidence that promotes an address to E4."""
    out: set[str] = set()
    for src in ([lead.get('owner_name'), lead.get('poc_name')]
                + [p.get('name') for p in (lead.get('pocs') or [])
                   if isinstance(p, dict) and not p.get('invalid')]):
        out.update(re.findall(r'[a-z]{3,}', (src or '').lower()))
    return out


def email_candidates(lead: dict) -> list[tuple[str, str]]:
    """(email, provenance) for every usable email on the lead, best-provenance
    first. `emails_invalid` entries are SKIPPED, never removed from the lead
    (CLAUDE.md rule 1) — the validator is the boundary that flags them."""
    invalid = {e['email'].lower() for e in (lead.get('emails_invalid') or [])
               if isinstance(e, dict) and e.get('email')}
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(e, prov):
        if not isinstance(e, str):
            return
        v = e.strip().lower()
        if not v or '@' not in v or v in seen or v in invalid:
            return
        seen.add(v)
        out.append((v, prov))

    for p in (lead.get('pocs') or []):
        if isinstance(p, dict) and not p.get('invalid') and p.get('email'):
            add(p['email'], 'poc')
    add(lead.get('owner_email'), 'owner')
    add(lead.get('poc_email'), 'poc')
    for e in (lead.get('emails') or []):
        add(e, 'maps_scrape')
    prov = 'crawl_suspect' if lead.get('crawled_emails_suspect') else 'crawl'
    for e in (lead.get('crawled_emails') or []):
        add(e, prov)
    return out


def classify_email(email: str, provenance: str, lead: dict) -> tuple[str, str]:
    """(E-tier, reason) for one email in the context of its lead. Classified
    from three properties: domain class (freemail / site-aligned / off-site),
    local-part class, and provenance."""
    local, _, domain = email.partition('@')
    site = _registrable(_host(lead.get('website')))
    free = _is_freemail(domain)
    aligned = (bool(site) and site not in BUILDER_HOSTS
               and _registrable(domain) == site)

    base = re.split(r'[._\-+]', local)[0]
    role = local in _ROLE_LOCALS or base in _ROLE_LOCALS
    lz = re.sub(r'[^a-z0-9]', '', local)
    business_named = (business_name_coverage(local, lead.get('title'))
                      >= BIZ_NAME_MIN_COVERAGE)
    names = _person_names(lead)
    person_shaped = (
        provenance in ('poc', 'owner')
        or any(n in lz for n in names if len(n) >= 4)
        or bool(re.fullmatch(r'[a-z]{1,}[._\-][a-z]{2,}', local))
    )

    # Off-site third-party domains are overwhelmingly the lead's web developer,
    # a font foundry, or a manufacturer's support desk — not the lead.
    if not (free or aligned):
        return (E_UNVERIFIED, 'off_site_person') if person_shaped else (E_NONE, 'off_site')
    if provenance == 'crawl_suspect':
        return E_UNVERIFIED, 'crawled_suspect'
    if person_shaped and not role:
        return E_PERSON, 'person_' + ('freemail' if free else 'site')
    if business_named and not role:
        return E_OWNER_INBOX, 'business_named_' + ('freemail' if free else 'site')
    if role:
        return E_SHOP_INBOX, 'role_' + ('freemail' if free else 'site')
    if aligned:
        return E_OWNER_INBOX, 'named_mailbox_site'
    return E_UNVERIFIED, 'opaque_freemail'


def email_reach_score(lead: dict) -> tuple[float, dict]:
    """Email leg: (points on the 0–50 reachability half, breakdown).

    Best tier wins; a second independent E2+ email adds a small capped bonus
    (more inboxes help a little; a crawl that harvested nine cannot outrank a
    named owner). The return value is the BLEND contribution (0–25), matching
    the `email_reach_score` CSV column; the arm's own 0–50 reading is reported
    alongside as `email_arm_score` (DDD-0004 §2/§4)."""
    best_tier, best_reason, best_email = E_NONE, '', ''
    n_genuine = 0
    cands = email_candidates(lead)
    for e, prov in cands:
        t, reason = classify_email(e, prov, lead)
        if E_ORDER.index(t) >= E_ORDER.index(E_MIN_GENUINE):
            n_genuine += 1
        if E_ORDER.index(t) > E_ORDER.index(best_tier):
            best_tier, best_reason, best_email = t, reason, e

    def leg(points: dict, multi: float) -> float:
        s = points[best_tier]
        if s > 0 and n_genuine >= 2:
            s += multi
        return round(min(points[E_PERSON], s), 2)

    return leg(PEP_E_BLEND, PEP_E_MULTI), {
        'email_tier': best_tier,
        'email_reason': best_reason,
        'best_reachable_email': best_email,
        'email_arm_score': leg(PEP_E_ARM, PEP_E_ARM_MULTI),
        'usable_email_count': len(cands),
        'genuine_email_count': n_genuine,
    }


def phone_email_parallel_reachability_score(lead: dict) -> tuple[float, dict]:
    """phone_email_parallel profile (DDD-0004): (score 0–50, breakdown).

    The phone leg reuses `phone_first_reachability_score` UNCHANGED for its
    channel facts; the blended half re-weights them so the callable gate keeps
    its 25 points and email gets the rest. Breakdown keeps the DDD-0002 shape
    and adds the per-arm columns."""
    _, ph = phone_first_reachability_score(lead)
    em, em_bd = email_reach_score(lead)
    phone_ok = 'phone' in ph['channels'] or 'phone_alt' in ph['channels']
    genuine_email = E_ORDER.index(em_bd['email_tier']) >= E_ORDER.index(E_MIN_GENUINE)

    phone = 0.0
    if phone_ok:
        phone += PEP_PHONE_GATE
    if 'named_decision_maker' in ph['channels']:
        phone += PEP_PHONE_NAME
    if 'direct_line' in ph['channels']:
        phone += PEP_PHONE_DIRECT
    if 'fallback_contact' in ph['channels']:
        phone += PEP_PHONE_FALLBACK

    reach = phone + em
    # DDD-0001's no-channel rule, now channel-aware: a missing phone no longer
    # caps the email leg — an email-only lead is a real lead once email is an
    # outreach channel.
    if not phone_ok and em <= 0:
        reach = min(reach, NO_CHANNEL_MULTI_CAP)

    channels = list(ph['channels'])
    if em > 0:
        channels.append('email:' + em_bd['email_tier'])
    arm = ('both' if (phone_ok and genuine_email) else
           'phone' if phone_ok else 'email' if em > 0 else 'none')
    return round(min(REACH_CAP, reach), 2), {
        'usable_poc_count': ph['usable_poc_count'],
        'representative': ph['representative'],
        'channels': channels,
        'phone_reach_score': round(phone, 2),
        'email_reach_score': em,
        'ab_arm': arm,
        **em_bd,
    }


def reachability_score(lead: dict, profile: str = 'poc_channels') -> tuple[float, dict]:
    """Return (score, breakdown). Breakdown carries the representative
    contact's name, the channels credited, and the usable-POC count.

    `profile` selects the model: 'poc_channels' (default — reach a person via
    LinkedIn/email/social, 0–50), 'phone_first' (DDD-0002 — reps cold-call;
    callable number + owner name carry the score, 0–50), 'lpo_ladder'
    (DDD-0003 — strict personal-channel ladder that is itself the tier, 0–100),
    or 'phone_email_parallel' (DDD-0004 — phone and email as co-equal outreach
    channels for an A/B test, 0–50)."""
    if profile == 'lpo_ladder':
        return lpo_ladder_reachability_score(lead)
    if profile == 'phone_first':
        return phone_first_reachability_score(lead)
    if profile == 'phone_email_parallel':
        return phone_email_parallel_reachability_score(lead)
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
