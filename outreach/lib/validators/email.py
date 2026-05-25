"""
Validate emails extracted from lead-website crawls.

`validate_email(email, *, extra_vendor_domains=frozenset()) -> (valid, reason)`

`reason` is a short tag suitable for the `email_invalid_reason` field.
Returns (True, None) for emails that look like real practice contacts.

Categories of invalid:
  placeholder         — generic dummy text ('user@domain.com', 'example@*')
  vendor_marketing    — website-builder / SaaS vendor whose emails are never
                        real practice contacts
  image_artifact      — image filename that the @-regex picked up ('foo@2x.png')
  malformed           — does not look like a parseable email
  no_reply            — automated outbound-only address

Vendor scope: the lib's `VENDOR_DOMAINS` only lists domains generic to every
service-business vertical (web builders, template services, analytics SaaS).
Vertical-specific marketing vendors live in `pipelines/<vertical>/config.py:
VENDOR_DOMAINS_EXTRA` and are passed as `extra_vendor_domains`.
"""
import re
from typing import Optional, Tuple

# Generic web-builder / template / analytics / SaaS domains. Any practice-website
# crawler regardless of vertical will pick these up — they're never the
# practice's real address.
VENDOR_DOMAINS = frozenset({
    # Website builders / template services
    'wix.com', 'wixsite.com',
    'squarespace.com',
    'godaddy.com',
    'duda.co',
    'weebly.com',
    'webflow.io', 'webflow.com',
    'rola.com',
    'metapv.co',
    # Analytics / tracking / SaaS that show up via template emails
    'sentry.io', 'sentry-next.wixpress.com',
    'datadoghq.com',
    'hubspot.com',
    'mailchimp.com',
    'constantcontact.com',
    'cloudflare.com',
})

# Domains that are placeholder literals.
PLACEHOLDER_DOMAINS = frozenset({
    'domain.com', 'yourdomain.com', 'example.com', 'example.org', 'email.com',
    'yoursite.com', 'sample.com', 'test.com', 'demo.com', 'site.com', 'mywebsite.com',
})

# Username placeholders — case-insensitive comparison on the local part.
PLACEHOLDER_LOCALS = frozenset({
    'user', 'example', 'sample', 'test', 'demo', 'placeholder',
    'yourname', 'firstname', 'lastname', 'name', 'you',
    'email', 'youremail', 'someone', 'mail',
    'admin@admin', 'foo', 'bar', 'baz',
    'john.doe', 'jane.doe', 'john', 'jane',
    'info@info',
})

# No-reply / automation prefixes — mark non-deliverable for outreach.
NOREPLY_RE = re.compile(
    r'^(no[-_]?reply|do[-_]?not[-_]?reply|donotreply|mailer[-_]?daemon|postmaster|abuse|noreply|nobody)\b',
    re.I,
)

# Image filenames captured by the @-regex. Two flavors observed in the wild:
#   foo@2x.png            — retina-suffix immediately after the @
#   foo@-158x106.jpg      — width×height suffix with a separator after the @
# Allow any non-alpha chars between the @ and the `<digits>x<ext>` tail.
IMAGE_RE = re.compile(r'@[^a-zA-Z]*\d+x\d*\.(png|jpg|jpeg|svg|gif|webp)$', re.I)

# Basic email shape — already filtered upstream but double-check.
EMAIL_RE = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')


def validate_email(
    email: str,
    *,
    extra_vendor_domains: frozenset[str] = frozenset(),
) -> Tuple[bool, Optional[str]]:
    """Return (valid, reason). `extra_vendor_domains` extends the generic
    `VENDOR_DOMAINS` with vertical-specific vendors from pipeline config."""
    if not email or not isinstance(email, str):
        return False, 'malformed'
    em = email.strip().lower()

    if IMAGE_RE.search(em):
        return False, 'image_artifact'

    # URL-encoded chars in the local part are scraper noise (e.g. '%20info@...'
    # where '%20' is an encoded leading space). Real address syntax doesn't
    # use percent-encoding; the clean form is usually right next to it in
    # the captured list.
    if '%' in em.split('@', 1)[0]:
        return False, 'malformed'

    if not EMAIL_RE.match(em):
        return False, 'malformed'

    local, _, domain = em.partition('@')

    if domain in PLACEHOLDER_DOMAINS:
        return False, 'placeholder'

    if local in PLACEHOLDER_LOCALS:
        return False, 'placeholder'

    if NOREPLY_RE.match(local):
        return False, 'no_reply'

    if domain in VENDOR_DOMAINS or domain in extra_vendor_domains:
        return False, 'vendor_marketing'

    return True, None
